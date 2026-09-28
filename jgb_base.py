# =============================================================================
# JGB / ASW 固定年限データ作成（土台コード）
#
# 【前提】既存コードの以下の変数を作るセルまで実行してから、このファイルを貼って実行する
#   df_bond : 銘柄マスタ（ticker, maturity, issue ...）
#   df      : OISレート（列名 'oisrate(jpy,,YYYYMMDD)'、単位 bp、index は object）
#   df_bbg  : JGB利回り（列名 'JB347' など、単位 bp、index は DatetimeIndex）
#
# 【既存コードからの変更点】
#   1. index の型を揃えてから結合（OISは object、Bloombergは DatetimeIndex だったため）
#   2. 目標年限から離れすぎた銘柄しかない日は NaN にする
#      （マスタに償還済み銘柄がないため、過去の1y/2y等が長い銘柄で代用されていた問題への対処）
#   3. 各日にどの銘柄を使ったかを記録（銘柄入れ替えによるジャンプを確認できるように）
#   4. 最後に df_jgb_current / df_asw_current を上書きするので、既存のプロットセルはそのまま使える
# =============================================================================

# %% [0] 設定
import os
import re
import numpy as np
import pandas as pd

OUT_DIR = r'/home/desktop/data'   # ← 会社PCの保存先に置き換える
os.makedirs(OUT_DIR, exist_ok=True)

TENOR_CODE_LIST = [
    ('1y', 'JN'), ('2y', 'JN'), ('3y', 'JS'), ('4y', 'JS'), ('5y', 'JS'),
    ('6y', 'JB'), ('7y', 'JB'), ('8y', 'JB'), ('9y', 'JB'), ('10y', 'JB'),
    ('11y', 'JL'), ('12y', 'JL'), ('15y', 'JL'), ('20y', 'JL'),
    ('25y', 'JX'), ('30y', 'JX'), ('35y', 'JU'), ('40y', 'JU'),
]

# 許容ずれ（年）= max(TOL_MIN, TOL_RATIO × 目標年限)
#   例: 1y,2y → 0.25年 / 5y → 0.5年 / 10y → 1年 / 30y → 3年
TOL_MIN = 0.25
TOL_RATIO = 0.10

STD_WEIGHT = {1: [1], 2: [-1, +1], 3: [-1, +2, -1]}
LEGS_LIST = [
    '2y', '5y', '7y', '10y', '20y', '30y', '40y',
    '2y 5y', '5y 7y', '7y 10y', '5y 10y', '10y 20y', '10y 30y', '20y 30y', '30y 40y',
    '2y 5y 7y', '2y 5y 10y', '5y 7y 10y', '10y 15y 20y', '10y 20y 30y',
]

# %% [1] 形式を揃える
# 銘柄マスタ：日付型に変換し、ticker を index に
bond = df_bond.copy()
bond['maturity'] = pd.to_datetime(bond['maturity'])
bond['issue'] = pd.to_datetime(bond['issue'])
bond = bond.drop_duplicates('ticker').set_index('ticker')

# JGB利回り：マスタにある銘柄だけ
yld = df_bbg.copy()
yld.index = pd.to_datetime(yld.index)
yld = yld[[t for t in yld.columns if t in bond.index]]

# OIS：列名 'oisrate(jpy,,YYYYMMDD)' → 償還日（Timestamp）
ois = df.copy()
ois.index = pd.to_datetime(ois.index)
ois = ois[[c for c in ois.columns if re.search(r'\d{8}', str(c))]]
ois.columns = pd.to_datetime([re.search(r'(\d{8})', str(c)).group(1) for c in ois.columns],
                             format='%Y%m%d')
ois = ois.loc[:, ~ois.columns.duplicated()]

# 両方にある日付だけ
dates = yld.index.intersection(ois.index).sort_values()
yld = yld.loc[dates]
ois = ois.loc[dates]

print(f'共通営業日: {len(dates)}日 ({dates.min().date()} ~ {dates.max().date()})')
print(f'JGB銘柄数: {yld.shape[1]} / OIS償還日数: {ois.shape[1]}')

# %% [2] 銘柄別ASW（利回り − 同一償還日OIS）
mat_of = bond.loc[yld.columns, 'maturity']
ois_matched = ois.reindex(columns=mat_of.values)
ois_matched.columns = yld.columns
bond_asw = yld - ois_matched

missing = mat_of[~mat_of.isin(ois.columns)]
if len(missing):
    print(f'※ OISがない償還日の銘柄: {len(missing)}本 → ASWはNaN', list(missing.index[:10]))

# %% [3] 残存年数（日付 × 銘柄）
days_left = mat_of.values[None, :] - dates.values[:, None]
ttm = pd.DataFrame(days_left / np.timedelta64(1, 'D') / 365.25,
                   index=dates, columns=yld.columns)


