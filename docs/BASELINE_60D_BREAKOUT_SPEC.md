# baseline_60d_breakout_v1 — 60 日突破完整基線規格

狀態：**SPEC REVIEW REQUIRED / NOT EXECUTED**

本文件只固定規格與最小缺口對帳。未修改引擎、未執行回測、未啟用 E2/E3、未變更 OWNER_PRIORITY_QUEUE。第 5 項目前仍為 AWAITING_REVIEW；因此本文件中的待凍結決策在審查核定前不得進入策略研究。

## 1. 研究目的與結論邊界

策略版本：`baseline_60d_breakout_v1`。

目的：建立一套與 VCP Round 1 並列的「完整方法基線」，回答兩套完整方法各自的描述性交易結果如何。

這個比較**不能**回答「VCP 收縮條件是否提供額外增益」。若要回答增益問題，必須另立實驗，固定出場、成本、母體、執行與其他條件，只改進場定義。

本版本只固定一套規則，不建立掃描網格。亂數／虛無校準與多重檢定尚未完成前，只能稱 E1 描述性基線，不宣稱有效 edge、不 promote、不解鎖 OOS。

## 2. 原始來源與固定 revision

來源對照以 `docs/BASELINE_SOURCE_LEDGER.md` 已固定版本為準：

- 第三方 repo：`Joyen09/tw-stock-strategy-framework`
- frozen commit：`aafe2bf23f587fba13ec52c6e41af97918ace097`
- 來源策略：`src/strategies/livermore.py::LivermoreStrategy.evaluate`
- 指標：`src/indicators.py::{sma, atr, rolling_high, rolling_low}`
- 來源回測呼叫流程：`src/engine/backtest.py::Backtester.run`
- 來源撮合／持倉均價：`src/broker/paper.py::PaperBroker.place_order`

歸屬仍沿用 ledger：第三方實作只視為 TRANSLATED 參考，不宣稱為李佛摩本人原始規則。

### 2.1 來源實際算式

來源 `LivermoreStrategy.DEFAULTS`：

- `breakout_window=60`
- `trend_ma=120`
- `atr_window=14`
- `atr_stop=3.0`
- `exit_window=20`

來源進場實際程式語意：

- `prior_high = rolling_high(close, 60).shift(1)`
- `trend = SMA120(close)`
- `price >= prior_high`
- `price >= trend`
- 沒有首次穿越要求。

來源 ATR 出場實際程式語意：

- TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
- `ATR14 = TR.rolling(14).mean()`，是 **14 日簡單移動平均**，不是 Wilder。
- 每個評估日重新計算 `ATR_t`，且包含當日 high/low/close。
- 門檻 = `entry_avg_price - 3 * ATR_t`
- 來源觸發比較 = `close_t <= threshold_t`
- 因 ATR 每日更新，threshold 可向上或向下；它不追蹤持倉最高價，也沒有「只上移」限制。
- 因此它**不是** AstraQuant 現有 `ATR_TRAILING`，也不是固定不變的價格停損。

來源 20 日低點出場：

- `exit_low = rolling_low(close, 20).shift(1)`
- 即「**前 20 個收盤價的最低值，排除當日**」。
- 來源觸發比較 = `close_t < exit_low_t`，嚴格小於。
- 不是盤中 low 跌破。

來源回測的 BUY/SELL 在原 repo 由 `Backtester.run` 以**同日收盤價**交給 `PaperBroker` 撮合。AstraQuant 不沿用這一點；本基線按既有研究契約翻譯成收盤確認、次一合法共同交易日 RAW 開盤執行。

## 3. AstraQuant 採用規格

### 3.1 研究期間與母體

與 VCP Round 1 對齊：

- epoch：E1，2016-01-04 ～ 2021-12-31。
- 可讀 E1 之前資料作暖機；不得讀 E2 價格補完交易。
- universe：`configs/examples/universes/all_liquid.yaml`。
- P2-060 frozen exclusion SHA：`379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134`。
- all_liquid 現行條件：四碼、close >= 10、observed_trade、valid_ohlc、P2-060 排除、同日成交額 top 25%。
- 額外流動性條件須與 VCP Round 1 相同：**訊號日前 20 個共同交易日平均成交額 >= TWD 20,000,000，排除訊號當日**。

注意：第 5 項 `amount_mean20_twd` 是包含當日的 rolling mean，**不能**直接替代 VCP Round 1 的 `shift(1).rolling(20)` 流動性口徑。

### 3.2 進場

採用：

1. trigger：`N_SESSION_HIGH`，`lookback=60`。
2. 沿用 AstraQuant 現有語意：
   - `close_t > prior_high60_t`
   - `close_{t-1} <= prior_high60_{t-1}`
   - 即首次穿越且嚴格 `>`。
