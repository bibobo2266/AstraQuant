# PIT Feature Matrix Layer 1 — Decision-Time Availability & Integration

狀態：**IMPLEMENTED / AWAITING REVIEW**  
本文件是 OWNER_PRIORITY_QUEUE 第 5 項的剩餘驗收交接。它不宣告第 5 項審查通過，不計算任何策略效果。

## 1. 決策／送單時間契約

AstraQuant 日線策略的實際時序定義為：

1. T 日交易結束後，才允許使用 T 日 EOD 資料計算訊號。
2. 資料不要求在「T 日收盤瞬間」全部到齊；只要有證據支持它在送出 T+1 開盤意圖的截止前已可取得即可。
3. 現行 canonical simulator 的機器 gate 是
   `candidate.available_at < CanonicalStrategySimulator._session_start(T+1)`。
   `_session_start` 目前是 T+1 日期的 00:00 date-level abstraction；它比實際開盤時間更嚴格，但本項不修改 simulator。
4. feature integration 本身不猜測發布時間，也不把交易日期當 available_at。若未保留可追溯發布／接收時間戳，且沒有適用於 E1 的歷史官方發布規則或資料契約，狀態不得標 VERIFIED。
5. 未來若有來源證據證明資料在 00:00 之後但實際開盤前可得，現有 simulator 仍會阻擋；那屬 timing model 的後續工程，不在本項偷偷放寬。

可用性四態：

- `VERIFIED`：證據支持在目前可執行的 order-intent cutoff 前可用。
- `ASSUMPTION_ONLY`：只有研究假設，未獲來源證據支持。
- `UNKNOWN`：證據不足，不能判定。
- `UNAVAILABLE`：已有證據顯示目前 artifact／資料語意包含決策時點之後才知道的資訊，或已知截止前不可用。

策略研究預設只接受 `VERIFIED` 的必要輸入；其餘三態全部 fail closed，明確報錯，不刪列、不換欄位、不自動延遲一天。

## 2. 決定性新證據：adjusted history 會被未來公司行動回寫

Frozen source revision：`fb8b042b46dc38838d103544ca17da10286c7bfe`。

來源程式實查：

- `minervini_picks/scripts/daily_update_adj.py::apply_dividends`：
  當未來某日發生除權息時，會把該股票 **所有先前年度檔的歷史 OHLC** 乘上新的 after/before ratio，再寫回 parquet。
- `minervini_picks/scripts/build_adj.py::build_factors`：
  明確定義「某歷史日的 factor = 該日之後所有除權息事件的 ratio 連乘」。

因此 frozen `prices_adj_YYYY.parquet` 是「以後來已知公司行動回看調整」的研究座標；它適合做 ex-post 經濟連續性分析，但不能被宣稱為 T 日當時已知的 point-in-time 價格座標。

這比 review1 的「缺時間戳所以 UNKNOWN」更強：對現有 v1 artifact 而言，依賴 adjusted price 的策略決策輸入為 **UNAVAILABLE**。

## 3. close_to_ma120 必要依賴

`close_to_ma120 = adjusted_close / SMA120(adjusted_close) - 1`。

必要依賴與狀態：

| 依賴 | 狀態 | 證據／原因 |
|---|---|---|
| adjusted research price | **UNAVAILABLE** | 未來公司行動會回寫 T 以前歷史 OHLC |
| stock artifact row membership | **UNAVAILABLE** | layer1 先套 all_liquid/P2-060 再持久化；all_liquid 又使用 adjusted close >= 10，因此 row 是否存在也受 hindsight-adjusted close 影響 |
| P2-060 frozen governance input | VERIFIED（研究治理） | config 與 manifest 固定相同 exclusion SHA；它不是市場即時資料 |
| exact feature formula | VERIFIED（軟體／版本） | formula version 固定為 `pit_feature_matrix_layer1_v1`，base manifest 有逐 parquet SHA256 |
| historical order-cutoff availability | **UNAVAILABLE** | 上述 adjusted hindsight rewrite 已足以阻擋，不需靠猜發布時間 |

結論：現有 v1 的真實 `close_to_ma120` **不得進入要求 T→T+1 可交易 PIT 的策略研究**。這不是 COLUMN_THRESHOLD 的問題；數值語意仍然是 `>= 0.0`。

## 4. 其他來源依賴分組

不對 61 個版本重複查同一來源，按依賴群組分類：

| 群組 | 狀態 | 說明 |
|---|---|---|
| adjusted-price technical features | **UNAVAILABLE** | 同一 hindsight-adjusted price 問題 |
| persisted stock artifact membership | **UNAVAILABLE** | row presence 已受 adjusted close universe rule 影響，因此即使欄位本身只用 volume 也不能把現有 artifact 宣稱為 contemporaneous PIT |
| Trading_money / EOD amount | UNKNOWN | E1 檔只有 session date/value，沒有 contemporaneous receipt timestamp；2026 現行工作流說明不可無證據回貼 E1 |
| raw observation / valid_ohlc / tradability | UNKNOWN | 由 session-dated official raw tape 推導，但 E1 沒保存接收時間或歷史發布契約 |
| TAIEX total-return index | UNKNOWN | date/value 有，歷史 receipt/publish timestamp 無 |
| PIT industry | UNKNOWN | valid_from 的 date-level causality 有證據，但完整 E1 的 cutoff-time 證據不足 |
| deterministic random-control raw value | VERIFIED（值本身） | 不讀外部未來資訊；但 v1 persisted stock row membership 仍 UNAVAILABLE，所以不能藉此繞過 stock artifact gate |
| L3-G02 theme membership | UNAVAILABLE/BLOCKED_DATA | dated source 尚不存在 |

