# PIT 安全特徵矩陣第一層 v1

狀態：BUILD_COMPLETE — 建置完成，待第 5 項審查驗收；不是效果掃描，也不是研究有效性結論。

## 結論邊界

- 本項只建立 L2 技術狀態與 L3 可由既有 PIT 資料支持的市場結構／背景。
- 未計算勝率、期望值、IC、有效特徵排名、存活名單或最佳參數。
- VCP Round 1 維持凍結；VCP Round 2 未執行，`min_amplitude_3=0.01` 仍只是未執行待測假設。
- 所有 rolling 先在完整歷史序列計算，再套 all_liquid + P2-060 當日母體。
- 股票技術價格使用既有 adjusted research coordinate；大盤只使用 FinMind TAIEX 含息指數。
- 本報告的 workflow success 只代表建置／驗證流程成功，不代表特徵有效或審查通過。

## 驗收交接識別

- 初始實作 commit：`24c0324cb8e798a3c1ed4d8ce54af742dd06e8f2`
- 建置前資料整合修正：
  - `53ab14eb935396bf6c99f17b811351db483848db` — PIT industry datetime resolution 正規化
  - `1f37fa1f427b548005d43f08b44868ed9d04031d` — industry cross-section 非連續 index 對齊
- 成功 build 的 head commit：`1b11924bea11a59749cb50b8637662345dc6af8d`
- 原始建置報告 commit：`e7dc6790b7d4f3bd948353c25b0e97dc27f2fce2`
- source revision：`fb8b042b46dc38838d103544ca17da10286c7bfe`
- config：`configs/research/pit_feature_matrix_layer1_v1.yaml`
- config SHA256：`dc4ad74beebdf4d9cb8f82180e12826b99dcfa337e8223329d59dc80ffa769d8`
- formula version：`pit_feature_matrix_layer1_v1`
- workflow：`PIT feature matrix layer1`，run `36662962925`，conclusion=`success`
- workflow URL：https://github.com/bibobo2266/AstraQuant/actions/runs/36662962925

## TEST_INVENTORY 範圍

已完成：
`L2-T01`, `L2-T02`, `L2-T03`, `L2-T04`, `L2-T05`, `L2-T06`, `L2-T07`, `L2-T08`, `L3-G01`, `L3-I01`, `L3-M01`, `L3-R01`, `L3-R02`。

受阻：
- `L3-G02` / `theme_membership`：`BLOCKED_DATA`。repo 沒有可持久讀取的 dated theme membership source，因此沒有用目前主題名單回貼歷史。

## 數字口徑對帳

### Dictionary

`out/pit_feature_matrix_layer1_v1_dictionary.csv` 共有 **72 個實體 row**：

- `COMPLETE`：**61**
  - `stock_features`：**58**
  - `market_context`：**3**
- `CONTROL`：**10**，全部是股票層固定種子亂數對照。
- `BLOCKED_DATA`：**1**，即 `theme_membership`。

因此：
- 「**43 個真實特徵**」是 `COMPLETE` rows 的 distinct `feature_key` 數，不是欄位／參數版本總數。
- 「**61 個真實參數版本**」是 dictionary 的 `COMPLETE` row 數，即 58 個股票特徵版本 + 3 個 market_context 版本。
- 「**10 個亂數對照**」是 `CONTROL` rows，與 61 不混計。
- 若看所有非 BLOCKED_DATA dictionary rows，`stock_features=68`（58 COMPLETE + 10 CONTROL）、`market_context=3`；再加 1 個 BLOCKED_DATA 股票 row，dictionary 的 `stock_features` 實體列總數為 69。

### Coverage CSV

`out/pit_feature_matrix_layer1_v1_coverage.csv` 共有 **414 列 = 69 列/年 × 6 年**。

每年 69 列固定由：
- 58 個 `COMPLETE stock_features`
- 10 個 `CONTROL`
- 1 個 `BLOCKED_DATA theme_membership`

組成。

3 個 `market_context` 不進股票逐年 coverage 表，因為它們是單一市場序列，不是股票橫截面欄位；其逐日可用性另在 `daily_valid_counts` 與 `market_context.parquet` 中保存。

