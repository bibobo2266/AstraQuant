# AQ-EXP-CAL-002 — 外部台股交易日曆與 104 個 UNKNOWN 的逐日判定

task_id: AQ-EXP-CAL-002 / revision 1
狀態：104 天全數判定完成；本文件由執行端產出，**不自行驗收**。

**量尺**：資料層診斷。不報勝率／賠率／每筆期望值，不得用於論斷任何元件有效或無效。

未改 producer、未改凍結交付、未重新產生 coverage v1、未改 queue／workflow。
FORMAL_RESEARCH 維持無條件阻擋。

## 1. 結論

AQ-EXP-CAL-001 留下的 **104 個 UNKNOWN 平日，全數判定為「非交易日」。
真缺日 0 天，剩餘 UNKNOWN 0 天。**

因此四項交集 **428,102 → 428,102，增量 0**。這是**實際值不是估計**：
真缺日集合為空，CAL-001 建立的敏感度路徑輸入為空集合，不需要插入任何
null session 列，四項交集依定義不動。

逐日判定表：`out/aq_exp_cal_002_adjudication.csv`（104 列）。

**但主要依據是第三方來源，不是權威來源。** 原因與殘留風險見 §2、§5。

## 2. 來源階梯：實際走過的結果

發工建議的順序是 TWSE → TPEx → 第三方。實際可取得性如下。

### Tier 1-a：TWSE 開(休)市日期表 —— **不可用於 E1**

```
https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=csv&queryYear=<民國年>
```

實測帶 `queryYear=108`（2019），回傳的卻是**民國 115 年（2026）**的表
——`queryYear` 參數已失效，只供當年度。data.gov.tw 資料集 11761 的說明也寫明
「提供最新一版資料，通常每年 12 月前會提供隔年度資料」。

**這條路涵蓋不到 2016–2021，發工建議的首選來源在本輪不成立。**

### Tier 1-b：TWSE 每日市場成交資訊 FMTQIK —— 可用，但只做了抽查

```
https://www.twse.com.tw/en/exchangeReport/FMTQIK?response=csv&date=<YYYYMMDD>
```

歷史月份取得得到，且這是**交易所自身的開市紀錄**，權威性沒有問題。
缺點是一次只回一個月，全期 2016-01～2021-12 要 **72 次請求**，本輪沒有逐月取盡。

用它做了單月權威抽查（§4）。

### Tier 2：TPEx —— 未取用

tier 1-b 已足以做權威抽查、tier 3 已足以做全期逐日判定，未再往下取。
這是本輪的取捨，不是 TPEx 不可用。

### Tier 3：exchange_calendars XTAI —— **第三方，非權威**

`exchange_calendars==4.13.2`（PyPI，Apache-2.0），`get_calendar('XTAI')`
涵蓋 2015-06 至 2021-12 全期。全期逐日判定用的是這個。

**依發工要求，明確標示為非權威來源。**

## 3. 與 panel 的對帳

| | 值 |
| --- | --- |
| panel E1 session | 1,468 |
| XTAI E1 session | 1,460 |
| **XTAI 有、panel 無（＝真缺日候選）** | **0** |
| panel 有、XTAI 無 | 8 |

那 8 天是 `2016-01-30`、`2016-06-04`、`2016-09-10`、`2017-02-18`、
`2017-06-03`、`2017-09-30`、`2018-03-31`、`2018-12-22` —— **全部是週六**，
台股的補行交易日，XTAI 沒有收錄。

扣掉這 8 個週六後，**平日的 session 集合兩邊完全相同**（1,468 − 8 = 1,460）。
104 個 UNKNOWN 全是平日，落在這個完全相同的範圍內，所以逐日判定有依據。

**這裡沒有同源循環**：判定依據是 XTAI 這份獨立清單，不是拿 panel 推日曆再去驗 panel。
panel 只作為被比對的一方。

## 4. 權威抽查：TWSE FMTQIK 2021-09

挑一個含 UNKNOWN 日的月份直接向交易所要紀錄。

- TWSE 權威交易日：9/1、2、3、6、7、8、9、10、13、14、15、16、17、22、23、24、27、28、29、30，共 **20 天**
- panel 該月 session：**20 天**，**兩者完全相同**
- 該月 UNKNOWN 平日：`2021-09-20`、`2021-09-21`（中秋連假）
- 兩天**都不在** TWSE 的交易日清單內 → 判定為非交易日，與 XTAI 一致

權威來源、第三方來源、panel 三方在這個月互相吻合。

## 5. 殘留風險：這個 0 有多硬

要講清楚，不要讓它被當成已經關閉。

**XTAI 對 session 是低報，不是高報。** 證據就是那 8 個補行交易週六——
panel 有、XTAI 沒有。既然它會漏，那麼「XTAI 有而 panel 無 = 0」就是
**支持性證據，不是決定性證明**：如果兩邊剛好漏掉同一天，這個比對看不出來。

降低了多少：CAL-001 時 104 天全是 UNKNOWN，且單一真缺日就動四項交集 −34,254。
現在 104 天有獨立來源逐日判定為非交易日，並在一個月上拿到權威確認。
風險從「完全未知」降到「第三方認定 + 單月權威抽查」，**但沒有歸零**。

**要徹底關掉它需要什麼**：逐月取盡 TWSE FMTQIK 2016-01 至 2021-12，共 72 次請求，
用交易所自身紀錄取代第三方清單。那是純粹的取數工作，沒有技術障礙，只是本輪沒做。
做完之後這 104 天的依據欄會從 `third-party` 變成 `authoritative`，
而結論預期不變（單月抽查已經吻合）。

## 6. 這輪缺什麼

- **缺全期權威紀錄**（見 §5）。在它補上之前，`aq_exp_cal_002_adjudication.csv`
  的 `source` 欄誠實寫著 NON-AUTHORITATIVE，只有 2021-09 那兩列帶權威確認。
- **缺 TPEx 端對照**。panel 含上櫃股，而本輪的權威抽查只用了 TWSE。
  兩個市場的開休市日實務上一致，但本輪沒有獨立驗證這件事。
- **真實資料接上後會先動的數字**：本輪結論是四項交集不動（428,102）。
  若日後逐月取盡 FMTQIK 發現任何一天是真缺日，會先動的是
  `INPUT_MISSING_OR_SUSPENDED_IN_120_COMMON_ROWS` 的列數（目前 28,451），
  再連動四項交集，量級參考 CAL-001 的 −34,254／天。ATR14 與 LOW20 不受影響。

## 7. 與既有結論的關係

**不矛盾。** CAL-001 的結論是「受影響 0 列，條件是那 104 天全不是真的 session」。
本輪把那個條件從未驗證變成「已由獨立來源逐日判定 + 單月權威抽查」。
CAL-001 的任何數字都沒有被改動。三項缺陷仍各自獨立不相加：
ATR14 暖機 17 筆、OHLC 幾何 0 列、日曆完整性 0 列。

## 8. 可重現

公開環境（只驗判定表與聚合檔自洽，不需網路）：

```bash
python -m pytest tests/test_aq_exp_cal_002.py -q
```

有外部日曆套件時，額外跑真實比對（否則明示 skip）：

```bash
pip install exchange_calendars==4.13.2
python -m pytest tests/test_aq_exp_cal_002.py -q
```

同時需要固定 source 時，再跑與 panel 的全量對帳：

```bash
AQ_SOURCE_ROOT=/path/to/minervini_picks/data \
AQ_PRODUCER=/path/to/scripts/astraquant_aq_exp_data_001.py \
  python -m pytest tests/test_aq_exp_cal_002.py -q
```

私有逐列內容未複製進本 repo。
