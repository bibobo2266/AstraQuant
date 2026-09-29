# Owner Priority Queue

## 目前狀態

更新時間：2026-09-29T12:19:00Z
做完：執行中，工作流 36561805068
結果：目前 Run Anchor-down daily sweep
卡住：無
下一項：1

狀態：ACTIVE

## 常駐回報規則

本檔開頭的「目前狀態」區塊是 owner 與審查端讀取的唯一狀態來源。每完成一項、卡住、或狀態改變時，必須立即更新該區塊，格式固定：

```text
目前狀態
更新時間：<UTC 時間>
做完：<一句話>
結果：<關鍵數字，沒有就寫無>
卡住：<一句話，沒有就寫無>
下一項：<queue 第幾項>
```

即使沒有在對話中回報，也必須寫進本檔；工作流執行中時，狀態寫「執行中，工作流 <編號>」。

本檔由 owner 指定執行順序，優先於任何自行判斷。每次接到新任務前必須先讀本檔。一次只做一項；完成並回報後，才可開始下一項；不得跳項。每項完成、卡住或狀態改變後，必須回寫本檔。

所有回報使用台灣繁體中文，最多四行，格式固定：

```text
做完：<一句話>
結果：<關鍵數字，沒有就寫「無」>
卡住：<一句話，沒有就寫「無」>
下一項：<queue 第幾項>
```

附加規則：

- 不列已完成事項的歷史清單；commit 已可查。
- 不複述任務內容或限制條件。
- 不解釋未完成原因，除非是卡住原因。
- 工作流仍在跑時，只寫「執行中，工作流 <編號>」，不描述步驟。
- 數字直接給，不加形容詞。

## 執行佇列

## 進入第 0 項前置處理

- 1.5：DONE
- legacy 重複報告清理：DONE；保留目前腳本命名規則的 `SOURCE_STRATEGY_PERFORMANCE_REPORT_{TRADES,OPEN_LOTS}.csv`
- E3 breakout regression-only 豁免：DONE
- #44 三份全期報告標記與接觸補登：DONE


### 0. 時期治理與接觸清冊

狀態：DONE

建立 strategy-version-specific E1/E2/E3/E4 時期治理、附加式接觸清冊與程式層效果查詢閘門。E3 效果查詢一律阻擋；E1 預設；E2 僅顯式啟用且強制標籤；路徑窗口與完整交易使用不同跨界 purge 規則。

產出：
- docs/EPOCH_GOVERNANCE.md
- docs/CONTACT_REGISTRY.md
- 程式層閘門與測試

E3 豁免：EX-001 已由 owner 裁定；僅允許 breakout 長窗 final NAV 51,696,620.30 的布林軟體回歸比對，限制詳見 docs/EPOCH_GOVERNANCE.md。

---

### 1. [NOW] 路徑診斷層 + 重算五份 sweep

狀態：NOW

建立候選級 5 / 10 / 20 交易日路徑診斷。entry_ref 為訊號日次一共同交易日 RAW 開盤價（CA 一致口徑）；次日無有效開盤價標 NO_VALID_ENTRY_REF，不延後、不略過。路徑值以一單位初始部位的 CA-aware 部位價值 V_t 計算，沿用既有 CA／終止生命週期語意。

要求：
- 多方與 Anchor-DOWN 空方依 owner 指定 MFE / MAE 定義。
- MFE / MAE 各自以當日 P2-060 共同支撐母體去均值。
- order_state 固定三態：MFE_FIRST / MAE_FIRST / SAME_DAY_UNKNOWN。
- 5 / 10 / 20 三窗口並列，不選最佳窗口。
- 依 EPOCH_GOVERNANCE：E1 預設、E2 顯式、E3 阻擋；各窗口獨立跨界 purge。
- 多承接證券日內極值無法可靠聚合時標 MULTI_LEG_INTRADAY_UNRESOLVED；其他不可可靠處理事件標原因，不得靜默刪除或補價。
- 漲跌停使用市場與日期實際適用限制價；無法取得則記限制價未知，不得用昨收固定乘數代替。
- 候選層不套用部位上限或資金限制。
- 重算 Bollinger / VCP / Anchor-UP / Anchor-DOWN / RSI 五份；不得更動訊號、參數網格、母體或 P2-060 排除名單。

---
### 1.5 通用 config 報告指令

狀態：DONE

`scripts/source_strategy_performance_report.py` 目前仍自行組建舊 breakout 訊號集。改為接受任一 config，輸出同一份 FIFO 交易表 + 基準比較，不需為每條訊號寫客製腳本。

要求：

- 基準比較模組自動掛上，不需手動接。
- 既有 breakout 路徑結果必須維持 final NAV `51,696,620.30`。

---

### 2. 2883B 來源端最小開口修復（P2-063 選項 A），解鎖 P2-062

狀態：DONE

只放寬估值 / 執行來源路徑，使帶字母後綴的上市證券可進 RAW 與 tradability；研究候選母體保持四位純數字普通股。

完成後重跑 P2-062 並通過既定硬檢。

---

### 3. PIT 安全特徵矩陣第一層

狀態：PENDING_AFTER_1_5

範圍：

- 族一：技術面；
- 族四：市場結構。

後續再做：

- 族二：籌碼；
- 族三：基本面；
- 族五：旗標。

---

### 4. ML 層

狀態：BLOCKED_BY_3

第 3 項完成後才定義。現在不要動。

---

### 5. 報告合理性自我警示層

狀態：BLOCKED_BY_1

第 1 項完成後再定義閾值。現在不要動。
