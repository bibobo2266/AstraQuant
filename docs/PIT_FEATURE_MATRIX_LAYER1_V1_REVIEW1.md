# PIT 特徵矩陣第 5 項驗收修正 — review1

狀態：修正完成，待審查驗收。這是品質稽核修正，不是新研究，也沒有重跑策略效果。

## 版本與不變項

- base feature version：`pit_feature_matrix_layer1_v1`
- review version：`pit_feature_matrix_layer1_v1_review1`
- source revision：`fb8b042b46dc38838d103544ca17da10286c7bfe`
- feature formula version：`pit_feature_matrix_layer1_v1`（未修改）
- base config：`configs/research/pit_feature_matrix_layer1_v1.yaml`，SHA256 `dc4ad74beebdf4d9cb8f82180e12826b99dcfa337e8223329d59dc80ffa769d8`
- review config：`configs/quality/pit_feature_matrix_layer1_v1_review1.yaml`
- feature parquet：**未重建、未覆蓋**；review1 只新增 QA/audit 產物。
- E1 仍是 2016-01-04～2021-12-31；未查 E2/E3 效果。

## available_at 修正

- 固定 seed：20260930
- stock_features：每年 180 筆
- market_context：每年 12 筆
- 總 audit sample：**1152** 筆；FAIL=0、UNKNOWN=1152、PASS=0。

| 年 | scope | PASS | FAIL | UNKNOWN |
|---:|---|---:|---:|---:|
| 2016 | market_context | 0 | 0 | 12 |
| 2016 | stock_features | 0 | 0 | 180 |
| 2017 | market_context | 0 | 0 | 12 |
| 2017 | stock_features | 0 | 0 | 180 |
| 2018 | market_context | 0 | 0 | 12 |
| 2018 | stock_features | 0 | 0 | 180 |
| 2019 | market_context | 0 | 0 | 12 |
| 2019 | stock_features | 0 | 0 | 180 |
| 2020 | market_context | 0 | 0 | 12 |
| 2020 | stock_features | 0 | 0 | 180 |
| 2021 | market_context | 0 | 0 | 12 |
| 2021 | stock_features | 0 | 0 | 180 |

### 可用時間證據結論

- 這次不再把「交易日期 <= 輸出日期」當成 PIT PASS。
- adjusted EOD、tradability、market_value、TAIEX TRI 的 source parquet 都沒有保留實際 provider available_at/known-time；因此精確到 AFTER_SESSION_CLOSE 決策時點一律為 **UNKNOWN**，不是 PASS。
- PIT industry 的 valid_from 由官方 MOPS snapshot available_date / reclassification effective_date 因果建置，**date-level causal order 有證據**；但 source 沒有時分秒，因此同日 AFTER_SESSION_CLOSE 的精確可用性仍是 **UNKNOWN**。
- fixed-seed random controls 不讀外部資料，raw control value 為 PASS；若使用其同日橫截面 percentile，仍會依賴 eligible-universe 輸入的可用時間。
- 所以目前真實 COMPLETE features 不可被宣稱為『已證實可在精確 AFTER_SESSION_CLOSE 決策時點 PIT 安全』。它們仍可作描述性／資料建置用途，待來源時間戳或更強的發布契約補齊。

完整逐 feature 證據見 availability_evidence CSV。逐 feature 證據列的結果為：**10 個 deterministic random controls = PASS；61 個 COMPLETE 真實特徵 + 1 個 BLOCKED_DATA = UNKNOWN；FAIL=0**。這裡的 PASS 只適用於不讀外部資料的 control raw value，不可轉述成真實特徵已通過 PIT。

## 長窗暖機診斷

- adjusted research price 實際最早：**2015-06-01**。
- RAW execution price 可早到 **2015-01-05**，但 RAW 與 ADJUSTED_RESEARCH 是不同價格座標，不能拿 RAW 補 MA250 等 adjusted 技術特徵。
- market_value 實際最早：2015-06-01。
- industry monthly snapshot available_date 可早於 adjusted price；但股票技術矩陣仍受 adjusted 起點限制。
- TAIEX total-return index 實際最早：**2015-06-01**；market MA200 第一個可用日為 **2016-03-23**，market position252 第一個可用日為 **2016-06-07**。
- 股票長窗第一個可用日：`close_to_ma250` / `ma_order_score` / `distance_250_high` / `distance_250_low` 為 **2016-06-04**；`ma250_slope10` 為 **2016-06-21**。
- 因此原 v1 的 2015-06-01 不是 loader 人為截短，而是 adjusted source 本身的起點；本次沒有可合法擴大的 adjusted 暖機資料，所以不重建 feature parquet。
- MA250 家族 2016 早期 null 必須保留；來源歷史不足之外，部分較晚上市股票另有個股歷史不足。null 不得補零、前填或視為條件不成立。