3. MA120 filter：
   - 第 5 項原值 `close_to_ma120 = adjusted_close / SMA120(adjusted_close) - 1`
   - 條件為 **`close_to_ma120 >= 0.0`**
   - 使用原值，不是 `>=1`，也不是橫截面 percentile。
4. 流動性：訊號日前 20 個共同交易日均額 >= 2,000 萬。
5. 訊號確認後，次一共同交易日以 RAW open 走 canonical execution。
6. RAW 缺失、OHLC 無效、tradability 不允許、buy_blocked 時，不成交；不得補 adjusted 價、不得延後追入。
7. 同股票持倉中新的進場訊號忽略並計數；同股票同時最多一筆。
8. 不套跨股票資金競爭；每筆採與 VCP Round 1 相同的獨立等初始名目研究口徑。
9. **不**加入 VCP pivot chase limit；本基線沒有追價上限。

與來源差異：

- 來源是 `>= prior_high`、無首次穿越；本基線採引擎既有首次穿越 + `>`。
- 來源回測以同日 close 成交；本基線收盤確認、次一合法共同交易日 RAW open。
- 這些是刻意的 TRANSLATED 差異，不冒充來源完全重現。

### 3.3 MA120 available_at

第 5 項 review1 已確認：

- `close_to_ma120` 的數值計算、欄位保留、`COLUMN_THRESHOLD min=0.0` 語意均正確。
- `SignalEvaluator._normalize_panel` 會保留 caller-supplied 額外欄位。
- 但 `ResearchConfigEngine.prepare()` **不會**自動載入／join 第 5 項 feature parquet。
- exact AFTER_SESSION_CLOSE provider availability timestamp 目前仍為 **UNKNOWN**。

因此本項分類為「計算已存在、缺串接」，不是缺 `PRICE_ABOVE_MA` evaluator；但在 exact decision-time PIT 證據未補齊前，不得宣稱可用於要求該時點已證實 PIT 安全的研究。

## 4. 出場規格

### 4.1 ATR_FROM_ENTRY_STOP

來源算式保持：

`threshold_t = entry_price_anchor - 3 * ATR14_t`

其中：

- ATR period = 14。
- TR 如 2.1。
- smoothing = **SMA14**，不是 Wilder。
- ATR_t 包含當日有效 high/low/close。
- 每日更新 ATR。
- threshold 容許因 ATR 改變而向上或向下。
- 不使用持倉最高價。
- 不映射到 `ATR_TRAILING`。

觸發：

- 來源是 `close_t <= threshold_t`。
- 本基線維持 `<=`，收盤確認。
- 觸發後次一共同交易日 RAW open 嘗試出場；若 sell side 不可執行，保留 pending exit，後續首個合法共同交易日 open 執行。

**待凍結決策 A — CA 一致價格座標**

來源 repo 沒有 AstraQuant 的 RAW/adjusted 雙座標與 CA ledger。AstraQuant 不可直接用 adjusted ATR 去減 RAW entry fill。

審查前需從下列原則凍結唯一實作：

- entry anchor、ATR、trigger close 必須處於同一個 CA 一致價格座標；
- 策略判斷不得因除權息機械觸發；
- 實際成交仍只能用 RAW canonical execution；
- entry anchor 遇現金／股數 CA 後的變換要與既有 portfolio CA 經濟語意一致；
- 不得用 `ATR_TRAILING` 的 high-watermark/monotonic trail 取代。

未凍結此點前，`ATR_FROM_ENTRY_STOP` 尚不可執行。

### 4.2 BREAK_N_DAY_LOW

本基線明確採來源算式：

- N = 20。
- series = CA 一致的 research close。
- reference_t = 前 20 個有效／共同 session 收盤價的最低值，**排除當日**。
- trigger = `close_t < reference_t`，嚴格 `<`。
- 比較的是收盤，不是盤中 low。
- 收盤確認，次一合法共同交易日 RAW open 出場。
- 若次日不可賣，保留 pending exit，之後首個合法 open 執行。

此條的「收盤確認、次一 open」為 TRANSLATED 執行語意；來源本身是在同日 close 回測成交。

### 4.3 同日雙觸發、terminal 與期末

- ATR 與 20 日低點同日成立：`exit_reason=BOTH`，只建立一個 exit intent，不重複成交。
- terminal lifecycle 另列 `TERMINAL:<component>`，不得算作 ATR／20D_LOW／BOTH。
- 期末未平倉另列，不強平、不讀 E2 補完。
- pending exit 到 E1 結束仍未成交者保持 open/pending 狀態。

## 5. 成本與執行比較契約

