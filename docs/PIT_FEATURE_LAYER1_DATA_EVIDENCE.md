# 第 5 項資料查核證據

範圍：固定 source `fb8b042b46dc38838d103544ca17da10286c7bfe`，既有 run `36702638509` 的產物加上來源品質查核。沒有策略效果查詢。兩個祖先版本僅讀 **2017 歷史價** 追溯回寫，沒有讀取 E3 行情或績效。

## 1. 重現與證據完整性

- 查核程式：[layer1_data_decision_probe.py](../scripts/layer1_data_decision_probe.py)。只做全市場 key 覆蓋／事件指派、10 個 E1 日期的母體資格核對，以及固定四檔、28 個股票日重建；不計算全市場 MA/N60、不重跑完整稽核。
- [inputs.json](../out/layer1_data_decision/inputs.json) 固定每個來源 Git blob SHA 與 SHA256；程式讀取前逐一核驗。
- 樣本固定 1101、1216、2317、2330：每年第一個觀測日，加 1216 的 2016-08-03/04、2330 的 2016-06-24/27。日期依除息事件選定，不依策略結果。
- [price_samples.csv](../out/layer1_data_decision/price_samples.csv) 記 RAW、stored adjusted、factor、兩種重建、價差、來源與當日 all_liquid 資格。1216、2330 全部樣本均在原研究母體內；1101 的樣本也在母體；2317 因 P2-060 排除，只是其他 CA 的額外對照。
- [sample_source_validation.csv](../out/layer1_data_decision/sample_source_validation.csv) 直接執行原腳本的 `source_validation` 函式於這 28 列。原欄名 `match_within_0_00005` 實際依 `PRICE_REBUILD_ATOL=0.0001`；本次揭露此命名差異，不改歷史欄名或容差。
- [reconstruction_steps.csv](../out/layer1_data_decision/reconstruction_steps.csv) 逐樣本、逐事件列 before/after、ratio、累乘因子與 rounding 誤差界；[sample_events.csv](../out/layer1_data_decision/sample_events.csv) 保留來源 before/after 及排除理由。

本地重現：將 manifest 指定來源檔放在唯讀來源副本的對應 path；祖先檔放 `snapshots/<sha>/prices_adj_2017.parquet`，保持與 `data/` 同層。從 repo root 執行：

```bash
PYTHONPATH=src SOURCE_ROOT=/path/to/frozen-source/data \
SOURCE_REVISION=fb8b042b46dc38838d103544ca17da10286c7bfe \
python scripts/layer1_data_decision_probe.py
```

若來源目錄沒有 `input_blobs.json`，程式使用已提交的 `out/layer1_data_decision/inputs.json`。不需要網路取數、API token 或 Actions；來源檔內容不回寫。

## 2. 2016 零事件：原表到彙總的完整鏈

