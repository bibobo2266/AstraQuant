# 歷史 CA 資料最小切片取得與驗證決策卡

task_id: `AQ-COORD-S4-002`  
revision: 1  
status: REVIEW CANDIDATE / DATA GATE UNCHANGED  
evidence basis: existing public aggregate `3a0fd1517907040ca613bdb22b3e4cf1e4325c77:out/ca_historical_evidence_path_diagnostic_v1.json` plus already-persisted private path-diagnostic / CA conflict evidence only.

本卡只決定「若下一步要取得 TPEx 歷史資料，最小要哪一段、拿到後驗什麼、什麼情況立刻停止」。本輪沒有新增外部查詢、沒有重查 142 筆、沒有重算 reconciliation、沒有購買或聯繫供應商，也沒有更動 normalizer / gate / formal E1 artifact / strategy effects。

## 決策摘要

**先取候選切片 A；切片 A 未證明資料是 original daily as-produced snapshot 時立即停止，不進切片 B、不 bulk。**

### 候選切片 A — 最小且先做

- 產品：TPEx eShop「上櫃股票基本資料」。
- 檔案：`STKANOU.TXT` + `T48`。
- 最小訂購單位：既有保存產品資料顯示「歷史月份可訂購」；因此本卡以 **1 個歷史月** 為最小驗證單位。
- 需涵蓋年月：**2016-09**。
- 選取理由：既有 private positive control 已知同一事件在同一天先有初始現金值、晚間又有修訂值，且修訂發生在下一交易決策 cutoff 前。這一個月可同時壓測：
  1. 事件在 cutoff 前是否已出現在原始日檔；
  2. 同日修訂是否留下可辨識的版本／更正關係；
  3. `T48` 的日終產出能否與公告／修訂狀態區分，避免把「日檔產製時間」誤當 issuer known_at。
- 已知取得資訊（僅重用既有保存證據）：歷史月份可訂購；`T48` 保存資料顯示每日產製時間 21:20 UTC+8；當時保存的產品頁列價為 **NT$1,000/月**。今晚未重新查價；稅費、帳號要求、授權／再散布限制為 **UNKNOWN**。
- 這個切片成功仍只代表該產品具備可驗證 PIT/version 能力，不代表 142 筆自動通過。

### 候選切片 B — 只在 A 通過原始快照測試後才考慮

- 產品：同上，仍用 `STKANOU.TXT` + `T48`，不先換產品。
- 最小訂購單位：歷史月。
- 需涵蓋年月：**2017-06 + 2017-07**。
- 選取理由：既有 private conflict evidence 已知一個跨月版本鏈：先發布原值、事件日後再發布修訂值。兩個月可測：
  1. first appearance 前一日／當日是否可由 daily snapshots 夾出 first-known interval；
  2. 事件日前的版本是否保留；
  3. 事件日後的修訂是否出現在後續 snapshot；
  4. 同一 event key 是否能把前後版本可靠連起來，而不是現在重建成單一 final state。
- 已知價格仍只有保存頁面的 **NT$1,000/月**；本卡不推定實際兩月結帳金額或授權條件。
- 若 A 已顯示歷史檔是 current-state reconstruction、缺 as-produced 日期／版本資訊，B 不執行。

## 收到檔案後固定驗證欄位

每個切片都只驗固定欄位／證據維度，不因結果不好而換標準：

1. **event key**
   - security identifier；
   - ex-right/ex-dividend effective date；
   - 若產品提供 stable row/event ID、公告序號或更正序號，原樣保留。
2. **經濟內容**
   - cash per share；
   - stock/free-allotment raw field；
   - 各欄位 source-specific unit；
   - 不使用未證實的跨來源 `/10` 或 `/1000` 通用換算。
3. **有效日**
   - ex-right / ex-dividend date；
   - 若 cash 與 stock 有不同 effective date，分開保留。
4. **檔案 as-produced 身分**
   - daily file 的原始日期／產製日期時間；
   - 原始檔名／member name；
   - 收件後另計 SHA256 只做 chain-of-custody，不把下載時間當歷史 publication time。
5. **first-known interval**
   - 前一個 as-produced snapshot 不含該事件；
   - 第一個 as-produced snapshot 含該事件；
   - first-known 只記為兩個 snapshot 邊界形成的 interval；只有其最晚可能時間嚴格早於 decision cutoff 才能支持 PIT available。
6. **revision relation**
   - 前版值、後版值；
   - correction/revision/cancel flag（若有）；
   - stable event key 是否保持；
   - 前後版是分別存在於歷史 snapshots，還是購買時已被回填成同一 final state。

## 固定驗證步驟

1. 先驗檔案層：確認交付是否包含逐日 as-produced 檔，而不是只給一份現在重建的歷史結果。
2. 用切片 A 的既有 control event：
   - 讀事件日前／同日／次日相關 snapshots；
   - 對照既有已知初始值與修訂值；
   - 不使用下載時間補 known_at。
