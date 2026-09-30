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

來源回測的 BUY/SELL 在原 repo 由 `Backtester.run` 以**同日收盤價**交給 `PaperBroker` 撮合。AstraQuant 不沿用這一點；本基線按既有研究契約翻譯成收盤確認、canonical trading calendar 的下一個合法 session RAW 開盤執行。

## 3. AstraQuant 採用規格

### 3.1 研究期間與母體

與 VCP Round 1 對齊：

- epoch：E1，2016-01-04 ～ 2021-12-31。
- 可讀 E1 之前資料作暖機；不得讀 E2 價格補完交易。
- universe：`configs/examples/universes/all_liquid.yaml`。
- P2-060 frozen exclusion SHA：`379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134`。
- all_liquid 現行條件：四碼、close >= 10、observed_trade、valid_ohlc、P2-060 排除、同日成交額 top 25%。
- 額外流動性條件須與 VCP Round 1 相同：**訊號日前 20 個該股票 common-session panel rows 的平均成交額 >= TWD 20,000,000，排除訊號當日**；common-session panel 對停牌／缺列會建立該市場 session 的空 row，因此任一 window row 的 `Trading_money` 缺失都使該次 prior20 均額為 null。

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
4. 流動性：依上節固定的 VCP Round 1 common-session panel row 語意，訊號日前 20 rows 均額 >= 2,000 萬；不含訊號日。
5. 訊號確認後，以 canonical trading calendar 的下一個 session RAW open 走 canonical execution。
6. RAW 缺失、OHLC 無效、tradability 不允許、buy_blocked 時，不成交；不得補 adjusted 價、不得延後追入。
7. 同股票持倉中新的進場訊號忽略並計數；同股票同時最多一筆。
8. 不套跨股票資金競爭；每筆採與 VCP Round 1 相同的獨立等初始名目研究口徑。
9. **不**加入 VCP pivot chase limit；本基線沒有追價上限。

與來源差異：

- 來源是 `>= prior_high`、無首次穿越；本基線採引擎既有首次穿越 + `>`。
- 來源回測以同日 close 成交；本基線收盤確認、canonical trading calendar 下一個合法 session 的 RAW open。
- 這些是刻意的 TRANSLATED 差異，不冒充來源完全重現。

### 3.3 MA120 available_at 與第 5 項依賴

直接引用最新第 5 項契約：`docs/PIT_FEATURE_MATRIX_LAYER1_INTEGRATION.md`。

- 數值語意仍固定：`close_to_ma120 = adjusted_close / SMA120 - 1`，條件為 `COLUMN_THRESHOLD min=0.0`。
- 通用 exact-key hydration 已實作於 `src/astraquant/research/feature_panel_integration.py`，config 為 `configs/quality/pit_feature_matrix_layer1_integration_v1.yaml`；本基線不得另建 loader 或第二套 availability 判準。
- 第 5 項已實查 frozen adjusted history 會被**未來公司行動回寫**，而 persisted stock-feature row membership 又先經 all_liquid（含 adjusted close 門檻）過濾。因此現有 v1 `close_to_ma120` 對「T 日收盤後形成決策、T+1 開盤執行」的可交易 PIT 用途為 **UNAVAILABLE**，不是單純 UNKNOWN。
- 現行 strategy gate 預設只接受 VERIFIED；`close_to_ma120:UNAVAILABLE` 會在讀 artifact 前 fail closed。
- 第 5 項 integration QA：workflow `36690479141` success，15 tests passed；這只證明 hydration/gate 軟體行為，不把合成測試當真實 PIT 通過。

因此 MA120 分類已從「計算存在、缺串接」更新為：**計算存在、串接 utility 已完成，但真實 v1 artifact 因 availability contract 被策略 gate 阻擋**。不新增 `PRICE_ABOVE_MA` evaluator。

## 4. 出場規格

### 4.1 ATR_FROM_ENTRY_STOP

來源算式保持：

`threshold_t = entry_anchor_t - 3 * ATR14_t`

來源與本基線共同固定：

- ATR period = 14。
- TR = max(high-low, |high-prev_close|, |low-prev_close|)。
- smoothing = **SMA14**，不是 Wilder。
- ATR 每日更新；threshold 可因 ATR 增減而上下移。
- 不使用持倉最高價、不設 monotonic floor，不映射成 `ATR_TRAILING`。
- trigger = `close_t <= threshold_t`；收盤確認後建立 sticky pending exit，下一個合法 canonical RAW open 才成交。

