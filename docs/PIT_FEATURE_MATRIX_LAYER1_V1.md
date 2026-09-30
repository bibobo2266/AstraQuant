# PIT 安全特徵矩陣第一層 v1

狀態：COMPLETE — E1 資料建置與資料品質稽核；不是效果掃描。

## 結論邊界

- 本項只建立 L2 技術狀態與 L3 可由既有 PIT 資料支持的市場結構／背景。
- 未計算勝率、期望值、IC、特徵排名、存活名單或最佳參數。
- VCP Round 1 維持凍結；Round 2 未執行。
- 所有 rolling 先在完整歷史序列計算，再套 all_liquid + P2-060 當日母體。
- 股票技術價格使用既有 adjusted research coordinate；大盤只使用 FinMind TAIEX 含息指數。

## 範圍

- 完成 TEST_INVENTORY IDs：L2-T01, L2-T02, L2-T03, L2-T04, L2-T05, L2-T06, L2-T07, L2-T08, L3-G01, L3-I01, L3-M01, L3-R01, L3-R02
- BLOCKED_DATA IDs：L3-G02
- 真實原始特徵數（distinct feature_key）：**43**
- 真實參數版本數（dictionary COMPLETE rows）：**61**
- 固定種子亂數對照：**10**

L3-G02 主題名單沒有可持久讀取的 dated membership source，因此本輪明確標 BLOCKED_DATA；沒有用目前名單回貼歷史。

## 來源與 available_at

- source revision：fb8b042b46dc38838d103544ca17da10286c7bfe
- formula version：pit_feature_matrix_layer1_v1
- E1：2016-01-04～2021-12-31；只讀 E1 之前資料作 rolling 暖機。
- adjusted OHLCV / Trading_money：當日收盤後可用。
- market_value：FinMind 當日市值欄；本矩陣只宣告同日 provider publication 後／次一交易決策可用，不宣稱盤中可用。
- PIT industry：只在 industry_pit.valid_from 之後使用，缺歷史不回填。
- market_context：FinMind TaiwanStockTotalReturnIndex (TAIEX)，含息口徑；market_context 不做股票橫截面排名。

## 資料品質

- available_at 抽樣：1,000 筆；違反數：**0**。
- 每日有效標的不足而不可排名／不可用的 feature-date：**686**；詳見 unusable_dates CSV。
- cache hits/misses：11 / 143；repeat-hit gate=True.
- 執行秒數：139.8；peak RSS：1679.0 MiB。

### 逐年覆蓋摘要

| 年 | 特徵版本列 | 缺值率中位數 | 最大缺值率 |
|---:|---:|---:|---:|
| 2016 | 68 | 0.25% | 44.32% |
| 2017 | 68 | 0.13% | 5.76% |
| 2018 | 68 | 0.10% | 4.80% |
| 2019 | 68 | 0.05% | 3.40% |
| 2020 | 68 | 0.03% | 2.58% |
| 2021 | 68 | 0.22% | 1.91% |

## 產物

- GitHub Actions artifact：pit-feature-matrix-layer1-v1-36662962925
- workflow run：https://github.com/bibobo2266/AstraQuant/actions/runs/36662962925
- artifact 內含 stock_features_2016.parquet～stock_features_2021.parquet 與 market_context.parquet。
- repo 內保留 manifest、feature dictionary、逐年 coverage、每日有效數、不可用日期與 available_at audit。

## 研究防線

本項沒有 outcome 欄位，也沒有讀取 E2/E3 效果。任何後續疊加或 ML 都必須另依 queue 啟動；本項不自動開始。