原報告的「每年 68 列」不是 CSV 物理列數，而是建置程式在年度缺值摘要時**排除 BLOCKED_DATA 後**的 58 COMPLETE 股票 + 10 CONTROL。原文字未把這個口徑寫清楚，屬**文件說明錯誤／不完整**，不是資料少一列。本版改為同時列出「coverage.csv 實體 69」與「可建置缺值摘要 68」。

## 暖機與 2016 缺值限制

設定檔的實際暖機起點是 **2015-06-01**；E1 從 2016-01-04 開始。這段暖機不足以在 E1 一開始提供 250 個有效交易 session，更不足以提供 MA250 後再往回 10 session 的 slope。

2016 年 coverage.csv 中：
- `theme_membership`：100% 缺值，但狀態是 `BLOCKED_DATA`，不是一般特徵缺值，且不納入年度非 blocked 最大缺值率。
- `ma250_slope10`：44.32%，`WARMUP_INSUFFICIENT=25,552`
- `close_to_ma250`：40.34%，`WARMUP_INSUFFICIENT=23,254`
- `ma_order_score`：40.34%，`WARMUP_INSUFFICIENT=23,254`

以上三個 MA250 家族欄位的 `SOURCE_MISSING_INDUSTRY_PIT` 與 `SOURCE_MISSING_MARKET_VALUE` 都是 0，故主要不是來源欄位缺失。

進一步對帳：
- `close_to_ma250` / `ma_order_score` 在 **2016-01-04～2016-06-03** 的股票橫截面 `n_valid=0`；這段產生 22,779 筆暖機缺值。全年總暖機缺值 23,254，剩餘 475 筆發生在橫截面已開始有值之後，代表個別股票仍未累積足夠有效 session（例如較晚上市或個別歷史起點較短）。
- `ma250_slope10` 的 `n_valid=0` 區間延長到 **2016-06-20**；這段產生 25,058 筆暖機缺值。全年總暖機缺值 25,552，之後另有 494 筆個別股票暖機不足。

因此，2016 年任何使用 MA250／MA250 slope／依賴 MA250 排列的後續研究，都必須把 null 當成「尚無足夠歷史」而非 false/0；不能用填補把它變成可比較訊號。2016 前半年的覆蓋與後半年不同，後續若做效果研究必須明列有效樣本數，不可把早期缺值當成策略沒有觸發。

## 686 個不可用 feature-date：實際原因

`out/pit_feature_matrix_layer1_v1_unusable_dates.csv` 有 **686** 列，日期範圍 **2016-01-04～2018-12-22**。這 686 列不是單一原因，也不能解讀成「686 次特徵壞掉」。

實際拆分：

1. **510 列：長窗股票特徵尚未完成暖機，導致橫截面沒有任何有效值**
   - `close_to_ma250`：100 日，2016-01-04～2016-06-03，`n_valid=0`
   - `ma_order_score`：100 日，同上
   - `distance_250_high`：100 日，同上
   - `distance_250_low`：100 日，同上
   - `ma250_slope10`：110 日，2016-01-04～2016-06-20，`n_valid=0`

   這些日子的股票 `n_eligible` 多在約 200 多檔；很多落在 221～236，但排名失敗的直接原因是**長窗特徵 n_valid=0**，不是合格股票母體只剩 1 檔。

2. **152 列：market_context 長窗暖機**
   - `market_to_ma200`：50 日，2016-01-04～2016-03-22
   - `market_position252`：102 日，2016-01-04～2016-06-06

   這些 row 的 `n_eligible=1` 是因為 market_context 本來就是一條大盤序列，且 `rank_required=False`。因此 **不能把這 152 列解讀成股票母體縮到 1 檔**；它們是市場 MA200／252 日位置本身尚未暖機完成。

3. **24 列：市值／value-turnover 在 8 個日期沒有有效值**
   - `market_cap_twd` 8 列
   - `turnover_value_ratio` 8 列
   - `market_cap_tier` 8 列
   - 日期：2016-01-30、2016-06-04、2016-09-10、2017-02-18、2017-06-03、2017-09-30、2018-03-31、2018-12-22。

