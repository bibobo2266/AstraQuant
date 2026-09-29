# Owner Priority Queue

狀態：ACTIVE

## 常駐回報規則

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
- E3 breakout regression-only 豁免：PENDING
- #44 三份全期報告標記與接觸補登：PENDING


### 0. [BLOCKED] 時期治理與接觸清冊

狀態：BLOCKED

建立 strategy-version-specific E1/E2/E3/E4 時期治理、附加式接觸清冊與程式層效果查詢閘門。E3 效果查詢一律阻擋；E1 預設；E2 僅顯式啟用且強制標籤；路徑窗口與完整交易使用不同跨界 purge 規則。

產出：
- docs/EPOCH_GOVERNANCE.md
- docs/CONTACT_REGISTRY.md
- 程式層閘門與測試

卡住：硬性紀律要求任何改動後驗證 breakout final NAV 51,696,620.30；該既有回歸路徑延伸至 2026-07-07，但 E3 自 2026-07-01 起禁止任何策略效果／路徑統計。需 owner 明示固定 regression-only 斷言是否為例外，或本項是否免做該回歸驗證。

---

### 1. 候選級 outcome 去均值修正 + 重算五份 sweep

狀態：DONE

現行 outcome 為 N 日絕對報酬，Bollinger / VCP / Anchor-UP / Anchor-DOWN / RSI 五份報告皆為 100% 組合正期望值，量到的主要是市場漂移而非選股資訊。

改為：

```text
個股 N 日報酬 − 同一天同母體全體平均 N 日報酬
```

去均值母體：

- 當日 P2-060 共同支撐內；
- tradability 為 `observed_trade` 且 `valid_ohlc`；
- 當日有效標的少於 200 檔則該日排除。

Anchor-DOWN 空方 outcome 同樣先去均值，再反號。

五份報告需新舊並列，同時列出：

- 絕對期望值；
- 去均值期望值。

不得更動：

- 訊號定義；
- 參數網格；
- 候選母體；
- P2-060 排除名單。

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
