# =============================================================================
# 直近の新発債チェック
#
# 【前提】既存コード → jgb_base.py の順に実行した後、その下に貼って実行する
#         （bond, yld, cm_ticker を使う）
#
# 【見るところ】
#   残存 5.0 / 10.0 / 20.0 / 30.0 年前後の新発債について
#   - 行がない             → 銘柄マスタに入っていない
#   - 利回り列あり = False → Bloomberg の取得対象に入っていない
#   - 直近利回り = NaN     → 直近日のデータがまだ来ていない（最終データ日を確認）
# =============================================================================

# %% 年限ごとの候補銘柄
latest = yld.index[-1]
print('直近日:', latest.date())

for code, lo, hi in [('JS', 4.4, 5.6), ('JB', 9.4, 10.6), ('JL', 19.4, 20.6), ('JX', 29.4, 30.6)]:
    m = bond[bond.index.str.startswith(code)].copy()
    m['残存'] = ((m['maturity'] - latest).dt.days / 365.25).round(2)
    m = m[(m['残存'] >= lo) & (m['残存'] <= hi)]
    m['利回り列あり'] = m.index.isin(yld.columns)
    m['直近利回り'] = [yld.loc[latest, t] if t in yld.columns else None for t in m.index]
    m['最終データ日'] = [
        yld[t].last_valid_index().date() if t in yld.columns and yld[t].notna().any() else None
        for t in m.index
    ]
    print(f'--- {code} ---')
    print(m[['maturity', 'issue', '残存', '利回り列あり', '直近利回り', '最終データ日']])

# %% 5y の銘柄切り替わり履歴（直近10回）
s = cm_ticker['5y']
chg = s[s != s.shift()]
print('--- 5y 切り替わり ---')
print(chg.tail(10))
