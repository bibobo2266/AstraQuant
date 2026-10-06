# AQ-EXP-DATA-001 — E1 可實測資料覆蓋率

狀態：**REVIEW_READY / NOT A DATA-GATE PASS / NO STRATEGY EFFECTS**

固定口徑：

- E1：2016-01-04～2021-12-31；暖機自 2015-01-01。
- source revision：`fb8b042b46dc38838d103544ca17da10286c7bfe`。
- Astra contract revision：`1e184908f17c7e612fad636f30b61071ed916a56`。
- existing private evidence revision：`abdc6e18f13710f830000bc946e63ca1c151dcfe`。
- CA reconciliation：program `9914525fe7db92a69fc08360823fb679518ee0b8`；run `37171913233`。
- coverage workflow：`37213806645`。
- private delivery commit：`8226478d0bcb5dc1ae66c08701535f4f1d579a35`。
- 原母體：既有 `all_liquid` 每日 membership；本任務沒有新增 ticker／year 排除。
- 不重查 142 筆 CA 候選、不購買、不做外部搜尋、不計算策略報酬。

## 1. 三類問題

本報告同時保留獨立 A/B/C flags；需要互斥年度比例時使用固定優先序 **C > B > A**。

- **A — 數值可用、歷史證據不足**：當前 frozen 數值／經濟處理可供限制性探索，但 historical as-published version、publication time 或 revision lineage 不足。RAW OHLC 與 Trading_money 的歷史版本 identity 目前仍為 UNKNOWN，因此原母體所有 stock-day 都有 A flag。
- **B — 數值／經濟內容仍可能錯**：CA 金額、share conversion、event completeness 或已知 stale value 仍可能改變應使用的策略價格座標。
- **C — 本身不可計算**：既有 missing/suspended common-session row 或暖機不足，使該 feature 當日不能依 frozen contract 計算。

A 不等於 VERIFIED。B 不等於已證明錯；只有已有正向證據的部分才列為 known affected。C 是依目前資料本身可直接確定的不可計算狀態。

## 2. 原母體與年度覆蓋

全 E1 原母體為 **458,315 stock-days / 1,394 unique stocks**。

| 年 | 原母體 stock-days | unique stocks | 四項數值皆可算 | 可算率 | 限制性探索可用 | 探索率 | B 問題率 | C 問題率 | known affected | supported unaffected | indeterminate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2016 | 68,570 | 920 | 60,489 | 88.21% | 37,972 | 55.38% | 36.46% | 11.79% | 8,081 | 0 | 60,489 |
| 2017 | 74,351 | 996 | 67,168 | 90.34% | 43,177 | 58.07% | 35.93% | 9.66% | 7,183 | 0 | 67,168 |
| 2018 | 76,937 | 1,020 | 71,361 | 92.75% | 45,455 | 59.08% | 36.30% | 7.25% | 5,576 | 0 | 71,361 |
| 2019 | 75,794 | 984 | 72,099 | 95.12% | 44,601 | 58.85% | 37.28% | 4.88% | 3,695 | 0 | 72,099 |
| 2020 | 78,081 | 974 | 75,113 | 96.20% | 46,637 | 59.73% | 37.57% | 3.80% | 2,968 | 0 | 75,113 |
| 2021 | 84,582 | 1,021 | 81,872 | 96.80% | 54,438 | 64.36% | 33.66% | 3.20% | 2,809 | 0 | 81,773 |
| **E1** | **458,315** | **1,394** | **428,102** | **93.41%** | **272,280** | **59.41%** | **36.16%** | **6.59%** | **30,312** | **0** | **428,003** |

`限制性探索可用` 的定義是：四項數值可計算，而且沒有 B exposure；A 可以存在，但必須標記
`ELIGIBLE_WITH_PIT_EVIDENCE_INCOMPLETE`。這不是 formal PIT eligibility。

## 3. MA120 / N60 / ATR14 / LOW20 的實際依賴傳播

不是只標事件當日。依 frozen contract：

- **MA120**：current + prior 119 common-session rows；CA event 可影響其後最多 119 個輸出 observations。
- **N60**：first-cross 需要 current + prior 61 common-session closes；CA event 可影響其後最多 61 個輸出 observations。
- **ATR14**：SMA14 true range；在 valid-observed-bar sequence 上至少要 15 個 valid bars 才有 14 個 TR，event-day TR 可留在 14 個 ATR outputs。
- **LOW20**：前 20 個 valid observed closes、不含 current；CA event 可影響後續 20 個 valid-bar outputs。