# %% [4] 固定年限：各日で目標年限に最も近い銘柄を選ぶ
def select_bonds(yld, ttm, tenor_list, tol_min=TOL_MIN, tol_ratio=TOL_RATIO):
    """各日・各年限で使う銘柄(ticker)と、その残存年数を返す。許容ずれを超えたら NaN。"""
    tickers, ttm_used = {}, {}
    rows = np.arange(len(yld))
    for tenor, code in tenor_list:
        target = float(tenor.replace('y', ''))
        cols = np.array([c for c in yld.columns if c.startswith(code)])
        if len(cols) == 0:
            tickers[tenor] = [None] * len(yld)
            ttm_used[tenor] = np.nan
            continue
        t = ttm[cols].to_numpy()
        gap = np.abs(t - target)
        gap[np.isnan(yld[cols].to_numpy())] = np.inf   # 利回りがない日は候補外
        idx = gap.argmin(axis=1)
        best_gap = gap[rows, idx]
        ok = best_gap <= max(tol_min, tol_ratio * target)
        tickers[tenor] = np.where(ok, cols[idx], None)
        ttm_used[tenor] = np.where(ok, t[rows, idx], np.nan)
    return (pd.DataFrame(tickers, index=yld.index),
            pd.DataFrame(ttm_used, index=yld.index))


def pick(values, tickers):
    """tickers（日付×年限）が指す銘柄の値を values（日付×銘柄）から取り出す。"""
    arr = values.to_numpy()
    col_pos = {c: i for i, c in enumerate(values.columns)}
    rows = np.arange(len(values))
    out = {}
    for tenor in tickers.columns:
        pos = tickers[tenor].map(col_pos)
        mask = pos.notna().to_numpy()
        res = np.full(len(values), np.nan)
        res[mask] = arr[rows[mask], pos[mask].astype(int).to_numpy()]
        out[tenor] = res
    return pd.DataFrame(out, index=values.index)


cm_ticker, cm_ttm = select_bonds(yld, ttm, TENOR_CODE_LIST)
jgb_cm = pick(yld, cm_ticker)        # 固定年限 利回り (bp)
asw_cm = pick(bond_asw, cm_ticker)   # 固定年限 ASW (bp)　※利回りと同じ銘柄を使用


# %% [5] レッグ（アウトライト・スロープ・バタフライ）
def calc_leg(cm, legs, std_weight=STD_WEIGHT):
    legs = legs.split(' ')
    weights = std_weight[len(legs)]
    return sum(w * cm[leg] for w, leg in zip(weights, legs))   # どれかの脚がNaNならNaN


jgb_legs = pd.DataFrame({leg: calc_leg(jgb_cm, leg) for leg in LEGS_LIST})
asw_legs = pd.DataFrame({leg: calc_leg(asw_cm, leg) for leg in LEGS_LIST})

# %% [6] チェック用サマリー
switch = (cm_ticker != cm_ticker.shift()) & cm_ticker.notna() & cm_ticker.shift().notna()
summary = pd.DataFrame({
    '許容ずれ(年)': [max(TOL_MIN, TOL_RATIO * float(t.replace('y', ''))) for t in jgb_cm.columns],
    '開始日': [jgb_cm[t].first_valid_index() for t in jgb_cm.columns],
    'カバー率(%)': (jgb_cm.notna().mean() * 100).round(1).values,
    '銘柄入替回数': switch.sum().values,
    '直近銘柄': cm_ticker.iloc[-1].values,
    '直近残存(年)': cm_ttm.iloc[-1].round(2).values,
    '直近利回り(bp)': jgb_cm.iloc[-1].round(1).values,
    '直近ASW(bp)': asw_cm.iloc[-1].round(1).values,
}, index=jgb_cm.columns)
pd.set_option('display.width', 200)
print(summary)

# %% [7] 保存
jgb_cm.to_csv(os.path.join(OUT_DIR, 'jgb_cm.csv'))
asw_cm.to_csv(os.path.join(OUT_DIR, 'asw_cm.csv'))
cm_ticker.to_csv(os.path.join(OUT_DIR, 'cm_ticker.csv'))
cm_ttm.to_csv(os.path.join(OUT_DIR, 'cm_ttm.csv'))
jgb_legs.to_csv(os.path.join(OUT_DIR, 'jgb_legs.csv'))
asw_legs.to_csv(os.path.join(OUT_DIR, 'asw_legs.csv'))
bond_asw.to_csv(os.path.join(OUT_DIR, 'bond_asw.csv'))

# 既存のプロットセル（calc_leg_series(df_jgb_current, leg) 等）をそのまま使えるように上書き
df_jgb_current = jgb_cm
df_asw_current = asw_cm
