# AQ-EXP-MERGE-PREP-001 — E1 證據線八個 Draft PR 的合併前準備

task_id: AQ-EXP-MERGE-PREP-001 / revision 2
狀態：本輪**不合併任何 PR**，只做準備。由執行端產出，不自行驗收。

revision 2 的改動：revision 1 只涵蓋 #8／#9／#10／#11 四個 PR，並把它們當成一條線，
漏掉 runner 線的 #4／#5／#7 以及兩疊互不相依的 stack 結構；且其乾跑結論早於各分支的現行 head。
§1、§2 已整段汰換，§3 之後的結論經重新驗證後維持不變。

未改任何既有交付的內容、未改 manifest 本體、未改 producer、未改 queue、未改 workflow。
FORMAL_RESEARCH 維持無條件阻擋。私有逐列內容未進 repo。

參考點：`main` = `42a5324`。所有 head 與乾跑結論均以此為準；main 若再往前走，§2 需重跑確認。

## 1. 依賴圖與建議合併順序

> **revision 2 更正**：revision 1 把八個 PR 當成一條線處理，漏了 runner 線三支的
> stack 關係，也沒有涵蓋 #4／#5／#7。實際上是**兩疊互不相依的 stack**，可並行。
> 以下為以現行 head 重做的結果。

### 1.1 兩疊 stack 與現行 head

```
資料／證據線                                runner 線
main ← #8   sol4/aq-exp-data-001-r2         main ← #4  solb/baseline-60d-simulator-integration
       ↑ #10 solc/aq-exp-atr-001                   ↑ #5  solb/prepared-run-eligibility-evidence
       ↑ #11 solc/aq-exp-geom-001                        ↑ #7  solb/baseline-60d-exploration-runner-prep

main ← #9   claude/aq-exp-survivor-001      獨立
main ← #12  solc/aq-exp-merge-prep-001      獨立
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
| #12 | `8c30ca4a` | `main` |

#4／#5／#7 的 head 是合併前置①（把 main 併入 runner 線三支並重跑 CI）之後的新值，
不是 revision 1 當時的 `75a0867` / `c275f81` / `418154bf`。

### 1.2 建議順序

兩疊各自由深到淺，互不相依：

- **資料線**：`#10 → #11 → #8 → main`
- **runner 線**：`#7 → #5 → #4 → main`
- `#9`、`#12` 獨立，順序不拘

兩個必須先知道的副作用（兩疊都適用）：

- **先合深層會把淺層 PR 的 diff 撐大。** 例如 #10、#11 進 sol4 之後，#8 的 diff
  從 6 個檔變 12 個檔；#7 進 #5 之後，#5 的 diff 也會長大。按下最外層那一顆之前
  應重讀其最終 diff，不要照舊的審查印象按。
- **不要直接把深層 PR 合進 main。** #10／#11 的 commit 鏈含著 #8，#7 的含著 #5 與 #4；
  直接合會把上游連帶拖進 main 並跳過其審查狀態。

## 2. 衝突清單（以現行 head 重做，本機乾跑，未推、未合併）

全部用 `git merge --no-commit --no-ff` 乾跑後 `git merge --abort`，未推送。

### 2.1 兩兩乾跑

| 目標 ← 來源 | 結果 |
| --- | --- |
| `sol4`(#8) ← #10 | CLEAN |
| `sol4`(#8) ← #11 | CLEAN |
| `main` ← #8 | CLEAN |
| `solb/prepared-run`(#5) ← #7 | CLEAN |
| `solb/simulator`(#4) ← #5 | CLEAN |
| `main` ← #4 | CLEAN |
| `main` ← #9 | CLEAN |
| `main` ← #12 | CLEAN |

### 2.2 兩疊整串乾跑

- 資料線 `#10 → #11 → #8 → main`：**三步全 CLEAN**
- runner 線 `#7 → #5 → #4 → main`：**三步全 CLEAN**
- 再接 `#9`、`#12` 進 main：**CLEAN**

**八個 PR 全部併進同一棵樹後，零衝突檔案、零衝突行段。**
該樹上 `pytest -q` = **502 passed, 6 skipped**（6 skip 是需要私有逐列／固定 source 的
那幾支，缺輸入時明示 skip）；帶齊三層輸入跑 `scripts/merge_postcheck.py --strict`
= **PASS 48 / FAIL 0 / SKIP 0**。

### 2.3 被多個 PR 同時觸碰的檔案

| 檔案 | 被幾個 PR 碰 | 性質 |
| --- | --- | --- |
| `src/astraquant/portfolio/strategy_simulator.py` | 3（#4／#5／#7） | 同一 stack 上的先後修改，非並行衝突 |
| `tests/test_baseline_60d_simulator_integration.py` | 2（#4／#5） | 同上 |
| `src/astraquant/research/config_engine.py` | 2（#4／#5） | 同上 |
| `docs/BASELINE_60D_BREAKOUT_READINESS.md` | 2（#5／#7） | 同上 |
| `out/aq_exp_data_001_r2_manifest.json` | 2（#8／#10） | 同上（#10 的 merge-base 即 #8 的 head） |

**全部都是 stack 內的順序依賴，沒有任何一組是兩個獨立分支各改一份。**
兩疊之間零交集：資料線四個 PR 不碰 runner 線的 `src/` 檔，runner 線三個 PR 不碰
`out/aq_exp_data_001_*` 或 `scripts/survivorship_72_scan.py`。

唯一會變成真衝突的情境，是在合併前又有人往某疊的中間層推新 commit 去改上面那些檔案；
屆時應在該疊內部解、讓下游 rebase，不要在 main 側解。

### 2.4 合併前置①的結果（CI 重跑）

runner 線三支原本落後 main 22 個 commit，已依序 `main → #4 → #5 → #7` 併接，
每一步 CLEAN、每一步本機測試通過後才推，三支 CI `tests` 皆 **completed / success**
（#4 415 passed、#5 440 passed、#7 465 passed）。

附帶一項更正：發工時認為那 22 個 commit 裡的
`ci: guard source config sweeps` 與 `ci: guard observation sweeps` 改了 workflow、
使舊綠燈失效。查證下來**不成立**——main 上那兩個 commit（`fa63a51`、`053e83b`）是
**空 commit**；真正改動 `source_observation_sweeps.yml` / `source_config_sweep.yml`
的是 `c61b143` 與 `04ae230`，兩者早就在三支分支的歷史裡。三支與 main 之間唯一有差異的
workflow 是 `watchdog.yaml`（監看排程，非 CI 閘門），而真正的閘門 `tests.yml`
在這 22 個 commit 內完全沒被改。重跑仍照辦且全綠，但結論是「本來就有效，再確認一次」。

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

以下沒有一項因為這八個 PR 合併而完成。不要在合併紀錄裡把它們寫成已完成。

1. **runner 線只有合成 fixture。** #4／#5／#7 的 src 凍結已由 Owner 解除、三個 PR 皆已 ACCEPTED，
   但 runner 至今只跑過 deterministic synthetic fixture，沒有真實 parquet 整合驗收，
   也沒有真實 E1／E2／E3。合併它們不等於 runner 可以跑真實資料。
2. **共同日曆完整性缺陷未量化。** `REVISION_2` 列出的三項缺陷裡，ATR14 暖機門檻
   由 #10 算成 17、OHLC 幾何由 #11 算成 0，**日曆完整性那一項到現在還是 UNKNOWN**。
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