與 VCP Round 1 對齊：

- 買進手續費 0.1425%。
- 賣出手續費 0.1425%。
- 賣出證交稅 0.3%。
- 買賣各 0.1% 不利滑價。
- 成本由共用成本模型只扣一次。
- RAW execution + canonical tradability + CA/terminal lifecycle。
- 每股票同時最多一筆。
- 無跨股票資金競爭。
- 期末 open positions 不混入 closed trade 的勝負統計。

刻意不同於 VCP Round 1：

- 進場 trigger = 60 日首次突破 + MA120，不是 VCP 三段收縮。
- 沒有 pivot。
- 沒有 1.05 chase limit。
- 出場是 entry-anchor ATR14(SMA) 與 prior-close-low20，不是 ATR21 Wilder trailing + D21。
- 沒有 VCP 的四軸 108 格掃描。

## 6. 預定輸出統計

完整方法基線後續報告至少包含：

- signal_count、entry_count、ignored_while_holding、其他未成交原因。
- n_closed、n_open。
- 扣成本 win_rate、loss_rate、breakeven_rate。
- avg_win、avg_loss（絕對值）、payoff、expectancy。
- expectancy identity 核對。
- holding days / holding sessions。
- unique stocks、entry dates、年度交易覆蓋。
- exit_reason：ATR / 20D_LOW / BOTH / TERMINAL / OPEN。
- 前 1／3／5 筆最大獲利交易移除後 expectancy，保留原結果。
- 逐年結果；不得把跨年結果混成獨立 OOS。
- 期末未平倉截尾提醒。

本輪沒有亂數／虛無與多重檢定校準完成，因此後續即使跑出正期望也只能寫描述性 baseline。

## 7. 最小缺口對帳

### 7.1 可直接重用

| 需要 | 現有位置 | 結論 |
|---|---|---|
| 60 日首次突破 | `src/astraquant/research/signal_engine.py::_n_session_high` | 直接重用 `N_SESSION_HIGH lookback=60`；已知與來源 `>=`/無首次穿越不同 |
| MA120 數值條件 evaluator | `COLUMN_THRESHOLD` | evaluator 可直接重用；門檻是 `close_to_ma120 >= 0.0` |
| RAW next-open + tradability | `src/astraquant/execution/market_data.py::ExecutionMarketData.resolve` + canonical execution | 直接重用；缺 RAW/invalid/tradability block 均 fail closed |
| CA/terminal accounting | canonical portfolio/CA stack | 直接重用 |
| VCP Round 1 成本模型 | SideAwareBpsFeeModel + FixedBpsSlippage | 直接重用相同假設 |

### 7.2 計算已存在、缺串接

| 需要 | 現況 | 最小後續工作 |
|---|---|---|
| MA120 feature -> signal panel | `close_to_ma120` 已在第 5 項 parquet；ResearchConfigEngine 只吃 caller-supplied panel | 建立既有 feature artifact 到 canonical signal panel 的 hydration/join；不新增 PRICE_ABOVE_MA evaluator |
| prior-20-day avg amount | `vcp_three_segment_details` 已有 `shift(1).rolling(20).mean()`；第 5 項 `amount_mean20_twd` 則包含當日、不等價 | 抽出／重用同一 prior-20 計算成可供 baseline filter 使用的欄位或通用介面；不能直接拿 amount_mean20_twd |
| close-confirmed exit plan -> canonical simulator | `ExitCompiler` 可攜帶 `close_exit_rules`，但 `CanonicalStrategySimulator` 現行只執行 policy RAW stop / max-hold | 後續把通用 close-rule evaluator 與 pending-next-open exit state 接入 canonical simulator；不可只靠 VCP 客製 runner |

### 7.3 確實缺 evaluator

| evaluator | 必要語意 |
|---|---|
| `ATR_FROM_ENTRY_STOP` | entry anchor − multiplier × 每日 ATR；本版 ATR14 SMA、close <= threshold、next legal open；不可用 ATR_TRAILING |
| `BREAK_N_DAY_LOW` | prior N close low（排除當日），close < level，next legal open |

注意：新增上述 compiler/evaluator 本身仍不足；還必須完成 7.2 的 canonical simulator close-rule 串接。

### 7.4 缺資料或語意未定

1. **MA120 / adjusted EOD exact decision-time available_at = UNKNOWN**。第 5 項 review1 未取得 provider 精確 known-time；在解決前不可宣稱 exact AFTER_SESSION_CLOSE PIT PASS。
2. **ATR_FROM_ENTRY_STOP 的 CA 一致 entry anchor 座標**待凍結，見 4.1 決策 A。
3. 若 feature artifact 到期且未持久化，需按第 5 項 manifest 重建；不得臨時用不同公式替代。