來源 [dividend_events.parquet](https://github.com/bibobo2266/minervini_picks/blob/fb8b042b46dc38838d103544ca17da10286c7bfe/data/adj/dividend_events.parquet)，blob `5c8ae7734357bffc44da7d53d50ee9e1286dc27f`。

| 年 | 原表 | 日期範圍 | ratio 排除 | normalize 後 |
|---|---:|---|---:|---:|
| 2015 | 0 | 無 | 0 | 0 |
| 2016 | 0 | 無 | 0 | 0 |
| 2017 | 1,252 | 01-10～12-27 | 0 | 1,252 |
| 2018 | 1,297 | 01-09～12-28 | 1 | 1,296 |
| 2019 | 1,367 | 01-02～12-27 | 0 | 1,367 |
| 2020 | 1,371 | 01-02～12-30 | 0 | 1,371 |
| 2021 | 1,477 | 01-05～12-23 | 0 | 1,477 |
| 2022 | 1,548 | 01-03～12-28 | 1 | 1,547 |
| 2023 | 1,581 | 01-04～12-27 | 0 | 1,581 |
| 2024 | 1,586 | 01-03～12-30 | 2 | 1,584 |
| 2025 | 1,649 | 01-02～12-31 | 0 | 1,649 |
| 2026 | 1,463 | 01-05～08-28 | 1 | 1,462 |
| 合計 | 14,591 | 2017-01-10～2026-08-28 | 5 | 14,586 |

invalid date=0、before/after 非正或缺失=0、同股同日 group 合併減少=0。五筆排除：4303/2018-08-29、3293/2022-07-27、3293/2024-07-24、1808/2024-09-26、5314/2026-08-14，全部是 ratio<0.5；沒有放寬倍率，也沒有為了對帳改年份。詳見 [events_by_year](../out/layer1_data_decision/events_by_year.csv)、[excluded_events](../out/layer1_data_decision/excluded_events.csv)。

online 的觀測序列是原腳本 adjusted keys 左接 RAW，起於 2015-01-01 暖機；在 T 處理 event.date≤T 的未處理事件。只用 keys 的 searchsorted 重現事件首次處理日，不重算 MA/N60。對帳如下：

| 事件年 | E1 已處理 | 無對應 adjusted 股票 | 無後續觀測 | 暖機處理 | 非事件當日、延至下一觀測 |
|---|---:|---:|---:|---:|---:|
| 2015 | 0 | 0 | 0 | 0 | 0 |
| 2016 | 0 | 0 | 0 | 0 | 0 |
| 2017 | 1,252 | 0 | 0 | 0 | 0 |
| 2018 | 1,296 | 0 | 0 | 0 | 0 |
| 2019 | 1,367 | 0 | 0 | 0 | 12 |
| 2020 | 1,371 | 0 | 0 | 0 | 0 |
| 2021 | 1,477 | 0 | 0 | 0 | 0 |
| E1 合計 | 6,763 | 0 | 0 | 0 | 12 |

這 6,763 筆在處理日都有 RAW key；這裡是 key 覆蓋，不等同所有 RAW close 都有效。12 筆延至下一觀測的逐事件記錄：[event_assignment_deferred](../out/layer1_data_decision/event_assignment_deferred.csv)；含零分類及 E1 後事件：[event_assignment_counts](../out/layer1_data_decision/event_assignment_counts.csv)。逐年 observation-year 總和由程式斷言等於已驗收 CSV。

**定位：0 先出現在原始來源表；normalize、對齊、暖機、年度彙總都不是 2016 由有變零的原因。** `build_adj.py --start` 預設 2017-01-01，與表起點一致；但缺初次 run 參數／API 回應，不把預設值當作實際執行參數的證明。

### 2016 股票與價格覆蓋

這張原事件表的 2016 股票集合是空集合，故其對應股票／行情交集皆為 0，不能拿空集合得到「覆蓋完整」。獨立查看同 revision 官方 `ex_right_dividend` ledger：

| 來源 | 事件列 | 不重複股票 | 事件股票有 adjusted 年內觀測（事件列數） | 有 RAW 年內觀測（事件列數） | 當日 adjusted key | 當日 RAW key |
|---|---:|---:|---:|---:|---:|---:|
| TPEx exDailyQ | 510 | 491 | 489 | 510 | 479 | 499 |
| TWSE TWT49U | 734 | 711 | 734 | 734 | 720 | 720 |
| 合計 | 1,244 | 1,202 | 1,223 | 1,244 | 1,199 | 1,219 |

來源與結果：[official_2016_coverage](../out/layer1_data_decision/official_2016_coverage.csv)。這些官方事件**沒有偷偷注入 online 或正式資料**；用途是證明缺的是特定事件表，不是整個來源完全沒有 2016 公司行動。

2016 價格 key：adjusted 455,344 列／1,930 檔；RAW 436,698 列／1,851 檔；兩邊 key 交集 430,230、只有 adjusted 25,114、只有 RAW 6,468。key 有但 close=null 與無 key 不同，因此本表不取代舊報告的 `raw_close_missing=32,918`。暖機及各年 key 覆蓋在 [price_key_coverage](../out/layer1_data_decision/price_key_coverage.csv)。

## 3. 不一致個案與原因分級

| 個案 | RAW | stored adjusted | round-once | sequential | 已證實／仍未知 |
|---|---:|---:|---:|---:|---|
| 1216 2016-01-04 | 53.90 | 34.690681 | 35.7748 | 35.7747 | 缺 2016-08-04 cash 事件的診斷可解釋此價差。 |
| 1216 2016-08-03 | 66.00 | 42.478385 | 43.8058 | 43.8059 | 同一漏失事件；補診斷倍率後殘差約 1.92e−9。 |
| 1216 2016-08-04 | 63.50 | 42.146523 | 42.1465 | 42.1465 | 除息當日不再乘其自身倍率；一致對照。 |
| 1216 2017-01-03 | 53.30 | 35.376530 | 35.3765 | 35.3766 | 兩算法皆在 0.0001 內；2018～2021 首日也一致。 |
| 2330 2016-01-04 | 139.50 | 104.959000 | 109.3905 | 109.3907 | 缺 2016 cash 可解釋部分；補診斷倍率後仍差 −0.3035714，未全解。 |
| 2330 2017-01-03 | 183.00 | 143.087700 | 143.5015 | 143.5016 | 後續增量回寫有直接祖先版本證據，但回寫前仍有殘差。 |
| 1101 2017-01-03 | 35.15 | 17.035679 | 17.0314 | 17.0313 | 差 0.004279／0.004379；大於同事件表 rounding 上界，原因未定。 |
| 1101 2019-01-02 | 35.50 | 20.396696 | 20.3967 | 20.3967 | 一致對照；不能由此放行其他年度。 |
| 2317 2017-01-03 | 84.30 | 69.448305 | 57.2412 | 57.2411 | 額外案例：ledger 有 2018 減資，但經濟倍率不完整，未把殘差全部歸因減資；不在研究母體。 |

其餘固定年度案例完整保留於 CSV，不挑選最好解釋的年份替代全樣本。

### 1216：可數值解釋的缺漏

`fundamentals/dividend.parquet` 有 cash=2、除息日 2016-08-04、公告 2016-07-20 17:17:55；官方 ledger 同股同日有除息事件。前日 RAW close=66，診斷 multiplier=(66−2)/66=64/66。

2016-01-04 的 RAW×既有 future_factor×64/66 = 34.6906810818，stored=34.690681，殘差 −8.18e−8。除息前日也吻合，除息當日本來就吻合。這提供**該案例缺漏事件的數值解釋**；不是新增正式事件，不是證明所有缺漏，也不是把重建值稱為歷史真值。見 [missing_cash_diagnostic](../out/layer1_data_decision/missing_cash_diagnostic.csv)。

### 2330：事件表未含的後續來源回寫

祖先 commit [906f257](https://github.com/bibobo2266/minervini_picks/commit/906f257d73d6515212d922aea4b6afd31b736129)（09-15）中 2017-01-03 adjusted=143.509499；[e108105](https://github.com/bibobo2266/minervini_picks/commit/e10810504c07f92dcbcca957d0156b21233db358)（09-16）變成 143.087700，與 frozen 值相同。變動 −0.421799；事件表卻只到 08-28。

同 revision dividend details 有 2330 在 2026-09-16 生效、cash=7.000001、公告 09-01 16:39:47。`daily_update_adj` 會將當日 API 事件套用至歷史價，**沒有把事件 append 回 dividend_events.parquet**。這證明 frozen 表不能完整重現所有後續更新。祖先價格：[historical_snapshot_trace](../out/layer1_data_decision/historical_snapshot_trace.csv)。

尚未取得該次 API 的 before/after 原始回應，故不把上述比值反推成已驗證 event ratio；且回寫前價與 round-once 仍差 +0.007999。這部分仍可能涉及初始回補算法／事件定義或其他修訂，未分解。

### 1101 與其他 CA

1101/2017-01-03 的同一事件表共有 10 個後續事件。假設相同 RAW、相同 ratio、只差逐次 round(4)，誤差上界遞推 `B_next=abs(r)*B+0.00005`，得到約 0.000398；再加最終單次 rounding 0.00005 也小於觀察差異。因此**僅靠這兩種 rounding 的差別無法解釋**；不是證明所有可能的供應商 rounding／算法版本都排除。2018 首日也仍有殘差，2019～2021 首日一致。需要當初 FinMind adjusted 算法／版本及修訂紀錄才能進一步定因。

2317/2018-10-26 官方減資列有 prev=68.10、ref=82.62，但 cash/share_multiplier 缺失，不能由 ref/prev 猜經濟轉換；P2-060 已排除此檔。這是「其他 CA 依賴存在，但貢獻未證實」，不是本次新排除。

### 跨來源建置差異

固定版本來源程式：

- [build_adj.py](https://github.com/bibobo2266/minervini_picks/blob/fb8b042b46dc38838d103544ca17da10286c7bfe/scripts/build_adj.py)：讀 `data/prices.parquet`，不是此次比較的 `data/raw/prices_raw_YYYY.parquet`；after/before 連乘，再 round(4)。不能假定兩個 RAW 輸入曾經完全一致。
- [backfill_adj.py](https://github.com/bibobo2266/minervini_picks/blob/fb8b042b46dc38838d103544ca17da10286c7bfe/scripts/backfill_adj.py)：直接下載 `TaiwanStockPriceAdj`，不由本地事件表重建，保留供應商值；[檔案歷史](../out/layer1_data_decision/source_history.json) 包含 `ede6598` 與 `fc0b8e8` 回補提交。
- [daily_update_adj.py](https://github.com/bibobo2266/minervini_picks/blob/fb8b042b46dc38838d103544ca17da10286c7bfe/scripts/daily_update_adj.py)：當日事件按股聚合倍率、round(4) 更新所有已存歷史，再 append RAW；補缺模式跳過重新調整。這與離線按 event.date 處理的語意，僅在既存列皆早於此次生效日等前提下相符。

因此比較同時跨了事件覆蓋、初始價格來源、供應商 adjusted 算法、後續回寫與精度。**確定存在多路徑，不等於已證明每一個殘差由哪條路徑造成。** 樣本日期均以同股同交易日 exact-key 對齊、無 duplicate；未觀察到這些樣本是日期錯配，但不外推全市場。

## 4. 證據結論邊界

已證實：2016 事件原表缺列；部分 missing cash 可解釋樣本；2017 歷史價遭事件表截止日之後的更新；有一致普通股對照；有無法用既定 rounding 解釋的殘差。

未證實：全市場每筆差異成因、所有公司行動的完備 known-time、整個 E1 EOD 截止契約、供應商歷史算法／修訂、2016 的 1,463 個 N60 翻轉逐筆歸因。

本查核足以提出 [最小資料修正方案](PIT_FEATURE_LAYER1_DATA_DECISION.md)，不足以解除任何策略 gate。所有重建均為 frozen-source 診斷，不是歷史當時真值。


## 5. 本地驗證與交付

- `python -m pytest -q tests/test_ca_adjustment_invariance_audit.py tests/test_feature_panel_integration.py`：**42 passed**。
- 小範圍 probe 完成：來源 blob/SHA256、normalize 數量、事件年度對帳、28 列逐事件重建終值、普通股母體資格斷言均通過。
- 已驗收四份數值 CSV 的 SHA256 全部維持原 manifest；未改寫歷史結果檔。
- 靜態語法、文件相對連結、`git diff --check` 通過。只更新交接／報告、查核腳本與新證據，未修改 workflow 或策略 gate。
