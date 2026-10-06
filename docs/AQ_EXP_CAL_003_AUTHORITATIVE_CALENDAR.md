# AQ-EXP-CAL-003 — 以權威紀錄取代第三方日曆

task_id: AQ-EXP-CAL-003 / revision 1
狀態：**取數機制已交付並通過測試，但尚未執行** —— 執行端無法派送 workflow。
本文件由執行端產出，不自行驗收。

**量尺**：資料層診斷。不報勝率／賠率／每筆期望值，不得用於論斷任何元件有效或無效。

未改 producer、未改凍結交付、未重新產生 coverage v1、未改 queue、未碰 TPEx。
FORMAL_RESEARCH 維持無條件阻擋。

## 1. 本輪的實際狀態

**72 個月的權威紀錄一筆都還沒取到。** 不是結果是 0，是還沒跑。
CAL-002 的 104 天判定**維持第三方來源不變**，沒有任何一天被升級。

原因是取數管道，不是方法：

| 管道 | 結果 |
| --- | --- |
| 執行端容器直連 twse.com.tw | **403**，對外網路只允許套件來源，不含交易所網域 |
| 一般網頁抓取工具 | **把帶不同 `date` 參數的同一端點塌回同一個月**：請求 `date=20160101` 與 `date=20180301`，回傳的都是 2021/09 那一份，`destination_url` 顯示 `date=20210910`。取不到第二個月份 |
| GitHub Actions runner | 網路沒有上述限制，**可行** |

所以本輪把取數做成 workflow。腳本與 workflow 已推上分支、已通過測試，
但執行端的 token **只有 Contents 與 Pull requests，沒有 `actions=write`**，
派送時回 403（`x-accepted-github-permissions: actions=write`）。
**需要有人手動按一次 Run workflow，或把 Actions 權限加給執行端。**

## 2. 交付了什麼

### `scripts/fetch_twse_fmtqik.py`

逐月請求 `https://www.twse.com.tw/en/exchangeReport/FMTQIK?response=csv&date=YYYYMM01`，
2016-01 至 2021-12 共 72 個月，預設間隔 4 秒循序取得。

- 每月原始回應原樣留存在 `out/twse_fmtqik_raw/FMTQIK_<YYYYMM>.csv`，供審查端覆核（驗收標準 1）
- 非 200、空內容、或疑似阻擋回應（HTML 挑戰頁、rate limit 字樣）→ 該月標 **UNKNOWN**
- **連續兩次被擋即停止整條路徑**，不繞過、不換同義查詢重試（取數紀律）
- 已取得的月份照常留存，未取得的逐月列在 `months_unknown_list`

### `scripts/adjudicate_calendar_authoritative.py`

用取回的權威 session 集合重新判定 104 天，並與 panel 全期對帳。全部 fail-closed：

| 情況 | 判定 | source 欄 |
| --- | --- | --- |
| 該日所屬月份取數非 OK | 維持 CAL-002 原判定 | **維持 third-party**，標 `UNKNOWN_MONTH` |
| 月份 OK、該日不在權威 session 內 | `NON_TRADING_DAY` | 升級為 **authoritative** |
| 月份 OK、該日在權威 session 內 | `REAL_MISSING_SESSION` | 升級為 **authoritative** |

**不以第三方補位。** 取不到的月份，那些日子就停在 third-party，逐日列出（驗收標準 2）。

雙向對帳只在權威覆蓋到的月份內進行（驗收標準 3）——
取不到的月份排除在對帳窗之外，否則會把「沒取到」誤算成「真缺日」。
兩個方向都輸出：`authoritative_only_dates`（真缺日）、`panel_only_dates`
（預期為 8 個補行交易週六，含 `panel_only_all_saturdays` 與
`panel_only_matches_expected_makeup_saturdays` 兩個旗標，數目不符時由報告解釋）。

**真缺日出現時 delta 留空。** 不就地估計，要走 CAL-001 的敏感度路徑逐日插入
null session 列重算（驗收標準 4）。artifact 裡會寫明單日參考量級 −34,254，
但那是參考值不是結果。

### `.github/workflows/twse_fmtqik_calendar.yml`

一次 dispatch 把取數、判定、commit 串完，產出直接進分支。
`workflow_dispatch` 可調 `start`／`end`／`interval`。

### `out/aq_exp_cal_003_panel_sessions.csv`

panel 的 E1 session 日期 1,468 筆，供對帳用。
**只有 date 一欄**，沒有 stock_id、沒有價格——是聚合，不是逐列內容。
這裡 panel 是「被權威檢查的一方」，不是判定依據，沒有同源循環。

## 3. 範圍為什麼必須是全期 72 個月

發工已經點明，這裡記錄原因以免日後被縮水：CAL-002 的盲點是
「panel 與第三方日曆同時漏掉同一天」。那種日子**依定義不在 104 天內**
（它在兩邊都不是 session，所以不會被標成 UNKNOWN 平日）。
只取含 UNKNOWN 日的月份，看不出這種日子。

全期對帳才會讓 `authoritative_only_dates` 把它抓出來。

## 4. 測試

`tests/test_aq_exp_cal_003.py`，**9 passed**，全部用合成 fixture，
不需網路、不需私有資料，CI 可跑。

涵蓋驗收標準 5 的兩條路徑：

- **權威紀錄齊備**：72 個月全 OK → 104 天全升級為 authoritative、
  `still_third_party = 0`、真缺日 0 時 delta 為實際 0
- **部分月份缺漏**：指定月份標 UNKNOWN → 該月的日子維持 third-party 並逐日列出、
  不被第三方補位、且該月被排除在對帳窗外

另有真缺日路徑（delta 必須留空不得估計）、取數腳本的月份範圍與阻擋判定、
以及 panel session 檔確實只有日期欄的斷言。

## 5. 這輪缺什麼

- **缺那一次 dispatch。** 這是唯一的阻塞點，不是技術問題。
- **缺 TPEx 端。** 本輪依發工明確不處理，上櫃端對照另案。
- **真實資料接上後會先動的數字**：若全期取盡後 `authoritative_only_dates` 非空，
  先動的是 `INPUT_MISSING_OR_SUSPENDED_IN_120_COMMON_ROWS` 的列數（目前 28,451），
  再連動四項交集（目前 428,102），量級參考 CAL-001 的 −34,254／天；
  ATR14 與 LOW20 不受影響。若為空，CAL-002 的結論從「第三方認定」升級為
  「交易所自身紀錄認定」，數字不變但依據強度變了。

## 6. 執行方式

有 Actions 權限的人按一次即可：

```
Actions → "TWSE FMTQIK calendar (AQ-EXP-CAL-003)" → Run workflow
  branch: solc/aq-exp-cal-003
  start: 201601   end: 202112   interval: 4
```

約 72 次請求 × 4 秒間隔，含判定與 commit 約 6–8 分鐘。
結果會自動 commit 回同一分支，`out/twse_fmtqik_raw/` 留下每月原始回應。

本機要驗腳本（不含取數）：

```bash
python -m pytest tests/test_aq_exp_cal_003.py -q
```