#### 本次推薦、等待核定：CA-normalized RAW strategy coordinate

推薦使用**因果、事件驅動的 RAW 經濟座標**，不使用 frozen hindsight-adjusted history 來維護持倉後的 ATR/entry state。

定義每個已知且可可靠處理的公司行動事件：

- 現金成分 `c = cash_per_share`，無則 0；
- 股數倍率 `m = share_multiplier`，無則 1；
- 從事件前策略價格座標轉到事件後座標：`P_post = (P_pre - c) / m`。

同一事件對 **entry anchor、ATR rolling state 內仍保留的 OHLC/prev-close、20D-low rolling state** 套用同一個轉換。實際交易成交價仍只用 canonical RAW；這個轉換只維護策略判斷狀態，不新增 fill、不改既有 CA 會計。

entry anchor：

- 初始值 = canonical buy **實際 fill.price**，所以包含既有不利滑價。
- **不含買進手續費**；手續費／賣出費稅仍由既有 portfolio/cost model 單獨計入報酬與交易統計。
- 理由：現有 `PortfolioIntentPolicy.register_entry()` 也是以 fill price 保存策略 entry_price，而 ledger 的 avg_cost 才把 fees 納入會計成本；技術門檻不應因券商費率改變。

與現有 CA 語意一致的證據：

- `PortfolioIntentPolicy.apply_corporate_action()` 對 stop state 已使用 `S_post=(S_pre-c)/m` 維持 RAW 經濟座標。
- `CanonicalExecutionService.mark_after_corporate_actions()` 對同 session stale RAW mark 也使用 `P_post=(P_pre-c)/m`。
- ledger 股數 mutation 保留總成本：quantity × m、avg_cost ÷ m。  
本基線只重用這個**轉換語意**，不把現有 fixed stop evaluator 改造成 ATR evaluator，也不重寫 CA accounting。

可靠處理範圍：

- 現金股利／明確現金成分 + 明確 share multiplier：使用上述公式。
- 單一 successor 且有明確 `quantity_multiplier=q`、無未分配的複合價值：entry anchor 以 `E/q` 移轉；若另有明確現金成分則先減現金再除倍率。**技術 rolling window 不把 predecessor bars 與 successor bars 直接拼接**；successor 的 ATR14/20D-low 狀態重置並重新暖機。
- composite successor、缺少 multiplier/value allocation、known-date 不可靠、轉換後價格 <= 0、或其他無法唯一映射事件：**阻擋策略技術出場評估並原因標記**，讓 canonical CA/terminal lifecycle 處理經濟持倉；不得猜轉換。

具體例子：

1. **無 CA**：RAW open=100，買方 0.1% 不利滑價後 fill=100.10；買費 0.1425% 約 0.1426/股另計。entry anchor=100.10。若 ATR14=2.00，門檻=94.10。費用影響淨報酬，不把門檻改成 94.24 或其他含費數字。
2. **純現金股利**：事件前 anchor=100.10，`c=5,m=1` → anchor=95.10；rolling 中事件前價格也各自減 5 後再與事件後 RAW 比較。若事件後一致座標 ATR14=2.00，門檻=89.10。5 元股利由既有 receivable/cash accounting 處理，不能再加進策略價格造成雙重計算。
3. **2-for-1 拆股**：事件前 anchor=100.10、ATR=2.00，`c=0,m=2` → anchor=50.05、ATR 尺度約 1.00、門檻=47.05；ledger quantity 同時乘 2。經濟門檻總值保持一致。

這是本次**推薦值，等待規格核定**；尚未授權實作。

### 4.2 BREAK_N_DAY_LOW

來源算式保持 `rolling_low(close,20).shift(1)`，本基線固定：

- N = 20。
- 比較欄位 = CA-normalized strategy close。
- reference_t = **該股票前 20 個 valid observed bars 的 close 最小值**，不含 T。
- current trigger = `close_t < reference_t`，嚴格 `<`；不是 intraday low。
- current bar 若無有效 close，當日不評估。
- suspended／無 bar 日期不當成一個 20D observation；不補值。
- explicit invalid/missing OHLC row 不進 valid-observed-bar sequence；不以較早值填入該日期。
- 至少要有 20 個前置 valid observed closes；不足則 reference=null、不得觸發。
- 公司行動時 rolling state 與 entry anchor 使用 4.1 的同一 CA-normalized RAW strategy coordinate。
- 收盤觸發後建立 sticky pending exit，下一個合法 canonical RAW open 執行。