因此目前 **沒有任何 v1 persisted stock feature 欄位被批准為策略輸入**。market_context 也仍 UNKNOWN。這不否定特徵可作描述性資料研究，只限制「可交易 PIT 策略」用途。

## 5. 受控 feature-panel 串接

實作：

- `src/astraquant/research/feature_panel_integration.py`
- `configs/quality/pit_feature_matrix_layer1_integration_v1.yaml`
- tests：`tests/test_feature_panel_integration.py`
- QA workflow：`.github/workflows/source_pit_feature_matrix_layer1_integration.yml`

固定基礎 artifact：

- name：`pit-feature-matrix-layer1-v1-36662962925`
- artifact ID：`11075033221`
- base workflow：`36662962925`
- source revision：`fb8b042b46dc38838d103544ca17da10286c7bfe`
- formula version：`pit_feature_matrix_layer1_v1`
- manifest：`out/pit_feature_matrix_layer1_v1_manifest.json`
- manifest git blob：`c8e6c7e1d405aab4cfde8ddcc85d72f8fd45ca74`
- 每個年度 parquet 的 SHA256 由 base manifest 固定，loader 逐檔重新驗證 checksum。

串接契約：

1. 只接受 `(date, stock_id)` 唯一鍵。
2. canonical panel 或 feature parquet 有重複鍵立即失敗。
3. 左連接後 logical row count 必須完全不變。
4. config 明確列出 requested columns；parquet 以 schema inspection 後只讀 requested + 必要 metadata，不載入未要求特徵。
5. RAW 與 percentile 用明確欄名；RAW request 不允許指向 `*_pct`。
6. caller panel 已有同名 feature 或 companion audit 欄時立即失敗，不覆蓋。
7. E1 period 以 manifest 固定；panel 出現 E2/E3 key 立即失敗。
8. 缺值保留 null；不補零、不 forward-fill、不找下一日值。
9. 每個 feature 加：
   - `__feature_availability__<column>`
   - `__feature_missing_reason__<column>`
10. missing reason 至少區分 `ARTIFACT_ROW_ABSENT`、`WARMUP_INSUFFICIENT`、`FEATURE_VALUE_NULL`。
11. 若 artifact 有 `source_available_at` 且 caller 提供 `__decision_cutoff_at`，`source_available_at >= cutoff` 立即阻擋。
12. strategy mode 預設 `verified_only=True`；任何 required feature 不是 VERIFIED，**在 artifact 讀取前即阻擋**。

這個 utility 不另建 feature pipeline/cache，也沒有改 `ResearchConfigEngine` 或 simulator；後續只有在可用性契約真正變 VERIFIED 後，才可由既有 caller 把 hydration 結果傳入原 panel 路徑。

## 6. MA120 最小端到端驗證

合成資料驗證：

`close_to_ma120 = [-0.01, 0.0, 0.02, null]`

配 `COLUMN_THRESHOLD min=0.0` 的執行結果：

- -0.01 → 不通過，且 missing reason 空白：語意是「低於 MA120」。
- 0.00 → 通過。
- 0.02 → 通過。
- null → 執行上不放行，但 missing reason=`FEATURE_VALUE_NULL`；報告不得寫成「低於 MA120」。

另外已驗證：

- duplicate canonical key → fail
- duplicate artifact key → fail
- column conflict → fail
- formula version mismatch → fail
- parquet checksum mismatch → fail
- E1 之外 key → fail
- source timestamp 到達／超過 explicit cutoff → fail
- 修改較晚日期的 artifact row，不改寫較早 key 的 join 結果
- 未 requested 的欄位不會被 hydration 載入結果
- 真實 config 的 `close_to_ma120:UNAVAILABLE` 在 artifact read 前 fail closed

真實 E1 smoke test **沒有執行篩選計數**，因為 MA120 可用性契約未通過；照 owner 指示保留阻擋，不用合成測試冒充真實 PIT。

## 7. 測試結果

Integration QA workflow：`36690479141`  
結果：**success；15 passed in 0.78s**。

專用 QA 另有獨立 gate，確認真實 `close_to_ma120` 必須回報 `UNAVAILABLE`，不可因 artifact 不在 runner 本機而繞過 availability gate。

這次沒有執行：

- baseline
- VCP Round 2
- ML
- E2/E3 effect query
- outcome / win rate / expectancy / IC

觸發 QA push 同時依 repo 既有規則啟動一般 tests 與 EX-001 legacy regression；它們是既有 CI／授權軟體回歸，不視為新增研究。

## 8. 第 5 項剩餘限制

1. **PIT-safe contemporaneous price coordinate 尚未建立。** 現有 adjusted history 有 hindsight corporate-action rewrite，不能直接升級 VERIFIED。
2. 若要讓 adjusted-price features 用於 T→T+1 策略，需建立或取得「每個歷史 T 當時已知」的 adjustment state／as-of factor，或等價且可驗證的 causal coordinate；不能把現有 frozen hindsight-adjusted parquet改標 VERIFIED。
3. Trading_money、RAW/tradability、TAIEX TRI、PIT industry 的 historical cutoff-time evidence 仍需各自補強；沒有證據維持 UNKNOWN。
4. L3-G02 theme membership 仍 BLOCKED_DATA。
5. base feature artifact 到期：`2026-12-29T03:07:12Z`（台北 11:07:12）；目前 repo 只持久保存 manifest／QA CSV，不保存大型 parquet。
6. Canonical simulator 現行 candidate cutoff 是 T+1 00:00 abstraction；本項沒有修改。若未來要接受午夜後、實際開盤前才到達的來源，需另行審查 timing model。

第 5 項目前可交付審查的結論是：**feature-panel hydration 軟體契約已完成且 fail-closed；真實 stock feature 策略使用仍被資料可用性阻擋。** 這不是審查通過宣告。