## 修正前後 coverage

- feature values 與公式未改、parquet 未重建，因此逐年 coverage **前後完全相同**；review1 只修正 audit 與文件口徑。

| 年 | feature rows | before median missing | after median missing | before max | after max |
|---:|---:|---:|---:|---:|---:|
| 2016 | 68 | 0.25% | 0.25% | 44.32% | 44.32% |
| 2017 | 68 | 0.13% | 0.13% | 5.76% | 5.76% |
| 2018 | 68 | 0.10% | 0.10% | 4.80% | 4.80% |
| 2019 | 68 | 0.05% | 0.05% | 3.40% | 3.40% |
| 2020 | 68 | 0.03% | 0.03% | 2.58% | 2.58% |
| 2021 | 68 | 0.22% | 0.22% | 1.91% | 1.91% |

## MA120 重用驗收

- dictionary 原值公式：`adjusted_close / SMA120(adjusted_close) - 1`。
- 正確條件「收盤 >= MA120」就是 **close_to_ma120 >= 0.0**；不是 >=1，也不是 percentile >=0。
- raw `close_to_ma120` 欄位會保留在 feature parquet；COLUMN_THRESHOLD 對 synthetic gate 已驗證：[-0.01, 0, 0.02, null] -> [false, true, true, false]。
- `SignalEvaluator._normalize_panel` 保留額外欄位，所以只要欄位已在 caller-supplied panel 中，COLUMN_THRESHOLD 可直接讀。
- 但 `ResearchConfigEngine.prepare()` 本身**不會自動載入／join 第 5 項 parquet**；現有 canonical strategy runner 仍傳入原 research panel。
- 結論：**計算已存在，但仍缺串接**。不需要新增 PRICE_ABOVE_MA evaluator；需要的是 feature artifact -> canonical panel 的明確 hydration/join。
- 缺值時 COLUMN_THRESHOLD 回 false；這只代表『filter 不通過』，不能在報告中把 null 說成『價格低於 MA120』。
- close_to_ma120 精確決策時點 available_at：**UNKNOWN**。

## Baseline 缺口更正

- `BASELINE_COMPONENT_GAPS.md` 已移除『PRICE_ABOVE_MA 確實缺 evaluator』的舊結論。
- 舊文件的 C 類文字計數本身少算一列；實體表原為 11 列。移出 `PRICE_ABOVE_MA` 後，C 類現為 **10**；B 類可重用計算但缺介面為 **5**。
- 60 日突破 baseline 的最小缺口改為：**2 個確實缺的 exit evaluator + 1 個 feature-panel 串接工作**；不再寫『最少新增 3 個 evaluator』。
- 本次沒有新增 baseline evaluator，也沒有跑 baseline。

## 測試與產物

- review workflow：https://github.com/bibobo2266/AstraQuant/actions/runs/36685799139
- review artifact：`pit-feature-matrix-layer1-v1-review1-36685799139`；ID `11083208566`；90 天 retention；到期 `2026-12-29T07:48:02Z`（台北時間 2026-12-29 15:48:02）
- review manifest：`out/pit_feature_matrix_layer1_v1_review1_manifest.json`
- stratified audit：`out/pit_feature_matrix_layer1_v1_review1_available_at_audit.csv`
- availability evidence：`out/pit_feature_matrix_layer1_v1_review1_availability_evidence.csv`
- warmup diagnostic：`out/pit_feature_matrix_layer1_v1_review1_warmup_diagnostic.csv`
- coverage comparison：`out/pit_feature_matrix_layer1_v1_review1_coverage_comparison.csv`
- MA120 audit：`out/pit_feature_matrix_layer1_v1_review1_ma120_audit.csv`

review workflow 的 unit gate 實際結果：**13 passed in 1.25s**。其中明確覆蓋：跨年分層抽樣不會被第一年吃完整 quota；UNKNOWN 不會被聚合成 PASS；MA120 threshold=0 語意；另與原第 5 項測試一起執行。

## 尚未解決限制

- 真實 features 的精確 provider availability timestamp 仍未建立，所以 decision-time PIT 為 UNKNOWN。
- L3-G02 theme_membership 仍為 BLOCKED_DATA。
- 第 5 項 feature parquet 本身仍使用原 v1 artifact `pit-feature-matrix-layer1-v1-36662962925`；ID `11075033221`；到期 `2026-12-29T03:07:12Z`（台北時間 2026-12-29 11:07:12）。review1 沒有改值也沒有延長其保存期限；到期後若未另行持久化，parquet 需重建才能取得。
- 未啟動 ML、baseline 回測、VCP Round 2；未讀 E2/E3 效果。