所以審查時應把 686 理解為「**feature-date 不可用紀錄**」，主要是長窗暖機，其次是 market_context 暖機，另有少量市值相關日期缺值；不是某一個特徵全面失效，也不是股票 eligible universe 普遍縮小。

## available_at audit：範圍與限制

`out/pit_feature_matrix_layer1_v1_available_at_audit.csv` 有 **1,000 筆，0 個 date-level violation**，但這不是「全面 PIT 安全」的證明。

實際抽樣設計：
- 完整 E1 股票 feature corpus：**421,362 個 eligible stock-date rows**（六個年度 parquet row 數合計）。
- 目前 audit 實作在逐年迴圈中填滿 1,000 筆 quota；2016 年第一個年度已填滿，因此**實際抽樣母體只涵蓋 2016 的 57,650 個 eligible stock-date rows**。
- 從 2016 frame 對 `date|stock_id` 使用穩定 hash 排序，取前 1,000 筆；不是隨執行順序取前 1,000。
- audit 比較每筆的：
  - 股票價格 row date
  - `industry_valid_from`
  - 有 market_value 時的同日 date
  - 有 market TRI 時的同日 date
  - 與輸出 `available_at_date`
- 在這個 date-level 檢查內，最大 input available date 沒有晚於 output available date，因此 violation=0。

本次 audit **未覆蓋**：
- 2017～2021 的抽樣；
- 逐一對 61 個 COMPLETE feature 公式做獨立 available_at tracing；
- provider 的盤中／發布時分秒，只驗到日期層級；
- market_value 真實發布時間晚於交易日收盤的可能 provider lag；
- `BLOCKED_DATA theme_membership`；
- 後續 outcome／交易流程（本項本來就不包含 outcome）。

因此正確結論是：「**2016 的 1,000 個 stock-date date-level availability sample 為 0 violation**」，不能擴張成全年度、全欄位、全 provider 時間戳都已證實 PIT 安全。

## 實際通過的測試與尚未驗證事項

成功 workflow 的 unit gate：**10 passed in 1.08s**。測試覆蓋：
- 未來資料變動不改寫過去已知特徵；
- rolling 暖機與 null 保留；
- adjusted price 常數尺度變換下比例類特徵一致；
- 同值 average-rank 與缺值排名；
- 10 個固定種子亂數對照的排序不變性；
- PIT industry 不回填首個 known date 之前；
- FeatureCache repeat hit；
- market_context 不做股票橫截面排名；
- PIT industry mixed datetime resolution；
- 非連續 index 下的產業橫截面對齊。

另外 workflow 的 `Verify no-effect contract` 成功，確認 manifest 為 E1、available_at violation=0、10 controls、6 個年度股票 parquet、無禁止的 outcome/effect 欄位。

尚未驗證／不在本項範圍：
- L3-G02 dated theme source；
- 2017～2021 的 available_at 抽樣；
- provider intraday publication timestamp；
- 籌碼／基本面／旗標；
- 任何特徵效果、IC、勝率、expectancy、策略存活或最佳參數；
- VCP Round 2 效果。

## 產物、保存期限與取得方式

### GitHub repo 內持久保存

- manifest：`out/pit_feature_matrix_layer1_v1_manifest.json`
- dictionary：`out/pit_feature_matrix_layer1_v1_dictionary.csv`
- coverage：`out/pit_feature_matrix_layer1_v1_coverage.csv`
- daily valid counts：`out/pit_feature_matrix_layer1_v1_daily_valid_counts.csv`
- unusable dates：`out/pit_feature_matrix_layer1_v1_unusable_dates.csv`
- available_at audit：`out/pit_feature_matrix_layer1_v1_available_at_audit.csv`
- 本交接報告：`docs/PIT_FEATURE_MATRIX_LAYER1_V1.md`

### Parquet 特徵資料