ATR14 / LOW20 這裡只量化資料依賴覆蓋，不代表其正式 exit evaluator／simulator wiring 已獲批准。

| feature | 數值可算 | 可算率 | 限制性探索可用 | 探索率 | B exposure | B 率 | C exposure | C 率 | known affected | supported unaffected | indeterminate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MA120 | 428,102 | 93.41% | 272,280 | 59.41% | 165,709 | 36.16% | 30,213 | 6.59% | 30,312 | 0 | 428,003 |
| N60 | 438,344 | 95.64% | 354,271 | 77.30% | 87,572 | 19.11% | 19,971 | 4.36% | 20,029 | 0 | 438,286 |
| ATR14 | 457,916 | 99.91% | 437,419 | 95.44% | 20,524 | 4.48% | 399 | 0.09% | 410 | 0 | 457,905 |
| LOW20 | 457,813 | 99.89% | 428,783 | 93.56% | 29,060 | 6.34% | 502 | 0.11% | 519 | 0 | 457,796 |

MA120 是四項交集的限制因子，所以「四項皆可算」與 baseline 限制性探索 stock-day 數和 MA120 相同；這是計數結果，不是選擇較好 feature。

## 4. 三態證據判定

- **KNOWN_AFFECTED**：C 類確定不可計算，或已有證據支持「當時使用值確實錯／時序錯」的 B exposure。
- **SUPPORTED_UNAFFECTED**：必須有正向證據同時清掉 A/B/C；「沒找到問題」不算。現階段全 E1 為 **0**。
- **INDETERMINATE**：仍有 A 或 unresolved B。全 E1 為 **428,003 stock-days（93.39%）**。

因此不能把 93.41% 的數值可算率寫成 93.41% PIT 通過率。

## 5. 主要 B/C 來源

MA120 的 B exposure 主要來自既有 CA `INSUFFICIENT_EVIDENCE` event groups 沿 119-row window 傳播；其次是 evidence-backed missing cash events 與 normalizer scope gaps。N60、ATR14、LOW20 使用各自較短的 dependency range，所以 B exposure 依序下降。

C 方面，MA120/N60 保留 common-session missing/suspension rows 為 null，不壓縮時間；ATR14/LOW20 依 baseline spec 使用 valid observed-bar sequence，因此 suspension 不當作一個有效 bar，而主要 C 原因變成上市／有效交易歷史不足的 warmup。

既有 386 筆 non-dividend share-event blocker 並未由本任務重新刪除股票。原 `all_liquid` contract 已包含 frozen P2-060 exclusion；本任務沿用該既有 exclusion，不額外修改母體。

## 6. RAW source 組成不是資料通過證明

原 all_liquid stock-days 包含 TWSE/TPEx official rows、targeted TPEx repair rows，以及 FinMind gap-fill rows。這些數值可用於本次 coverage 計數；但 historical version/correction lineage 未封口，所以統一保留 A，而不是把目前 frozen row 當作「當年版本已證明」。

## 7. Machine-readable private delivery

Private repo only：

`bibobo2266/tradestation`  
commit `8226478d0bcb5dc1ae66c08701535f4f1d579a35`  
path `private/astraquant/aq_exp_data_001_e1_coverage_v1/`

Sol 4.1B 可直接使用：

- `aq_exp_data_001_eligibility_reason_rows.parquet` — 逐 all_liquid stock-day、逐 feature A/B/C、三態證據、B event IDs/reasons、C reason、限制性探索資格。
- `aq_exp_data_001_yearly_coverage.csv`
- `aq_exp_data_001_feature_coverage.csv`
- `aq_exp_data_001_reason_counts.csv`
- `aq_exp_data_001_raw_source_breakdown.csv`
- `aq_exp_data_001_summary.json`

Row-level Parquet Git blob：`bf226d682470f7e83f7175afe6fff6e0167ef476`；size 2,718,958 bytes。私有逐列資料未進 public repo。

## 8. 結論

**可以支持有限制的 E1 探索實測，但只限明確標記 PIT evidence incomplete 的資料診斷／研究開發用途。**

具體可用範圍：**272,280 / 458,315 = 59.41%** 的原 all_liquid stock-days，在四項數值皆可算且沒有目前已知／可能改變經濟值的 B exposure；這些 rows 仍全部有 A，因此不能稱 VERIFIED 或 clean PIT。

不支持：

- 正式 E1 feature artifact；
- formal research gate；
- 策略報酬／有效性結論；
- OOS unlock；
- 將 UNKNOWN 改成 VERIFIED。

本任務只回答「目前 frozen data 在什麼限制下可做探索性實測」，沒有解除 queue item 5。