「valid observed bars」是本次對尚未實作 exit evaluator 的 TRANSLATED 推薦定義，等待核定；不再使用「有效／共同 session」這種可多義描述。

### 4.3 出場事件順序 — 本次推薦、等待核定

優先沿用 VCP Round 1 已實作的順序：opening CA 先於 pending exit；pending exit 一旦成立即保持，不因後續 close 恢復而取消。

| 時點 | 順序與規則 |
|---|---|
| T open 前 | 先完成既有 settlement／到期 CA cash payment。 |
| T open | 先套用 opening corporate actions／share mutation／明確 successor conversion；若事件直接 extinguish position，分類 TERMINAL，沒有策略 sell fill。 |
| T open（CA 後） | 若前一 close 已有 pending strategy exit，嘗試當日 RAW open 賣出。sell_blocked、無有效 open 或其他 canonical 不可成交原因時，**保留原 pending intent** 到後續首個合法 open；後續規則不再取消它。 |
| T open（pending 後） | 才處理由 T-1 close 形成的 entry intents。對同股票而言，若 T-1 close 時仍持有，新的 entry signal 必須按「持倉中訊號忽略」處理，因此不允許「同一個 open 先賣再用昨日訊號買回」。 |
| T intraday | 本基線兩條策略出場都不是盤中觸價，不做 intraday strategy exit。 |
| T close | **包含當日 open 新進場的部位**，立即評估 ATR_FROM_ENTRY_STOP 與 BREAK_N_DAY_LOW；若成立，最早 T+1 open 出場。這與 VCP Round 1 entry-day close 可建立 pending exit 的語意一致，避免人工給一日 grace period。 |
| T close 雙觸發 | 兩條在**同一個 trigger close** 同時成立才記 `BOTH`；只建立一個 exit intent。若 ATR 先在某日成立、20D low 到後日才成立，原 pending reason 不回寫成 BOTH，可另作 secondary diagnostic。 |
| T close terminal | close-applied terminal lifecycle 在策略 close evaluation 後處理；若 terminal 使持倉消失，最終分類 TERMINAL，策略 pending reason只保留 audit，不產生第二筆 exit。 |

公司行動遇 pending exit：

- 純 cash/share event、持倉 ticker 不變：先依 4.1 轉換策略狀態，再嘗試原 pending sell；pending reason 不改。
- 單一 successor conversion：pending intent 移轉到明確 successor ticker，直到 successor 第一個 canonical 可賣 open；entry anchor 可依明確倍率移轉，但新的 ATR/20D rolling state按 4.1/4.2 重置。
- composite successor／無唯一價格映射：不得把一個 pending sell 猜分成多腿；由 CA lifecycle 處理並標 `CA_TRANSFORM_BLOCKED`／TERMINAL 類 audit，不能冒充 ATR/20D/BOTH 策略成交。
- terminal extinguishment/cashout 在 pending fill 前發生：TERMINAL wins；pending strategy intent 標 superseded，不重複出場。

重新進場：

- pending sell 在 T open 完成後，同股票**不接受由 T-1 close 產生的 entry intent**，因 T-1 close 時仍在持倉。
- T open 賣出後若 T close 形成新的合法 entry signal，最早 T+1 open 可重新進場；無額外固定 cooldown。

期末：

- pending exit 到 E1 最後 session 仍未成交，維持 open + pending reason；不強平、不讀 E2。

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
| MA120 feature -> signal panel | 第 5 項受控 hydration utility 已完成；真實 `close_to_ma120` 目前為 UNAVAILABLE | **串接軟體已存在但策略 gate 阻擋**；不得新增第二套 loader，也不新增 PRICE_ABOVE_MA evaluator |
| prior-20-day avg amount | `vcp_three_segment_details` 已有 `shift(1).rolling(20).mean()`；第 5 項 `amount_mean20_twd` 則包含當日、不等價 | 抽出／重用同一 prior-20 計算成可供 baseline filter 使用的欄位或通用介面；不能直接拿 amount_mean20_twd |
| close-confirmed exit plan -> canonical simulator | `ExitCompiler` 可攜帶 `close_exit_rules`，但 `CanonicalStrategySimulator` 現行只執行 policy RAW stop / max-hold | 後續把通用 close-rule evaluator 與 pending-next-open exit state 接入 canonical simulator；不可只靠 VCP 客製 runner |

