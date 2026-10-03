# Owner Priority Queue

## 目前狀態

更新時間：2026-10-03T23:21:00Z
做完：第 5 項 causal RAW v2 程式與 B 合成資料／Parquet hydration 驗證已完成
結果：workflow 37161408316：327 passed；程式驗證通過，真實 E1 artifact 未產出
卡住：RAW／Trading_money／tradability 歷史 cutoff 證據與完整 CA 事件覆蓋仍未通過；資料 gate 維持 BLOCKED，待 Astra 驗收
下一項：baseline_60d_breakout_v1 本地準備（原授權 D；不跑正式回測）

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

### 1. 路徑診斷層 + 重算五份 sweep

狀態：DONE

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

### 2. 建立待測總表

狀態：DONE

建立 `docs/TEST_INVENTORY.md` 作為後續掃描、特徵建置與出場開發的唯一待測來源，並在 `docs/INDEX.md` 加連結。本項只盤點與對帳，不執行 sweep、不新增策略、不改既有報告。

要求：
- 每列九欄：id / origin / definition / purpose / code / tests / reports / gap / depends_on。
- 每列另記六階段：來源資料 / PIT / 元件 / 模擬器串接 / 正式掃描 / 報告，各自只能是有／無／不適用。
- 每列另記掃描層級 CANDIDATE / FULL_TRADE / NONE，以及原始方法涵蓋度 FULL / SIMPLIFIED / NA。
- L1 17 列與表外項目、L2、L3、出場表依 owner 規格完整列入；repo 清單外既有元件補列並明示。
- L2、L3 的概念數／元件數／參數版本數分開統計，不得混用。

---

### 已完成前置：2883B 來源端最小開口修復（P2-063 選項 A），解鎖 P2-062

狀態：DONE

只放寬估值 / 執行來源路徑，使帶字母後綴的上市證券可進 RAW 與 tradability；研究候選母體保持四位純數字普通股。

完成後重跑 P2-062 並通過既定硬檢。

---

### 3. VCP Round 1 三段收縮完整進出場參數掃描

狀態：DONE

版本：`vcp_round1_three_segment_v1`

本輪只執行 E1（2016-01-04～2021-12-31），以 owner 指定的 TRANSLATED 三段區間、連續兩次收縮定義，掃描 108 組進場參數；固定出場為 Wilder ATR21 × 2.5 移動出場與 D21 跌破，先觸發者收盤確認、次一合法共同交易日 RAW 開盤成交。

要求：
- 使用既有 PIT、RAW 執行、CA/terminal lifecycle 與 all_liquid/P2-060 母體；不查 E2/E3 效果。
- 108 格完整保留；base_len 25/35/50/65 × last_contraction 0.08/0.12/0.15 × dry_up 0.50/0.65/0.80 × breakout_vol 1.5/2.0/2.5。
- 訊號日前 20 日均額門檻 TWD 20,000,000 放入 params/config，不寫死。
- 無跨股票資金競爭；同 config/股票同時最多一筆；持倉中重複訊號忽略並計數。
- 追價上限為 pivot 的進場日 RAW 等值 × 1.05；不可合法成交則記原因，不延後追入。
- 成本：買/賣手續費各 0.1425%、賣出證交稅 0.3%、買賣各 0.1% 不利滑價；共用成本模型只扣一次。
- 不殘留固定停損、max-hold 或其他出場；期末未平倉不強平、不讀 E2 補完。
- 交付 out/vcp_sweep_round1.csv、trades、open_positions、overlap、單軸 4 圖、兩軸 6 圖、繁中研究報告與 run manifest。
- low_n = TRUE 當 n_closed < 100，且不得進入高原圖顏色標度。
- 若既有已驗證虛無/亂數對照不能依凍結契約直接重用，明示「亂數對照／預期偽陽性數尚未完成，本輪無推論性存活名單」。
- 不因結果修改本輪定義；不自動開始第二輪、不 promote、不解鎖 OOS。

---

### 4. VCP Round 2 前置修正與 Round 1 診斷

狀態：DONE

本項不得修改或重跑 round1。Round1 既有 config、程式行為與 out/ 產物視為凍結結果。

要求：
- 只針對既有 round1 產物建立 amplitude_3 診斷，輸出新檔 `out/vcp_round1_amp3_diagnostic.csv`，不得覆蓋既有 round1 檔案。
- 新增 round2 版本與 `min_amplitude_3` 參數，round2 預設 0.01；round1 行為維持等價 0.0。
- 測試 amplitude_3=0 在 round2 不觸發、round1 仍觸發。
- round2 summary schema 預備 exit_atr_count / exit_ma21_count / exit_both_count / exit_open_count，總和必須等於 n_closed+n_open。
- 實作封口：round1 既有 27 筆 terminal lifecycle 平倉不屬 ATR / MA21 / BOTH / OPEN；round2 另列 exit_terminal_count，五類合計才與 n_closed+n_open 完全一致，不得把 terminal 偽裝成策略出場或未平倉。
- round2 trades schema 補 entry_prior_avg_amount_twd / entry_day_amount_twd 與缺值原因；不補零。
- 本項只做診斷、程式與測試；不得啟動 round2 掃描。

---

### 5. [IN_PROGRESS] PIT 安全特徵矩陣第一層

狀態：IN_PROGRESS

三項稽核修復已驗收；真實資料適用性尚未全面通過。

eac32af 查核交付已通過，最小 v2 方向已核定，維持完整 E1 及 2015 暖機。causal RAW v2 核心與合成 hydration／E1 邊界驗收已實作；正式真實 E1 artifact 因歷史 cutoff 與完整 CA 證據不足而維持 BLOCKED，等待 Astra 驗收。不得據此解除策略 gate 或啟動第 6 項。

範圍：

- 族一：技術面；
- 族四：市場結構。

後續再做：

- 族二：籌碼；
- 族三：基本面；
- 族五：旗標。

---

### 6. ML 層

狀態：BLOCKED_BY_5

第 5 項完成後才定義。現在不要動。

---

### 7. 報告合理性自我警示層

狀態：PENDING

第 1 項完成後再定義閾值。現在不要動。
