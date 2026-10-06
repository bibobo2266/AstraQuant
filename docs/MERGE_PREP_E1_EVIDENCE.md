# AQ-EXP-MERGE-PREP-001 — E1 證據線十二個 Draft PR 的合併前準備

task_id: AQ-EXP-MERGE-PREP-001 / revision 3
狀態：本輪**不合併任何 PR**，只做準備。由執行端產出，不自行驗收。

revision 3 的改動：revision 2 只涵蓋 #4～#12 共八個 PR，不含 #13／#14／#15／#16，
其 `502 passed` 也不包含它們。本版以十二個 PR 的現行 head 重做乾跑，
並補上 CAL-003 的覆蓋範圍限制（§5 第 2 條）。§1、§2 整段汰換，§3 之後重新驗證後不變。

未改任何既有交付的內容、未改 manifest 本體、未改 producer、未改 queue。
FORMAL_RESEARCH 維持無條件阻擋。私有逐列內容未進 repo。

參考點：`main` = `6b60b05`。所有 head 與乾跑結論均以此為準；main 若再往前走，§2 需重跑確認。

## 1. 依賴圖與建議合併順序

### 1.1 四疊 stack 與現行 head

```
資料／證據線                                 倖存者線
main ← #8   sol4/aq-exp-data-001-r2          main ← #9  claude/aq-exp-survivor-001
       ↑ #10 solc/aq-exp-atr-001                    ↑ #16 solc/aq-exp-survivor-002
       ↑ #11 solc/aq-exp-geom-001
       ↑ #13 solc/aq-exp-cal-001             runner 線
            ↑ #14 solc/aq-exp-cal-002        main ← #4  solb/baseline-60d-simulator-integration
                 ↑ #15 solc/aq-exp-cal-003          ↑ #5  solb/prepared-run-eligibility-evidence
                                                         ↑ #7  solb/baseline-60d-exploration-runner-prep
main ← #12  solc/aq-exp-merge-prep-001  獨立
```

| PR | head（現行） | base |
| --- | --- | --- |
| #4 | `4d69eca9` | `main` |
| #5 | `aee7387a` | `solb/baseline-60d-simulator-integration` |
| #7 | `7bab63fb` | `solb/prepared-run-eligibility-evidence` |
| #8 | `25266f8a` | `main` |
| #9 | `05bfd378` | `main` |
| #10 | `bfbafa31` | `sol4/aq-exp-data-001-r2` |
| #11 | `2ccc65ed` | `sol4/aq-exp-data-001-r2` |
| #12 | `49d038bd` | `main` |
| #13 | `bb2fb943` | `sol4/aq-exp-data-001-r2` |
| #14 | `9f3b5979` | `solc/aq-exp-cal-001` |
| #15 | `773d4709` | `solc/aq-exp-cal-002` |
| #16 | `7e58989d` | `claude/aq-exp-survivor-001` |

### 1.2 建議順序

四疊各自由深到淺，互不相依：

- **資料線**：`#10 → #11 → #15 → #14 → #13 → #8 → main`
  （#13／#14／#15 是一條線性鏈；#10 與 #11 與 #13 同層，三者都掛在 #8 上）
- **倖存者線**：`#16 → #9 → main`
- **runner 線**：`#7 → #5 → #4 → main`
- `#12` 獨立

兩個必須先知道的副作用（四疊都適用）：

- **先合深層會把淺層 PR 的 diff 撐大。** #10／#11／#13／#14／#15 全進 sol4 之後，
  #8 的 diff 會從 6 個檔長到 20 餘個。按下最外層那一顆之前應重讀其最終 diff。
- **不要直接把深層 PR 合進 main。** 它們的 commit 鏈含著上游，直接合會把上游
  連帶拖進 main 並跳過其審查狀態。

## 2. 衝突清單（以十二個 PR 的現行 head 重做）

全部用 `git merge --no-commit --no-ff` 乾跑後 `git merge --abort`，未推送、未合併。

### 2.1 兩兩乾跑