3. 若 A 證明 original snapshots 存在但同日 revision 未被保存：
   - 記錄「可做日級 first appearance、不能重建同日 revision lineage」；
   - 再判斷這是否足以解 142 補事件候選的 timing blocker；不能就停止。
4. 只有 A 通過 original snapshot / field semantics，才考慮 B：
   - 用跨月案例確認 first appearance、事件日版本與後續 revision 可各自在不同 daily snapshots 中重建。
5. 對每個已驗事件輸出四個彼此獨立結論：
   - amount/component；
   - effective date；
   - historical availability interval；
   - revision lineage。
   不把其中一項 PASS 推成其他項 PASS。

## 成功／失敗判準與能縮小的 blocker

### PASS-A：可繼續評估 142 timing blocker

至少同時成立：
- 購得檔案可證明是當年逐日 as-produced snapshot，而非現在重建；
- 事件 key、cash／stock raw value 與單位可解讀；
- 可由「前一檔不存在、下一檔存在」建立 first-known interval；
- interval 最晚時間可與研究 decision cutoff 做嚴格比較；
- 修訂不會無痕回填到早期 snapshots。

可縮小：142 筆「金額足夠但歷史 cutoff 時間不足」中的 **historical first-known / version-state** blocker。  
不保證一次解 142；仍需逐事件存在於產品涵蓋與欄位可判定範圍內。

### PASS-B：可重建跨日 revision state

在 PASS-A 之外，跨月案例的前版與後版能在各自 as-produced snapshot 中分開定位，且可用同一 event key 連結。

可縮小：revision lineage blocker 的「是否可由官方歷史日檔重建」部分。

### STOP / FAIL

遇到任一項就停止，不追加大量搜尋、不回 MOPS、不補全 142：

- 歷史訂單實際提供的是現在重建的 current-state 檔，而非原始逐日 snapshot；
- as-produced 日期／檔案日無法確認；
- 事件 key 或 cash/stock raw field／單位不足以判定；
- 修訂會 retroactively overwrite 早期 snapshot，且無 revision marker／版本序號；
- 只有 `T48` 日終產製時間，卻沒有能證 first appearance 的前後 snapshot；
- license / use restriction 不允許本研究必要的保存或驗證用途；
- 供應商無法回答 historical snapshot 是否原樣保存。

停止結論：相關候選維持 `UNKNOWN / fail-closed`；不得縮短期間、刪 ticker 或降低 PIT 證據標準。

## 沒有被本卡解決的問題

即使 A/B 都 PASS，也**不等於第 5 項通過**，且不處理：
- RAW / Trading_money 歷史版本與 correction identity；
- 386 筆非股利 share-changing events；
- 股票股利未驗證 unit / par-value 轉換；
- 正式 E1 feature artifact；
- 任何策略效果、E2/E3 效果。

## 已保存產品選項與為何不先買第二產品

既有 evidence index 另列 TPEx eShop「上櫃股票統計資料」的 `STKPRERGHT.TXT` / `STKRGHTS.TXT`，保存頁面列價 NT$10,000/月，且既有診斷已指出 preview/calculation state 本身不等於 issuer publication known_at。

因此本卡**不把它列為第一輪購買切片**。只有 `STKANOU/T48` 小切片已證明原始日檔能力、但缺特定 preview/calculation 欄位，而供應商又能明確說明第二產品補得到該欄位／版本時，才另請 Owner 決策；今晚不擴大。

## 取得方式／授權資訊狀態

重用既有保存證據：
- TPEx eShop 上櫃股票基本資料產品頁：`https://eshop.tpex.org.tw/zh/product/detail/BCDDCDFD315841EC011ED99B91DD528E`
- 保存資訊：歷史月份可訂購；`STKANOU.TXT` 起始 2010-07-19；`T48` 起始 2011-11-30；保存頁列價 NT$1,000/月。
- 未重查、未購買、未申請帳號。
- 帳號資格、付款細節、研究內部保存／再散布授權：**UNKNOWN**。

可詢問供應商、但本 task 不代寄的必要問題只有：
1. 歷史月份下載是否為「當日原始 as-produced 檔案」逐日保存，還是下單時由 current DB 重建？
2. correction/revision 是否會 retroactively 改寫過去日檔？是否有 stable event ID、revision/cancel flag 或版本序號？
3. 月份訂單是否包含每個交易／產製日的原始檔名與 production date/time？
4. `STKANOU.TXT` 與 `T48` 對 cash、stock/free-allotment、effective date 的欄位定義與單位是什麼？
5. 研究用途下是否允許內部保存、雜湊與逐日版本比較？若有禁止再散布限制，具體範圍為何？

## 唯一需要 Owner 的下一個決策

若要往前走，**只需決定是否授權取得／提供候選切片 A：TPEx eShop 上櫃股票基本資料 2016-09 一個歷史月，檔案 `STKANOU.TXT` + `T48`；前提是先取得上面 5 個必要問題的明確答案。**

沒有這個授權或產品無法證明 original as-produced snapshots，就維持現況，不 bulk、不重查 142。