### 7.3 確實缺 evaluator

| evaluator | 必要語意 |
|---|---|
| `ATR_FROM_ENTRY_STOP` | entry anchor − multiplier × 每日 ATR；本版 ATR14 SMA、close <= threshold、next legal open；不可用 ATR_TRAILING |
| `BREAK_N_DAY_LOW` | prior N close low（排除當日），close < level，next legal open |

注意：新增上述 compiler/evaluator 本身仍不足；還必須完成 7.2 的 canonical simulator close-rule 串接。

### 7.4 缺資料或語意未定

1. **MA120 / adjusted-price v1 artifact = UNAVAILABLE for tradable PIT**：第 5 項已證實歷史 adjusted OHLC 會被未來公司行動回寫；不是靠延遲一天即可解決。
2. **其他 source cutoff evidence**：Trading_money、RAW/tradability、TAIEX TRI、industry 仍有 UNKNOWN；不得視為 PASS。
3. **ATR/entry CA coordinate**：本文件 4.1 已提出唯一推薦方案，等待規格核定，不再留成未定技術問題。
4. 若 feature artifact 到期且未持久化，需按第 5 項 manifest 重建；不得臨時用不同公式替代。

## 8. 後續最小修改檔案（規格核定後才動）

確定會涉及：

- `src/astraquant/research/exit_engine.py`：註冊／驗證 `ATR_FROM_ENTRY_STOP`、`BREAK_N_DAY_LOW` 的 config semantics。
- `src/astraquant/portfolio/strategy_simulator.py`：接通通用收盤確認、pending next-open、BOTH、blocked exit、terminal 分流；不得破壞舊 stop/max-hold 行為。
- `src/astraquant/research/config_engine.py`：把 compiled close rules 明確傳到 canonical simulation contract，或以等價的既有架構入口完成；目前 `simulate_prepared()` 沒有消費 `prepared.exit_plan.close_exit_rules`。
- feature panel：直接重用第 5 項 `feature_panel_integration.py`；不得另建 loader。現有 v1 `close_to_ma120` 因 UNAVAILABLE gate 會被阻擋，直到 causal/PIT-safe feature source 另經第 5 項驗收。prior20 amount 仍需使用與 VCP Round 1 相同、不含當日的計算口徑。
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

## 10. 凍結前決策清單

### 已有證據支持，可直接固定

- N_SESSION_HIGH 60 的現行首次穿越 + 嚴格 `>` 語意。
- MA120 數值門檻 = raw `close_to_ma120 >= 0.0`；不新增 PRICE_ABOVE_MA。
- 來源 ATR14 = SMA(TR,14)，每日更新、非 trailing。
- 20D source rule = prior 20 closes、排除當日、strict `<`。
- T close 確認、下一 canonical session RAW open 執行的 TRANSLATED 執行框架。
- 成本、E1、all_liquid/P2-060、terminal accounting 與 VCP Round 1 比較契約。

### 本次推薦，等待核定

1. 4.1 的 CA-normalized RAW strategy coordinate：`P_post=(P_pre-c)/m`；entry anchor 用含滑價、不含 fee 的實際 fill.price。
2. 4.2 的 ATR/20D exit window 採 stock-specific valid-observed-bar sequence；不把停牌空日當 bar。
3. 4.3 的事件順序與 sticky pending exit、entry-day close evaluation、BOTH/TERMINAL 分類。
4. single-successor 移轉 entry anchor、但重置 ATR/20D rolling state；composite/ambiguous conversion fail closed。

這些是完整技術推薦，不要求 owner 另猜 implementation 細節；審查只需核定或退回。

### 尚未完成的程式／資料依賴

- 第 5 項真實 adjusted-price feature availability 目前 **UNAVAILABLE**；因此 baseline 即使規格核定，也不能直接執行。
- `ATR_FROM_ENTRY_STOP`、`BREAK_N_DAY_LOW` evaluator 尚未實作。
- canonical simulator 尚未接通 close-confirmed pending-exit rules。
- prior20 amount 尚未形成 baseline 可直接使用的通用 filter 欄／介面；第 5 項 `amount_mean20_twd` 包含當日，不可替代。
- 其他 EOD/RAW/TRI/industry cutoff evidence 若成為必要 input，UNKNOWN 仍需阻擋。

## 10.1 窗口、停牌與缺值 — 唯一計數口徑

不同元件保留各自實際／推薦語意，不為了表面統一強改成同一種 session count：

