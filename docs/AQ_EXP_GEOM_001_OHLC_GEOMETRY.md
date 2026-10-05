# AQ-EXP-GEOM-001 — OHLC 幾何驗證缺陷的實際受影響筆數

task_id: AQ-EXP-GEOM-001 / revision 1
狀態：實際數字已算出並通過重建核對；本文件由執行端產出，**不自行驗收**。

本輪只量化，未改 producer、未改凍結交付、未重新產生 coverage v1。
FORMAL_RESEARCH 維持無條件阻擋，未跑策略效果、未讀 E2/E3、未掃參數，
未碰 solb 分支、CA accounting／normalizer／queue／workflow。

## 1. 結論

原母體 458,315 列裡，幾何違反列數是 **0**。不是範圍、不是上界。

四個 feature 的聚合**全部不動**，四項交集維持 **428,102**，變動量 0。
因為沒有任何一列變動，所以不存在「哪個 feature 主導」的問題。

這**不等於** PR #8 的缺陷不成立。缺陷在程式層是真的：producer 的有效性判定是

```
observed_trade AND valid_ohlc AND close > 0 AND Trading_money notna
```

裡面沒有任何一條檢查 `high ≥ low`、`high ≥ max(open, close)`、`low ≤ min(open, close)`。
它的幾何安全**全部**來自上游 `tradability.valid_ohlc` 這一個欄位。
本輪量到的是：在這份固定來源上，那一個欄位剛好擋得乾淨，所以漏接數為 0。
缺陷的性質是 **LATENT_CONDITIONAL_ON_UPSTREAM_FLAG**，不是已實現的錯誤。

## 2. 掃描範圍與判定

掃全 panel 2,427,931 列（2015 暖機～2021 期末，含未進母體的列），不是只掃母體，
否則無法分辨「沒有壞資料」與「壞資料被上游擋掉」。

| 幾何違反型態 | 全 panel | 原母體內 |
| --- | --- | --- |
| high < low | **0** | 0 |
| high < max(open, close) | 49,368 | 0 |
| low > min(open, close) | 30,628 | 0 |
| 任一 OHLC ≤ 0 | 22,739 | 0 |
| 任一 OHLC 為空 | 39,579 | 0 |
| **任一違反（去重）** | **119,601** | **0** |

涉及 862 檔。年度分佈（全 panel）：2015 15,137、2016 20,668、2017 18,303、
2018 19,562、2019 17,175、2020 15,828、2021 12,928。

關鍵一行：**119,601 列裡，`valid_ohlc = True` 的有 0 列。**
上游攔截率 100%，其中 112,605 列標 `INVALID_OHLC`，6,996 列標
`NO_TRADE_ROW_WITHIN_ACTIVE_SPAN`。所以沒有任何一列能通過 producer 的有效性判定，
更不會進入母體。

另外值得記一筆：PR #8 舉的例子是 `high 90 < low 99`。這種型態在全 panel
2,427,931 列裡**一列都沒有**。該行表格是合成契約測試（來源 flag 被強制設為 True），
不是從真實資料觀察到的個案。

## 3. 違反列目前的 evidence_state 與 dominant_problem_class

不適用。沒有任何違反列落在母體 458,315 列內，因此沒有列帶著 evidence_state
或 dominant_problem_class 可供回報。這一欄不是「查不到」，是「依定義為空集合」。

## 4. 若採用「幾何違反即判定該列不可用」

受影響列數 0，因此：

| feature | numeric_computable | limited | issue_C | 變動 |
| --- | --- | --- | --- | --- |
| MA120 | 428,102 | 272,280 | 30,213 | 0 |
| N60 | 438,344 | 354,271 | 19,971 | 0 |
| ATR14 | 457,916 | 437,419 | 399 | 0 |
| LOW20 | 457,813 | 428,783 | 502 | 0 |

四項交集 428,102 → 428,102，delta = 0。

（ATR14 欄位是 coverage v1 的原值。AQ-EXP-ATR-001 另外把 ATR14 的暖機門檻修正為 14 根，
那輪的 +17 與本輪無關，兩者不相加也不衝突。）

## 5. 真正該記下來的風險：這個 0 是誰撐住的

0 是結果，不是保證。producer 沒有自己的幾何閘門，整條防線只有上游一個 flag。
量一下那個 flag 擋著多少東西：

**若 `valid_ohlc` 退化成恆為 True，會有 48,518 列、290 檔**
（幾何壞、但 `observed_trade`、`close > 0`、`close ≥ 10`、`Trading_money` 皆通過，
且落在 E1 期間）直接進入候選篩選。那是單點失效的爆炸半徑，不是目前的錯誤。

對應的解法有兩個，建議兩個都做：

1. **在 producer 的有效性判定裡加一條獨立幾何斷言**，不要只依賴上游 flag。
   成本是幾行條件式，換掉一個單點失效。
2. **加一支回歸測試**把「攔截率 100%」釘住（本輪已附
   `tests/test_aq_exp_geom_001.py` 的真實資料測試），
   上游來源換版時若有幾何壞列通過 `valid_ohlc`，測試會紅。

本輪不改 producer，上面兩條是給 owner 的建議，不是已執行項目。

## 6. 參考數字

母體內 `high == low` 的零振幅 bar 有 **453 列**。這**不是**幾何違反——
台股漲跌停鎖死是合法型態。記在這裡只因為它會讓當日 true range = 0，
日後若有人量 ATR 分母或波動率時會撞到，先標出來免得被誤判成壞資料。

## 7. 與 PR #8 的關係

**不矛盾，因此沒有停下來等裁示。**
PR #8 主張的是「producer 缺少幾何驗證，這種列會被當 valid」——該主張在程式層成立，
本輪未推翻。本輪回答的是另一個問題：「這個前提在固定來源上實際發生幾次」，答案是 0 次。
缺陷存在與曝光為零可以同時為真，本文件沒有改動 PR #8 的任何結論。

## 8. 可重現

公開環境（只驗聚合檔自洽）：

```bash
python -m pytest tests/test_aq_exp_geom_001.py -q
```

可讀 source 與私有交付者，額外跑真實掃描（否則該項明示 skip）：

```bash
AQ_SOURCE_ROOT=/path/to/minervini_picks/data \
AQ_PRODUCER=/path/to/scripts/astraquant_aq_exp_data_001.py \
  python -m pytest tests/test_aq_exp_geom_001.py -q
```

私有逐列內容未複製進本 repo，本文件與 JSON 只保留聚合。