| 目標 ← 來源 | 結果 |
| --- | --- |
| `solc/aq-exp-cal-002`(#14) ← #15 | CLEAN |
| `solc/aq-exp-cal-001`(#13) ← #14 | CLEAN |
| `sol4`(#8) ← #13 / ← #10 / ← #11 | CLEAN / CLEAN / CLEAN |
| `main` ← #8 | CLEAN |
| `claude/aq-exp-survivor-001`(#9) ← #16 | CLEAN |
| `main` ← #9 | CLEAN |
| `solb/prepared-run`(#5) ← #7 | CLEAN |
| `solb/simulator`(#4) ← #5 | CLEAN |
| `main` ← #4 | CLEAN |
| `main` ← #12 | CLEAN |

### 2.2 四疊整串乾跑

- 資料線 `#13 → #14 → #15 → #10 → #11` 疊進 #8：**五步全 CLEAN**
- 倖存者線 `#16 → #9`：**CLEAN**
- runner 線 `#7 → #5 → #4`：**CLEAN**
- 四疊再加 `#12` 全部併進 main：**四步全 CLEAN**

**十二個 PR 併進同一棵樹後，零衝突檔案、零衝突行段。**
該樹上 `pytest -q` = **539 passed, 9 skipped**（9 skip 是需要私有逐列／固定 source／
外部日曆套件的那幾支，缺輸入時明示 skip）；帶齊三層輸入跑
`scripts/merge_postcheck.py --strict` = **PASS 48 / FAIL 0 / SKIP 0**。

revision 2 的 `502 passed` 不含 #13～#16，已作廢，合併輪不得引用。

### 2.3 被多個 PR 同時觸碰的檔案

| 檔案 | 被幾個 PR 碰 | 性質 |
| --- | --- | --- |
| `src/astraquant/portfolio/strategy_simulator.py` | 3（#4／#5／#7） | 同一 stack 的先後修改 |
| `tests/test_baseline_60d_simulator_integration.py` | 2（#4／#5） | 同上 |
| `src/astraquant/research/config_engine.py` | 2（#4／#5） | 同上 |
| `docs/BASELINE_60D_BREAKOUT_READINESS.md` | 2（#5／#7） | 同上 |
| `out/aq_exp_data_001_r2_manifest.json` | 2（#8／#10） | 同上 |

**全部是 stack 內的順序依賴，沒有任何一組是兩個獨立分支各改一份。**
新增的 #13／#14／#15／#16 沒有與任何其他 PR 共用檔案 —— 它們各自只新增自己的
docs／out／tests，#15 另有 `scripts/` 與一支 workflow。四疊之間零交集。

### 2.4 CAL-003 的 workflow：已改為可落地 main 的形式

合併前置第 2 點已完成，並在最終合併樹上複驗：

- `on.push` 與 sentinel 路徑 `out/.cal003_run_token` **已刪除**，檔案不存在於樹上
- 只保留 `workflow_dispatch`
- 檔頭已註明**單次執行為 72 次對外請求**（2016-01～2021-12，每月一次，預設間隔 4 秒，
  整趟約 6–8 分鐘），並寫明請勿排程、請勿反覆觸發
- 檔頭同時載明更正後的取數紀律（單次阻擋標 UNKNOWN 不重試、連續兩次或累計三次停整條端點、
  被擋單位補取須 Owner 裁定）

## 3. period_end 定稿方案（只提方案，本輪不執行）

### 3.1 事實

- `out/aq_exp_data_001_r2_manifest.json` 的 `denominator.period_end` = `2021-12-31`
- 凍結母體實際最後一列 = `2021-12-30`
- 差一日的原因：2021-12-31 當日沒有通過門檻的列，不是資料缺漏

### 3.2 影響面實測

`2021-12-31` 不是 manifest 的筆誤，而是 **E1 epoch 的定義值**，散佈在：

- `docs/` 19 個檔案
- `out/` 8 個 artifact
- 測試至少 4 處，含 `tests/test_epoch_governance.py`（兩處直接寫
  `period_end=date(2021, 12, 31)`）、`tests/test_causal_raw_v2_integration.py`、
  `tests/test_contact_registry.py`
- 固定於 commit `8226478d` 的私有交付 summary 本身也帶 `2021-12-31`，**而且改不了**

### 3.3 方案 A（建議）：保留 manifest，用註記說明差異

manifest 宣告的是 **epoch 邊界**，`2021-12-30` 是**對資料的觀察**。兩者語意不同，
不是同一個欄位的兩個候選值，所以不該用「改掉其中一個」來處理。

A 又分兩段，建議先做 A1、A2 視需要再說：

- **A1（零成本，合併後即成立）**：PR #9 的 `docs/SURVIVORSHIP_72_DELISTED.md` §3 已明寫差異，
  `out/survivorship_e1_universe_contact.json` 也同時輸出 `manifest_period_end` 與
  `e1_end_observed` 兩個欄位。`scripts/merge_postcheck.py` 的 L1 層把這兩個值都釘住。
  **合併 #9 之後這件事就已經有文字與機器兩層紀錄，不需要再動任何檔案。**
- **A2（可選，需另開 PR）**：在 manifest 的 `denominator` 裡增加一個純描述性欄位，
  例如 `last_observed_row_date: "2021-12-30"` 與一行 note。這是新增欄位、不改既有值，
  不影響任何現有斷言。但它會動到一份已被 #8 審查過的檔案，所以必須獨立成 PR 走審查，
  不要塞進這次合併。

### 3.4 方案 B（不建議）：把 manifest 改成 2021-12-30

需要同時處理的事：

1. `tests/test_epoch_governance.py` 的兩處硬編碼要改，等於動到 epoch 治理層
2. 19 個 docs 與 8 個 out artifact 的 E1 期間敘述會與 manifest 不一致
3. 固定於 `8226478d` 的私有交付無法修改，manifest 會與它所描述的那份交付對不上
4. `docs/CONTACT_REGISTRY.md` 等既有登錄的覆蓋期間要連帶重登

成本遠大於收益，而且它解決的是一個不存在的問題——manifest 沒有寫錯，
只是沒有同時記錄「觀察到的最後一列」。**建議不要採用。**

### 3.5 對已凍結交付與既有測試的影響彙總

| 方案 | 改既有值 | 動測試 | 與 `8226478d` 一致 | 合併這四個 PR 需要先做 |
| --- | --- | --- | --- | --- |
| A1 | 否 | 否 | 是 | 否（合併 #9 即生效） |
| A2 | 否（只新增欄位） | 否 | 是 | 否（可事後另開 PR） |
| B | 是 | 是，含 epoch 治理 | **否** | 是，且會擋住合併 |

## 4. 合併後必須仍為真的斷言

寫成可執行腳本：`scripts/merge_postcheck.py`。三層，缺輸入的層一律 SKIP 並寫明缺什麼，
不會把 SKIP 當成通過；有任何 FAIL 時回傳碼 1。

```bash
# 公開環境（無私有資料）
python3 scripts/merge_postcheck.py

# 合併完成後，Owner 的完整驗證
AQ_COVERAGE_ROWS=/path/aq_exp_data_001_eligibility_reason_rows.parquet \
AQ_SOURCE_ROOT=/path/minervini_picks/data \
AQ_PRODUCER=/path/scripts/astraquant_aq_exp_data_001.py \
  python3 scripts/merge_postcheck.py --strict
```

釘住的數字：

| 數字 | 意義 | 驗在哪一層 |
| --- | --- | --- |
| 458,315 | 原母體股票日 | L1 manifest / 三份 artifact 交叉、L2 逐列、L3 重建 |
| 1,394 | 原母體檔數 | L1、L2、L3 |
| 428,102 | 四項交集 numeric_computable | L1 三處、L2、L3（ATR 修正後仍須相同） |
| 399 | ATR14 C rows（v1） | L1 兩處交叉、L2 |
| 502 | LOW20 C rows（v1） | L1、L2 |
| 17 | ATR14 暖機修正受影響列 | L1 manifest + artifact、L3 重算 |
| 457,933 / 437,435 / 382 | ATR14 修正後 numeric / limited / issue_C | L1、L3 |
| 0 | 幾何違反落在母體內 | L1、L3 |
| 0 | 幾何壞列通過 `valid_ohlc` | L1、L3（這是上游攔截率的回歸閘門） |
| 410 | 倖存者 60 日窗（＝持有期）內股票日 | L1、L3 重跑 scan |
| 2021-12-31 / 2021-12-30 | manifest 宣告值 / 母體實際最後一列，兩者都要在 | L1 |

另外還釘了三條**跨檔一致性**，單看任何一份 artifact 都看不出來的那種：

- 三份 artifact 記錄的母體列數必須是同一個值
- #10 與 #11 各自記錄的「ATR14 v1 issue_C」必須相等（都是 399）
- #11 記錄的 MA120 `numeric_computable` 必須等於四項交集（MA120 是最窄的一項；
  哪天不等就表示 baseline 有問題）

在模擬合併樹（main ← #8 ← #10 ← #11 ← #9）上帶齊三層輸入實跑的結果：
**PASS 48 / FAIL 0 / SKIP 0**。在尚未合併的 main 上跑則是 SKIP 6、回傳碼 0，
加 `--strict` 會轉成 FAIL——這是刻意的，合併後若有人漏了某個 artifact 會被抓出來。

## 5. 合併後**仍未**解決的事項

以下沒有一項因為這十二個 PR 合併而完成。不要在合併紀錄裡把它們寫成已完成。

1. **runner 線只有合成 fixture。** #4／#5／#7 的 src 凍結已由 Owner 解除、三個 PR 皆已 ACCEPTED，
   但 runner 至今只跑過 deterministic synthetic fixture，沒有真實 parquet 整合驗收，
   也沒有真實 E1／E2／E3。合併它們不等於 runner 可以跑真實資料。
2. **日曆完整性的「真缺日 0」只覆蓋 71/72 個月。**
   REVISION_2 的三項缺陷都已量成確數：ATR14 暖機 17 筆（#10）、OHLC 幾何 0 列（#11）、
   共同日曆 0 列（#13），日曆的外部驗證再由 #14（第三方）與 #15（權威）補強。
   但 **#15 的權威對帳覆蓋的是 71 個月，不是 72**：`2017-10` 回傳阻擋頁、標 UNKNOWN，
   該月**未驗證**，`2017-10-04`／`2017-10-09`／`2017-10-10` 三天仍停在 **third-party**。
   合併紀錄若要寫「真缺日 0」，**必須同時寫明覆蓋 71/72、2017-10 未驗證、3 天仍為第三方**，
   不得簡化成全期已驗。2017-10 的補取依更正後的取數紀律須 Owner 裁定後另案發工。
3. **producer 仍沒有獨立的幾何閘門。** #11 量到的 0 是上游
   `tradability.valid_ohlc` 一個欄位撐住的，爆炸半徑 48,518 列 / 290 檔。
   建議的兩條解法（producer 加斷言、回歸測試釘住攔截率）只有後者隨 #11 進去，
   前者未執行。
4. **`tradability.valid_ohlc` 本身未獨立稽核。** #11 把它當給定值。
5. **B 依賴曝光與原母體未重跑。** #10 只動 ATR14 的 C／numeric／limited／evidence／reason，
   B 曝光 20,524 與母體 458,315 都是沿用 v1 的值。
6. **21 檔下市事件未查證。** `data/research/terminal_events.csv` 仍待補，
   PR #9 只做到接觸面清點，沒有做事件歸類。
7. **PR #9 §7 的縮減比例仍用 lifetime 口徑**（54%，8,465/15,797）。
   主口徑已改為 60 日窗，同一比較在 60 日窗下是 410/413 ≈ 99.3%。
   這不影響 §7 的建議方向（只查 21 檔），反而更支持它，但兩個口徑並存在同一份文件裡。
   PR #9 已用完兩輪修改額度，列為已知限制。
8. **A2 的 manifest 註記未執行**（見 §3.3），若要做需另開 PR。
9. **沒有任何策略效果數字。** FORMAL_RESEARCH 全程無條件阻擋，這四個 PR 全是
   資料可算性的 membership accounting，不含勝率、賠率、期望值或任何報酬口徑。

## 6. 本輪沒有做的事

- 沒有合併任何 PR，沒有推送任何既有分支
- 沒有修改任何既有交付的內容，沒有改 manifest 本體
- 沒有改 producer、queue、workflow
- 沒有碰凍結的 solb 分支與那兩個 src 檔
- 乾跑合併全部在本機進行並已 abort，遠端狀態未變