| 元件 | 計數序列 | 當日 T | 停牌／無 row | explicit 缺值 | 最低暖機 |
|---|---|---|---|---|---|
| N_SESSION_HIGH 60（既有實作） | caller panel 內該股票依 date 排序的 rows；`shift(1).rolling(60,min_periods=60)` | high window **不含 T**；T 只做 breakout compare | 若 panel 沒該股票 row，就不計數；既有元件不自行補 session | null close 佔 row 但不算 valid observation，rolling 不足 60 non-null 時 prior_high=null | current prior_high 要 60 個前置 non-null closes；首次穿越還要 previous_prior，因此實際首次可觸發需 previous row 也已有完整 60-window（等價至少 61 個前置 panel rows/close history） |
| MA120（第 5 項既有公式） | layer1 build 的該股票 adjusted rows；rolling 120 rows | **包含 T close** | source 沒 row 就不計數 | window 內 close 缺值使 120-valid requirement 不足，結果 null | 120 個可用 close；但真實 v1 artifact 目前 UNAVAILABLE for strategy |
| ATR14（本次推薦，TRANSLATED） | 該股票 **valid observed OHLC bars** sequence | **包含 T bar** | 不計 bar、不補值 | invalid OHLC 不進 sequence；不生成 TR | 14 個 valid TR observations；首個有效 bar 的 TR 用 high-low，其後用前一 valid observed close |
| BREAK_N_DAY_LOW 20（本次推薦，TRANSLATED） | 與 ATR 相同的 valid observed close bars | reference 排除 T；T close 只比較 | 不計 bar | invalid close 不進 sequence | T 之前 20 個 valid observed closes |
| prior20 Trading_money（沿用 VCP R1） | VCP Round 1 `build_common_session_panel` 的該股票 rows；`shift(1).rolling(20,min_periods=20).mean` | **排除 T** | common-session grid 會留下空 row，Trading_money=null，因此該 20-row window 失效 | 任一 prior20 row amount null → mean=null | 連續 20 個 prior common-session rows 全部有有效 Trading_money |

這個差異是刻意保留實際元件語意：N_SESSION_HIGH 不因基線新增規則而改寫；prior20 也不偷換成第 5 項「包含當日」的 `amount_mean20_twd`。

## 10.2 必要驗收案例

規格核定後，除了第 8 節原測試，至少加入：

- **CA coordinate**：無 CA、cash dividend、2-for-1 split 三組數值案例，驗證 entry anchor、ATR/rolling bars 與 threshold 按同一公式轉換，且 ledger cash/share accounting 不重複。
- **entry fee separation**：同一 fill price、不同 fee rate 不得改 ATR stop threshold，但 trade net return 必須反映 fee。
- **successor**：single successor 明確倍率可移轉 anchor、rolling reset；composite/缺倍率必須 fail closed。
- **N_SESSION_HIGH row semantics**：插入停牌缺 row 與 explicit null row，驗證既有 rolling 行為不被新 baseline wrapper 改寫。
- **ATR/20D valid-bar windows**：停牌空日不計 bar；invalid OHLC 不前填；暖機不足不觸發。
- **prior20 amount**：common-session 空 row 導致 null；T 當日成交額極端值不影響 T 的 prior20。
- **entry-day close**：T open 新進場、T close 立即觸發，最早 T+1 open 出場。
- **sticky pending**：觸發後連續 sell_blocked，即使之後 close 回到門檻上方仍保留原 intent。
- **BOTH immutability**：同 close 雙觸發=BOTH；不同 close 先後觸發不回寫成 BOTH。
- **terminal precedence**：pending exit 尚未 fill 時先被 terminal extinguish，只產生 TERMINAL lifecycle close，不產生第二筆策略 sell。
- **re-entry timing**：同 open pending sell 後不接受前一 close 的同 ticker entry；最早用賣出當日 close 的新訊號於下一 open 重進。
- **第 5 項 gate**：`close_to_ma120:UNAVAILABLE` 時 baseline prepare 必須阻擋；不得因 COLUMN_THRESHOLD 本身可運作就放行。

## 11. 停止點

本次規格補充只修改本文件。沒有：

- 修改 OWNER_PRIORITY_QUEUE；
- 修改 signal/exit/simulator；
- 建立正式 baseline config；
- 執行 baseline 回測；
- 讀取 E2/E3 效果；
- promote / unlock OOS；
- 啟動 ML、VCP Round 2 或其他研究。
