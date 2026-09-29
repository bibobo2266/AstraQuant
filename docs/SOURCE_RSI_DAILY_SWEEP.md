# Candidate Path Diagnostics

Status: **PASS**

## 定位與時期

- epoch: E1：歷史開發期
- 本報告只做路徑診斷；MFE / MAE / order_state / days_to_MFE / days_to_MAE 不取代完整交易績效，也不得單獨判定訊號有效或無效。
- E1 為預設；E2 僅能以 RESEARCH_EPOCH=E2 顯式啟用；E3 由治理層阻擋。
- 本報告是候選層，不套用部位上限與資金限制；候選數不等於可執行交易數，資金受限結果另行報告。
- direction: LONG
- windows: 5 / 10 / 20 common trading sessions; entry day is day 1.
- entry_ref: signal date next common trading session RAW open; no valid open => NO_VALID_ENTRY_REF; no delay and no skip-forward.
- path value V_t uses one initial unit with canonical cash/share/successor/terminal corporate-action semantics.
- multi-successor intraday extrema are not summed; they are MULTI_LEG_INTRADAY_UNRESOLVED.

## 方向定義

- LONG: favorable = V_t^high - 1; adverse = V_t^low - 1.
- SHORT (Anchor-DOWN): favorable = 1 - V_t^low; adverse = 1 - V_t^high.
- MFE is maximum favorable deviation; MAE is minimum adverse deviation.
- repeated cross-day extrema use the first day; same-day MFE/MAE is SAME_DAY_UNKNOWN because daily OHLC cannot establish intraday order.

## 去均值

- Demean mother is all same-day four-digit P2-060 common-support names with observed_trade and valid_ohlc, not the triggered signal set.
- MFE and MAE are demeaned separately; a date requires at least 200 calculable mother names for that window.
- SHORT uses the same short-direction transformation for the mother before demeaning.

## 漲跌停口徑

- Uses source price-limit records when an explicit daily upper/lower limit or explicit no-limit state is available.
- No previous-close fixed-multiplier fallback is used. Missing source limit information is counted as limit-price-unknown.
- source price-limit file years present: 2015,2016,2017,2018
- Touch flags are market-constraint diagnostics only; touch does not mean locked and daily OHLC cannot establish fillability at the extreme.

## 不可計算與跨界

- Each 5/10/20 window is purged independently. A window crossing the epoch boundary is counted and excluded; it is never shortened.
- Suspended/no-price sessions remain calendar days. Existing terminal stale-mark semantics are used only inside an explicitly modeled terminal stale window; otherwise missing RAW path value is reported, not filled.
- build_supported_ca unsupported source rows observed: 0; event summary: {}

## 參數組合 × 窗口輸出

- machine-readable table: docs/SOURCE_RSI_DAILY_SWEEP.csv
- rows: 828
- columns include candidate/calculable/unique counts, truncation/missing/terminal/NO_VALID_ENTRY_REF/multi-leg/cross-boundary counts, multi-leg share, all requested price-limit strata, demeaned MFE/MAE medians, days-to-extrema medians, three order_state shares, raw MFE threshold candidate shares, and the auxiliary raw MFE / |raw MAE| median plus undefined share.
- raw MFE > 5% / 10% / 20% shares use all signal candidates as the denominator; non-calculable candidates remain in that denominator and are separately disclosed by status counts.

## 比值限制

每筆原始 MFE / |原始 MAE| 僅為輔助描述；原始 MAE = 0 時保持未定義，不代入任意小數。此比值不是交易賠率，也不能推出每筆期望值，因為最大有利與最大不利偏離不是可同時實現的一筆交易結果。

## 待驗證解釋清單

- 若後續對齊完整交易後觀察到 MFE 明顯高於實際獲利，待驗證：出場過早、出場過晚後回吐、執行價與極值價差異、極值當下不可成交（鎖停或無量）。
- 若後續對齊完整交易後觀察到 MAE 淺但遭停損掃出，待驗證：停損過緊、停損採用的價格基準與診斷不同、盤中觸價與收盤價差異。
- 若極值集中於窗口末端，只標示邊界效應提示；不自動主張延長窗口，也不據此選擇最佳窗口。
- 上述均為待驗證解釋，不是成因判定。