## 8. 後續最小修改檔案（規格核定後才動）

確定會涉及：

- `src/astraquant/research/exit_engine.py`：註冊／驗證 `ATR_FROM_ENTRY_STOP`、`BREAK_N_DAY_LOW` 的 config semantics。
- `src/astraquant/portfolio/strategy_simulator.py`：接通通用收盤確認、pending next-open、BOTH、blocked exit、terminal 分流；不得破壞舊 stop/max-hold 行為。
- `src/astraquant/research/config_engine.py`：把 compiled close rules 明確傳到 canonical simulation contract，或以等價的既有架構入口完成；目前 `simulate_prepared()` 沒有消費 `prepared.exit_plan.close_exit_rules`。
- feature panel 的既有 caller/hydration 層：join `close_to_ma120` 與 prior-20 avg amount。**最終落檔位置需沿用現有 panel builder，不另建平行資料管線；審查前不臆造新 loader path。**
- baseline configs：規格核定後建立 `baseline_60d_breakout_v1` 對應 signal / exit / run config，不沿用現有過時的 `PRICE_ABOVE_MA` draft。

### 必要測試

後續至少要有：

1. N_SESSION_HIGH 60：首次穿越與嚴格 `>` regression。
2. MA120：`close_to_ma120 [-0.01,0,0.02,null] -> [false,true,true,false]`，且確認是 raw feature 欄非 percentile。
3. feature hydration：join 不改 logical row count、不偷讀 E2/E3、hash/version 可追溯。
4. prior20 amount：只用 t-20..t-1；訊號日極端成交額不能改變當日流動性資格。
5. ATR14：TR、SMA14、包含當日、每日更新、threshold 可上下移。
6. ATR 與 entry anchor 經 CA 前後保持同一經濟座標，不製造機械觸發。
7. 20D low：排除當日、只看 close、嚴格 `<`。
8. 兩條同日成立 = BOTH，只一筆 exit intent。
9. 收盤觸發不能同日成交，只能次日或後續首個合法 RAW open。
10. sell_blocked / 無有效 open 時 pending exit 不消失。
11. terminal lifecycle 與策略 exit 分開。
12. E1 期末 open 不強平、不讀 E2。
13. 固定 stop / max-hold 不得殘留。
14. 成本與滑價只扣一次。
15. baseline 與 VCP Round 1 的共同比較設定 manifest 對帳一致。

## 9. 現有文件矛盾與證據

本文件不修改其他來源文件，只集中記錄：

- `configs/drafts/baseline/baseline_livermore_v1.yaml` 仍寫 `PRICE_ABOVE_MA`；這與 review1 / `BASELINE_COMPONENT_GAPS.md` 已確認的「`close_to_ma120` + `COLUMN_THRESHOLD min=0.0`，只缺 feature-panel 串接」矛盾。該 draft 不可直接執行。
- `BASELINE_SOURCE_LEDGER.md` 已正確指出來源 ATR 是 entry-anchor，而非 high-watermark trailing；但本規格再進一步從 frozen `src/indicators.py::atr` 確認 smoothing 是 **rolling SMA14**。
- `BASELINE_COMPONENT_GAPS.md` 將 baseline 最小缺口概括為「2 exit evaluators + 1 feature-panel join」。唯讀實查 `CanonicalStrategySimulator` 後需再補充：close-rule compiler 結果目前沒有被 canonical simulator 執行，因此實作時還有一項 **close-rule simulator wiring**，不是只註冊兩個 evaluator 就完成。
- 第 5 項 `amount_mean20_twd` 包含今日；VCP Round 1 liquidity 是 prior20、不含今日。兩者不能混用。

## 10. 待凍結決策

審查時只需凍結下列尚未有唯一證據答案的事項；其餘規則已明確：

1. **ATR/entry anchor 的 CA 一致價格座標與轉換方式**：必須保留 `entry - 3×ATR_t` 經濟語意，禁止改成 trailing。
2. **第 5 項 exact available_at UNKNOWN 的處置**：取得更強 provider 時戳／契約，或明確維持 BLOCKED；不得把 UNKNOWN 當 PASS。
3. **feature hydration 的既有架構落點**：必須沿用現有 panel pipeline，不另建平行 loader/cache。

這三點核定後才可稱為「可實作凍結規格」。

## 11. 停止點

本 commit 只新增本文件。沒有：

- 修改 OWNER_PRIORITY_QUEUE；
- 修改 signal/exit/simulator；
- 建立正式 baseline config；
- 執行 baseline 回測；
- 讀取 E2/E3 效果；
- promote / unlock OOS；
- 啟動 ML、VCP Round 2 或其他研究。