- Artifact name：`pit-feature-matrix-layer1-v1-36662962925`
- Artifact ID：`11075033221`
- Artifact size：269,648,589 bytes
- Artifact digest：`sha256:8eb1680a664471ac26aaf08d34119483772c4b570b02a7aa786d2eb8dc1c751c`
- Artifact URL：https://github.com/bibobo2266/AstraQuant/actions/runs/36662962925/artifacts/11075033221
- 建立時間：2026-09-30T03:11:03Z
- 到期時間：**2026-12-29T03:07:12Z（台北時間 2026-12-29 11:07:12）**
- retention：**90 天**

repo 沒有提交大型 parquet；目前它們只存在 GitHub Actions artifact。**到期後若沒有另行持久化備份，特徵 parquet 需重跑第 5 項建置流程才能重新取得。** 本項沒有因此重跑或新增研究。

Artifact 內含：
- `stock_features_2016.parquet`～`stock_features_2021.parquet`
- `market_context.parquet`

## baseline commits 自動 Actions 核對

這裡只記錄 trigger 與執行狀態，不把自動 CI／report workflow 解讀成新的 owner 研究任務，也不讀其 E3 效果。

### 全部 main push 都會觸發

1. `.github/workflows/tests.yml`
   - trigger：任何 `main` push。
   - baseline docs/config commits 都會自動排 tests。
   - 本次查看到的 baseline 相關 runs 為 completed/success。

2. `.github/workflows/legacy_breakout_regression.yml`
   - trigger：任何 `main` push。
   - 因此連 docs-only baseline commits 也會觸發。
   - 本次查看到的 baseline 相關 runs 為 completed/success。
   - 依治理契約，這是 EX-001 final-NAV boolean software regression，不代表新研究或 OOS 驗證。

### signal config push 另外會觸發

3. `.github/workflows/source_strategy_performance_report.yml`
   - push paths 包含：
     - `configs/research/runs/**`
     - `configs/examples/universes/**`
     - `configs/examples/signals/**`
     - `configs/examples/exits/**`
     - `src/astraquant/**`
     - 對應 workflow / report scripts / terminal-events 檔
   - baseline signal config 移動／提交位於 `configs/examples/signals/**`，因此觸發 `Governed canonical strategy performance report`。
   - 觀察到多個早期 run 為 `cancelled`，以及 commit `bc3894b...` 對應 run `36673163906` 為 `success`；該 workflow 使用共用 `research-effect-publication` concurrency group。
   - 這些是 repository 自動觸發的既有 report workflow，不視為 owner 在第 5 項啟動新研究。

### 不由這批 baseline signal files 觸發

4. `.github/workflows/source_config_sweep.yml`
   - 主要 push path 為 `configs/research/**`、特定 canonical signal/universe/exit 與 research engine 檔。
   - 一般 `configs/examples/signals/baseline_*.yaml` 不在其泛用 push path；本次 baseline signal moves 不因該路徑觸發 Source config sweep。

截至本交接撰寫時，以上查到的 baseline 相關 Actions 都已是 completed 狀態；本項沒有修改 workflow、取消 run 或新增效果查詢。

## 年度 coverage 摘要

下表的「可建置摘要列」**排除 BLOCKED_DATA**，所以是每年 68；實體 `coverage.csv` 每年是 69（再加 1 個 `theme_membership BLOCKED_DATA`）。

| 年 | coverage.csv 實體列 | 可建置摘要列 | 缺值率中位數 | 非 BLOCKED_DATA 最大缺值率 |
|---:|---:|---:|---:|---:|
| 2016 | 69 | 68 | 0.25% | 44.32% |
| 2017 | 69 | 68 | 0.13% | 5.76% |
| 2018 | 69 | 68 | 0.10% | 4.80% |
| 2019 | 69 | 68 | 0.05% | 3.40% |
| 2020 | 69 | 68 | 0.03% | 2.58% |
| 2021 | 69 | 68 | 0.22% | 1.91% |

## 執行摘要

- cache hits/misses：11 / 143；repeat-hit gate=True
- runtime：139.8 秒
- peak RSS：1679.0 MiB
- no-effect contract：pass
- Round 2 executed：false

## 研究防線

本項沒有 outcome 欄位，也沒有讀取 E2/E3 效果。第 5 項目前只到「建置完成，待審查驗收」；不自動開始第 6 項、baseline 回測或 VCP Round 2。
