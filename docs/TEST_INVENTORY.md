# Test Inventory

狀態：ACTIVE — 本表為待測項目的唯一來源。

## 維護規則

本表為待測項目的唯一來源。後續任何掃描、特徵建置或出場開發，一律從本表取項目並回寫狀態，不從對話臨時決定。每完成一項即時更新該列的六階段狀態與報告連結。新增項目必須同時填入九個欄位。

九個必填欄位是 `id / origin / definition / purpose / code / tests / reports / gap / depends_on`。本表另加 `item` 供閱讀，以及六階段、掃描層級、原始方法涵蓋度與備註。找不到實作時 `code` 必須寫「未實作」；沒有測試或報告必須寫「無」。

六階段只能寫「有／無／不適用」：
1. 來源資料
2. PIT
3. 元件
4. 模擬器串接
5. 正式掃描
6. 報告

六階段的「有」代表該列所述範圍已具備；部分代理不把整列升成「有」，而是在 code/tests/reports 與 gap 中明示代理。掃描層級固定為 `CANDIDATE / FULL_TRADE / NONE`。原始方法涵蓋度固定為 `FULL / SIMPLIFIED / NA`。

L2/L3 計數規則：
- **概念數**：把一個獨立資訊概念算一次；同一概念的不同週期、門檻、差值或斜率不另算概念。下方每個 bundle 的「概念拆分」明示它包含幾個概念。
- **元件數**：只計目前 repo 內實際可執行且能支援該層概念的 distinct component；generic adapter 不算成 domain feature。
- **參數版本數**：只計上述可執行元件目前已明示的完整可執行版本；不把 sweep Cartesian cells 當版本。EARNINGS_STREAK 的 2/3/4 季門檻計三個版本；其餘目前各計一個 committed/default executable version。
- 三個數字分開統計，不相加、不互相代替。

目前計數：**L2 = 57 概念 / 8 元件 / 10 參數版本；L3 = 15 概念 / 2 元件 / 2 參數版本。**

L2 的 8 個現有元件：`LONG_TERM_TREND_STRUCTURE`、`BOLLINGER_COMPRESSION`、`RSI` filter/rank（合併計一）、`RSI_RELATIVE`、`KD_SATURATION_STATE`、`STABLE`、`FUNDAMENTAL_FLOOR`、`EARNINGS_STREAK`。其中多數只覆蓋 bundle 的一部分，故對應 bundle 的六階段仍可為「無」。

L3 的 2 個現有元件：`ALL` turnover-top-fraction liquidity pool、`INDUSTRY_THEME` 的 dated `THEME` evaluator。

## 表一：L1 進場觸發（17 列）

計數口徑：**「老手觀察為六大分類，與本表 17 列不是同一種計數。250 日突破屬 repo 既有，不在老手六大分類內。」**

L1 六階段完成數：來源資料 **17/17**；PIT **15/17**；元件 **15/17**；模擬器串接 **15/17**；正式掃描 **5/17**；報告 **5/17**。

| id | item | origin | definition | purpose | code | tests | reports | gap | depends_on | 來源資料 | PIT | 元件 | 模擬器串接 | 正式掃描 | 報告 | 掃描層級 | 原始方法涵蓋度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L1-001 | 250日新高突破 | repo 既有 | close 上穿前 250 個 session 的 prior-only rolling high，且前一日尚未在該 prior high 之上。 | 檢查長期新高突破是否提供候選資訊。 | src/astraquant/research/technical_components.py::n_session_high | tests/test_config_engine.py | SOURCE_ONEIL_TAIWAN_SWEEP.md；SOURCE_BREAKOUT_SIGNAL_AUDIT.md | 已有候選掃描，但 SOURCE_ONEIL_TAIWAN_SWEEP 同時帶 LONG_TERM_TREND_STRUCTURE，並非裸 N_SESSION_HIGH 的獨立 surface。 | 無 | 有 | 有 | 有 | 有 | 有 | 有 | CANDIDATE | NA | 無 |
| L1-002 | 布林壓縮後突破（日線） | owner 觀察 | 先以 bandwidth=(upper-lower)/middle 判定近期壓縮，再要求 close 上穿上軌、量能條件與可選中線向上；現行日線 config 另加 RSI13>RSI26。 | 檢查壓縮後擴張是否有候選路徑資訊。 | src/astraquant/research/technical_components.py::bollinger_compression_breakout；::bollinger_compression；::rsi_relative | tests/test_observation_components.py；tests/test_path_diagnostics.py | SOURCE_BOLLINGER_DAILY_SWEEP.md | 只涵蓋日線；60 分鐘原始版本缺 canonical 盤中來源。 | 無 | 有 | 有 | 有 | 有 | 有 | 有 | CANDIDATE | SIMPLIFIED | 日線代理版；不得宣稱涵蓋 60 分鐘原始方法。 |
| L1-003 | VCP 收縮後突破（機械化第一版） | owner 觀察 | 現有 SIMPLIFIED 實作含舊版 prior-only 多窗口收縮，以及 round1 TRANSLATED 三段連續區間收縮（兩次 0.75 收縮、pivot、dry-up、breakout volume、不追高）；round2 新版本另加 min_amplitude_3=0.01，尚未執行效果掃描。 | 檢查機械化 VCP breakout 與固定完整進出場近似的穩定性。 | src/astraquant/research/technical_components.py::vcp_breakout；::vcp_three_segment_details；src/astraquant/research/vcp_round1.py::VCPRound1TradeRunner；src/astraquant/research/vcp_round2.py::VCPRound2TradeRunner | tests/test_observation_components.py；tests/test_path_diagnostics.py；tests/test_vcp_round1.py；tests/test_vcp_round2.py | SOURCE_VCP_DAILY_SWEEP.md；VCP_ROUND1_THREE_SEGMENT_V1.md | 原始 discretionary VCP 的突破前進場、突破後加碼仍未涵蓋；round2 min_amplitude_3/output-schema 修正已實作測試但尚未掃描、無 round2 報告。 | 無 | 有 | 有 | 有 | 有 | 有 | 有 | FULL_TRADE | SIMPLIFIED | round1 結果凍結；round2 為新版本，不回寫 round1 定義或輸出。 |
| L1-004 | Anchor 反轉 UP | owner 觀察 | local low 僅在 right_confirm_sessions 完成後成立；anchor=低點前一根 high；之後需 required_closes 根 close>anchor，且不得回填到極值日。 | 檢查 PIT-safe anchor-up 反轉候選。 | src/astraquant/research/technical_components.py::anchor_reversal | tests/test_observation_components.py；tests/test_path_diagnostics.py | SOURCE_ANCHOR_UP_DAILY_SWEEP.md | 無。 | 無 | 有 | 有 | 有 | 有 | 有 | 有 | CANDIDATE | FULL | 無 |
| L1-005 | Anchor 反轉 DOWN | owner 觀察 | local high 僅在 right_confirm_sessions 完成後成立；anchor=高點前一根 low；之後需 required_closes 根 close<anchor；路徑診斷以 SHORT 定義驗算。 | 檢查 PIT-safe anchor-down 反轉候選。 | src/astraquant/research/technical_components.py::anchor_reversal | tests/test_observation_components.py；tests/test_path_diagnostics.py::test_anchor_down_short_direction_manual_check | SOURCE_ANCHOR_DOWN_DAILY_SWEEP.md | 無。 | L1-004 | 有 | 有 | 有 | 有 | 有 | 有 | CANDIDATE | FULL | UP/DOWN 共用同一元件，不重複實作。 |
| L1-006 | 跳空上漲 | repo 既有 | open/prior_close-1 > threshold；unfilled_sessions 非 0 時目前明確拒絕。 | 檢查開盤跳空是否是有用觸發。 | src/astraquant/research/technical_components.py::gap_up | 無 | 無 | 缺正式 source parameter sweep 與落盤報告。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | NA | 無 |
| L1-007 | 爆量 | repo 既有 | 當日 Trading_Volume / prior-only lookback 平均量 > multiplier。 | 檢查量能異常是否是有用觸發。 | src/astraquant/research/technical_components.py::volume_spike | 無 | 無 | 缺正式 source parameter sweep 與落盤報告。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | NA | 無 |
| L1-008 | 均線黃金交叉 | repo 既有 | fast SMA>slow SMA 且前一日 fast<=slow；要求 1<=fast<slow。 | 檢查均線交叉觸發。 | src/astraquant/research/technical_components.py::ma_golden_cross | 無 | 無 | 缺正式 source parameter sweep 與落盤報告。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | NA | 無 |
| L1-009 | MACD 柱狀值上穿零 | repo 既有 | 目標定義：MACD histogram 由 <=0 上穿 >0。現行函式實際計算 EMA_fast-EMA_slow 的 MACD 線上穿零，未計 signal line/histogram。 | 檢查 MACD 柱狀動能翻正。 | src/astraquant/research/technical_components.py::macd_cross_above_zero | 無 | 無 | 實作名稱存在但機械定義不符目標：目前是 MACD 線，不是 histogram；需修正後才可視為驗證可用；另缺正式 sweep/report。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | SIMPLIFIED | 無 |
| L1-010 | KD 低檔黃金交叉 | repo 既有 | K>D、前一日 K<=D，且前一日 K/D 都在 low_zone 以下。 | 檢查低檔 KD 交叉。 | src/astraquant/research/technical_components.py::kd_low_zone_golden_cross | 無 | 無 | 缺正式 source parameter sweep 與落盤報告。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | NA | 無 |
| L1-011 | RSI 穿越門檻 | repo 既有 | Wilder-style RSI 由 <=level 上穿 >level；lookback/level 可配置。 | 檢查 RSI threshold cross。 | src/astraquant/research/technical_components.py::rsi_cross | 無 | 無 | 現有 SOURCE_RSI_DAILY_SWEEP 是 RSI_PULLBACK_RECLAIM 日線代理，不是本 RSI_CROSS 的正式 sweep；本列仍缺 sweep/report。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | SIMPLIFIED | RSI 原始多時間框架方法另列 L1-X03。 |
| L1-012 | KD 解除鈍化 | owner 觀察 | 前一日處於持續 high/low saturation state，當日離開該 zone；可要求 K/D cross 確認。 | 檢查鈍化狀態真正解除，而非把極值區本身當反轉。 | src/astraquant/research/technical_components.py::kd_saturation_release；::kd_saturation_state | tests/test_rsi_kd_observations.py | 無 | 缺正式 source daily sweep 與報告；現有測試直接驗 state，release 尚無獨立結果報告。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | FULL | 無 |
| L1-013 | 布林上軌突破（單純） | repo 既有 | close>當日 upper band 且前一日 close<=前一日 upper band；window/stddev 可配置。 | 隔離單純上軌突破，不混入壓縮/量能。 | src/astraquant/research/technical_components.py::bollinger_upper_break | 無 | 無 | 缺正式 source parameter sweep 與落盤報告。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | NA | 無 |
| L1-014 | 一般回檔後重新站回 | repo 既有 | 前一日 low 觸及/接近 MA，前一日 close<=MA，當日 close>MA；ma_window/touch_tolerance 可配置。 | 檢查一般 pullback reclaim。 | src/astraquant/research/technical_components.py::pullback_reclaim | 無 | 無 | 缺正式 source parameter sweep 與落盤報告。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | NA | 無 |
| L1-015 | 連續上漲天數 | repo 既有 | 最近 N 個 session 每日 close 都高於前一日 close。 | 檢查連續上漲 streak 觸發。 | src/astraquant/research/technical_components.py::consecutive_up_days | 無 | 無 | 缺正式 source parameter sweep 與落盤報告。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | NA | 無 |
| L1-016 | 一目均衡表轉折 | repo 既有 | 未定義 | 檢查 Ichimoku 轉折觸發。 | 未實作 | tests/test_config_engine.py::test_unimplemented_signal_component_fails_at_compile_time | 無 | 來源日 OHLC 可用，但 exact trigger/available_at 尚未定義；schema 名稱存在、registry 無 evaluator。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L1-017 | Donchian 通道突破 | 本次新提 | 未定義；若定義為 close 上穿 prior-only N-session high，語義可重用 L1-001，需先凍結 channel/lookback/突破時點。 | 檢查 Donchian breakout，避免重寫等價元件。 | 未實作；先確認能否重用既有 250 日新高突破元件，不要重寫。 | 無 | 無 | 需先定義；若採 prior-only N-session high 版本，直接重用 L1-001，不另建元件。 | L1-001 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |

### 表一之外（不計入 17 列）

表外項目數：**7**。

| id | item | origin | definition | purpose | code | tests | reports | gap | depends_on | 來源資料 | PIT | 元件 | 模擬器串接 | 正式掃描 | 報告 | 掃描層級 | 原始方法涵蓋度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L1-X01 | 布林壓縮 60 分鐘版 | owner 觀察 | 與日線 Bollinger 邏輯相同，但只能使用已完成 60 分鐘 bar；bar 完成後才 available。 | 驗證原始 60 分鐘 Bollinger 方法。 | src/astraquant/research/technical_components.py::bollinger_compression_breakout（邏輯可重用） | tests/test_observation_components.py | 無 | DEFERRED：缺 canonical 盤中來源、completed-bar available_at、聚合邊界與快照/hash 契約。 | L1-002 | 無 | 無 | 有 | 無 | 無 | 無 | NONE | SIMPLIFIED | 無 |
| L1-X02 | VCP 突破前進場 / 突破後加碼 | owner 觀察 | 未定義；需分別定義 pre-breakout entry 與 breakout add-on 的條件、available_at、資金/部位互動。 | 補齊原始 VCP 未涵蓋的進場與加碼段。 | 未實作 | 無 | 無 | 現行 VCP 只涵蓋機械化 breakout；前置 entry/add-on 未實作。 | L1-003 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | SIMPLIFIED | 無 |
| L1-X03 | RSI 多時間框架 SOP | owner 觀察 | daily direction → completed 60m rhythm → completed 15m strength/pullback + volume；以 available_at 對齊，不得只按 date join。 | 驗證完整多時間框架 RSI SOP。 | src/astraquant/research/technical_components.py::rsi_pullback_reclaim；::rsi_filter（日線代理部分） | tests/test_rsi_kd_observations.py | SOURCE_RSI_DAILY_SWEEP.md | DEFERRED：缺 canonical 60m/15m 來源與 completed-bar PIT；現有報告僅日線代理。 | L1-011 | 無 | 無 | 有 | 無 | 有 | 有 | CANDIDATE | SIMPLIFIED | 無 |
| L1-X04 | 夜盤＋美股背景疊加 | owner 觀察 | TAIFEX 夜盤 05:00 相對前一 TWSE close 的 basis，加上 TSM ADR/SOX/Nasdaq 同方向票數；所有輸入需在台股決策點前已知。 | 檢查 overnight context 是否改善候選條件。 | src/astraquant/research/technical_components.py::overnight_market_context | tests/test_observation_components.py::test_overnight_context_requires_explicit_premarket_columns | 無 | DEFERRED（owner 暫緩）：缺可驗 known_at 的 canonical 夜盤/海外來源與跨市場時區/假日映射。 | 無 | 無 | 無 | 有 | 有 | 無 | 無 | NONE | FULL | 無 |
| L1-X05 | O'Neil 長期趨勢結構 | repo 既有 | close>fast SMA、fast>slow、fast/slow 皆較 slope_lookback 前上升，並限制 fast/slow spread。 | 作為長期趨勢結構 filter。 | src/astraquant/research/technical_components.py::long_term_trend_structure | tests/test_technical_components.py | SOURCE_ONEIL_TAIWAN_SWEEP.md | 無獨立 full-trade 結論；現有產物是 candidate-level surface。 | L1-001 | 有 | 有 | 有 | 有 | 有 | 有 | CANDIDATE | NA | 無 |
| L1-X06 | EMA9 回踩後確認 | USER_PROVIDED_TRANSCRIPT | 原文只登錄「回踩 EMA9 後確認」作為觸發概念；日線版為研究改編，不能反推為影片完整原法。 | 檢查 EMA9 pullback/reclaim 是否可作為獨立進場觸發候選。 | 未實作；_ema_by_ticker 可重用 EMA 計算骨架，但現有 pullback_reclaim 使用 SMA，不能視為 exact evaluator。 | 無 | 無 | 待凍結 touch 定義（low/close、容忍帶）、confirmation 條件、同 bar/次 bar、EMA 初始化/暖機、缺值、available_at 與成交時點；影片 5/15 分鐘版本另走 intraday lineage。EMA 計算與資料契約為共用依賴，不要求先完成 L2-T09。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | SIMPLIFIED | 原文：回踩 EMA9 後確認；機械化選擇：日線改編可獨立定義；未定義：確認規則與 timing。L1-014 僅供結構參考，不構成前置依賴。 |
| L1-X07 | EMA9／EMA20 交叉 | USER_PROVIDED_TRANSCRIPT | 原文登錄 EMA9／EMA20 交叉概念；尚未核定 bullish/bearish 方向、cross 等號邊界、5/15 分鐘或日線的 exact event。 | 檢查短中期 EMA 交叉是否形成候選觸發。 | 未實作；_ema_by_ticker 可重用 EMA 計算骨架；MA_GOLDEN_CROSS 為 SMA，不可代替。 | 無 | 無 | 待凍結 EMA 初始化/暖機、cross 方向與首次穿越定義、缺值、時間框架、available_at/成交時點；日線與 5/15 分鐘不得混為同一版本。EMA 計算與資料契約為共用依賴，不要求先完成 L2-T09。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | SIMPLIFIED | 原文：EMA9/EMA20 交叉；機械化選擇：日線版本另立 lineage；未定義：方向與事件邊界。L1-008 僅為 SMA cross 對照，不構成前置依賴。 |

## 表二：L2 條件過濾

### 概念數拆分

- 技術狀態：26 概念 = 趨勢位階 3 + 250 日位置 2 + 波動 3 + Bollinger 3 + 量能 5 + RSI 3 + KD 2 + MACD/CCI/Williams 3 + EMA9 日線方向 1 + EMA9/session VWAP 盤中同向 1。
- 籌碼：10 概念。
- 基本面（成長）：8 概念。
- 基本面（品質）：8 概念。
- 基本面（評價）：5 概念。
- 合計：**57 概念**。元件數 **8**；參數版本數 **10**。三者不相加。

| id | item | origin | definition | purpose | code | tests | reports | gap | depends_on | 來源資料 | PIT | 元件 | 模擬器串接 | 正式掃描 | 報告 | 掃描層級 | 原始方法涵蓋度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L2-T01 | 趨勢位階（對 MA20/60/120/250 位置、均線排列、斜率） | 本次新提 | 概念拆分=3：price-vs-MA 位階、四均線排列、各均線斜率；明示 MA20/60/120/250。 | 描述中長期 trend state。 | 未實作 | tests/test_technical_components.py（僅相關 LONG_TERM_TREND_STRUCTURE） | SOURCE_ONEIL_TAIWAN_SWEEP.md（僅相關兩均線代理） | 缺完整四均線 feature component、PIT feature matrix、canonical simulator field plumbing、正式掃描與完整報告；現有 LONG_TERM_TREND_STRUCTURE 僅兩均線代理。 | L1-X05 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-T02 | 距 250 日高低點百分比、距前高天數 | 本次新提 | 概念拆分=2：距 250 日 high/low 百分比；距 prior high 的 sessions。 | 描述長期位置與 breakout recency。 | 未實作 | 無 | 無 | ADJ 歷史可計算，但 AstraQuant 未建立 PIT feature/available_at、component、simulator plumbing、scan/report。 | L1-001 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-T03 | ATR%、20/60 日波動、波動比 | 本次新提 | 概念拆分=3：ATR%；20/60 realized volatility；20/60 volatility ratio。 | 描述絕對與相對波動狀態。 | 未實作 | 無 | 無 | 日 OHLC source 有；feature/PIT/component/simulator/scan/report 未完成。 | EX-R01 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-T04 | 布林帶寬與其歷史分位、通道內位置 | 本次新提 | 概念拆分=3：bandwidth；trailing percentile；price channel position。 | 把 Bollinger state 變成可重用連續特徵。 | 未實作 | tests/test_observation_components.py（僅相關 boolean compression） | SOURCE_BOLLINGER_DAILY_SWEEP.md（trigger/path，不是本 feature bundle） | 現有 BOLLINGER_COMPRESSION 只回傳 boolean，未提供三個要求的連續 feature bundle；需 feature matrix/PIT/sim plumbing/正式掃描。 | L1-002 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-T05 | 量能比（5/20、20/60）、20 日均額、週轉率、量縮比、上漲日量佔比 | 本次新提 | 概念拆分=5：volume ratios；20d average amount；turnover；dry-up ratio；up-day volume share。 | 描述量能/流動性結構。 | 未實作 | 無 | 無 | OHLCV/Trading_money source 有；完整 bundle 未建立，缺 PIT component/simulator/scan/report。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-T06 | RSI 各週期與差值與斜率 | 本次新提 | 概念拆分=3：RSI level；multi-period difference；RSI slope。 | 把 RSI 狀態拆成可比較 feature。 | src/astraquant/research/technical_components.py::rsi_filter；::rsi_rank；::rsi_relative（部分） | tests/test_rsi_kd_observations.py | SOURCE_RSI_DAILY_SWEEP.md（只覆蓋日線代理） | RSI level 與 fast>slow 已有，但 numeric difference/slope 未實作；整列六階段未完整。 | L1-011;L1-X03 | 有 | 有 | 無 | 有 | 有 | 有 | CANDIDATE | SIMPLIFIED | 無 |
| L2-T07 | KD 各值與高低檔鈍化天數 | owner 觀察 | 概念拆分=2：K/D values；high/low saturation duration。 | 描述 KD state 與持續性。 | src/astraquant/research/technical_components.py::_stochastic_kd；::kd_saturation_state（部分） | tests/test_rsi_kd_observations.py | 無 | K/D helper 與 boolean sustained-state 有，但未提供可重用 numeric K/D + saturation-days feature bundle；缺正式 sweep/report。 | L1-012 | 有 | 有 | 無 | 有 | 無 | 無 | NONE | FULL | 無 |
| L2-T08 | MACD 柱與斜率、CCI、威廉指標 | 本次新提 | 概念拆分=3：MACD histogram state；CCI；Williams %R。 | 補足不同動能 oscillator。 | 未實作 | 無 | 無 | 現行 macd_cross_above_zero 實際是 MACD line cross，不能代替 histogram/slope；CCI/Williams 也未實作。 | L1-009 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-T09 | EMA9 方向狀態（日線研究改編） | USER_PROVIDED_TRANSCRIPT | 概念拆分=1：close > EMA9 且 EMA9 上升。這是日線研究版本；影片文字摘要/逐字稿所述 5/15 分鐘語境另保留 lineage。 | 作為固定進場 A 的附加條件 B，檢查短期趨勢方向是否提供增量資訊。 | 未實作 exact filter；src/astraquant/research/technical_components.py::_ema_by_ticker 僅為計算 helper，generic COLUMN_THRESHOLD 也不負責產生 EMA。 | 無 | 無 | 實驗前需凍結 EMA 初始化/暖機、斜率定義與等號、待核定的 CA 一致研究價格、缺值政策、訊號 available_at 與成交時點；完整日線 close 不得假裝盤中提前可知。EMA 計算與資料契約為共用依賴，方向條件可獨立研究，不以回踩或交叉完成為前置。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | SIMPLIFIED | 原文：EMA9 方向概念；機械化選擇：日線 B=close>EMA9 且 EMA9 上升；未定義：EMA 初始化、slope/timing/missing。6/9/12 僅登錄鄰近週期，未核定掃描。 |
| L2-T10 | 價格同側於 EMA9＋session VWAP（盤中） | USER_PROVIDED_TRANSCRIPT | 概念拆分=1：原文條件是價格同時高於 EMA9 與 session VWAP，或價格同時低於 EMA9 與 session VWAP；未指定 EMA9 與 VWAP 斜率同方向。必須使用 completed 5/15 分鐘 bar 與當時可知的累積 session VWAP，不得用日線代理。 | 研究盤中價格相對 EMA9 與成交量加權價格的位置關係。 | 未實作；repo 未見 session VWAP research evaluator。 | 無 | 無 | DEFERRED：KBar source family 存在但 canonical 5/15 分鐘聚合、completed-bar available_at、session VWAP 定義/重置時點與 PIT 契約未完成；禁止以日線 close/amount 冒充。不得自行加入 EMA9/VWAP 斜率條件。 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | NONE | SIMPLIFIED | 原文：價格同時位於 EMA9 與 VWAP 上方／下方；機械化選擇：5/15 分鐘 lineage 分開；未定義：VWAP price/volume 欄位、session 邊界與價格位置比較細節。 |
| L2-C01 | 外資／投信／自營 5 日與 20 日淨買超、三大法人合計 | 本次新提 | 概念拆分=1：institutional net flow；participant 與 5/20 日為參數版本。 | 衡量法人 flow。 | 未實作 | 無 | 無 | data/inst source family 有，但 available_at/PIT 尚未完成 runtime audit，AstraQuant feature/component/simulator/scan/report 皆缺。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-C02 | 外資持股比例與變化 | 本次新提 | 概念拆分=2：foreign ownership level；change。 | 衡量外資持有狀態。 | 未實作 | 無 | 無 | 尚未確認 canonical source 欄位與 available_at；後續階段皆缺。 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-C03 | 融資餘額變化、融券餘額變化、券資比 | 本次新提 | 概念拆分=3：margin change；short balance change；short/margin ratio。 | 衡量融資融券 positioning。 | 未實作 | 無 | 無 | margin source family 有且 FUNDAMENTAL_PIT_AUDIT 驗過 available_date=date，但 feature/component/simulator/scan/report 未建。 | 無 | 有 | 有 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-C04 | 借券賣出餘額變化 | 本次新提 | 概念拆分=1：securities-lending short balance change。 | 衡量借券賣壓。 | 未實作 | 無 | 無 | 未確認 canonical 欄位與 PIT；其餘階段皆缺。 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-C05 | 千張大戶持股比例與四週變化 | 本次新提 | 概念拆分=2：large-holder level；4-week change。 | 衡量大戶 ownership stability。 | 未實作 | tests/test_universe_components.py（僅相關 STABLE pool fixture） | 無 | STABLE pool 只消費 standardized large_holder 欄位，AstraQuant 尚未建立 source→feature 的 canonical producer/PIT；缺正式 scan/report。 | EX-R01 | 無 | 無 | 無 | 有 | 無 | 無 | NONE | NA | 無 |
| L2-C06 | 當沖比例 | 本次新提 | 概念拆分=1：day-trade ratio。 | 衡量短線交易占比。 | 未實作 | 無 | 無 | canonical source/available_at 未確認；後續階段皆缺。 | 無 | 無 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-G01 | 月營收 YoY（1月／3月均／12月均）、MoM、YoY 加速度、12月累計 YoY | 本次新提 | 概念拆分=4：revenue YoY；MoM；YoY acceleration；12m cumulative YoY；YoY 另有 1m/3m/12m 版本。 | 衡量營收成長速度與加速度。 | 未實作 | 無 | 無 | month_revenue source/PIT 已 audit；feature producer/component/simulator/scan/report 未建。 | EX-R02 | 有 | 有 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-G02 | EPS YoY（單季／四季均）、EPS QoQ、單季營收 YoY | 本次新提 | 概念拆分=3：EPS YoY；EPS QoQ；quarterly revenue YoY。 | 衡量季度成長。 | 未實作 | 無 | 無 | financials source/PIT 已 audit，但 exact feature producer/component/simulator/scan/report 未建。 | 無 | 有 | 有 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-G03 | EPS 連續成長季數 | repo 既有 | 概念拆分=1：eps_yoy_positive_streak；EARNINGS_STREAK 支援門檻 2/3/4 季。 | 衡量 earnings growth persistence。 | src/astraquant/research/universe_engine.py::_earnings_streak_pool | tests/test_universe_components.py | 無 | pool evaluator 已有，但 canonical source→eps_yoy_positive_streak producer 未接；因此正式 scan/report 未完成。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | NA | 無 |
| L2-Q01 | 毛利率與年增、營益率與年增、淨利率 | 本次新提 | 概念拆分=3：gross margin；operating margin；net margin；前兩者含 YoY delta。 | 衡量獲利品質。 | 未實作 | 無 | 無 | financials source/PIT 有，但 feature producer/component/simulator/scan/report 未建。 | EX-R02 | 有 | 有 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-Q02 | ROE、ROA、營運現金流對淨利比 | 本次新提 | 概念拆分=3：ROE；ROA；operating cash flow/net income。 | 衡量資本效率與盈餘品質。 | 未實作 | tests/test_universe_components.py（僅相關 FUNDAMENTAL_FLOOR fixture） | 無 | financials source/PIT 有；FUNDAMENTAL_FLOOR 只消費 roe_4q_avg，未建立本完整 bundle。 | EX-R02 | 有 | 有 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-Q03 | 存貨週轉變化、負債權益比 | 本次新提 | 概念拆分=2：inventory turnover change；debt/equity。 | 衡量營運效率與槓桿。 | 未實作 | tests/test_universe_components.py（僅相關 FUNDAMENTAL_FLOOR debt_ratio） | 無 | balance/financial source 有；PIT audit 支援 financials，但 exact feature/component 未建；debt_ratio 不能等同 debt/equity。 | EX-R02 | 有 | 有 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-V01 | 本益比自身三年分位、股價淨值比自身三年分位 | 本次新提 | 概念拆分=2：PE own-history percentile；PB own-history percentile；window=3 years。 | 衡量自身估值位置。 | 未實作 | 無 | 無 | stock_per source family 有，但 available_at/PIT 尚未 audit；feature/component/simulator/scan/report 未建。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L2-V02 | 殖利率、本益比相對同業、股價淨值比相對同業 | 本次新提 | 概念拆分=3：dividend yield；PE relative industry；PB relative industry。 | 衡量收益率與同業相對估值。 | 未實作 | 無 | 無 | valuation/dividend/industry source families存在，但跨源 available_at 與 feature join 尚未驗；後續階段皆缺。 | L3-G01 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |

## 表三：L3 族群與背景

### 概念數拆分

- 族群：PIT 產業別 / 市值級距 / 流動性級距 / 波動特性分群 = 4；主題名單 = 1。
- 個股相對強度：相對強度 = 1；beta / 大盤相關性 / beta-residual volatility = 3。
- 產業層級：產業相對大盤強度 / 全市場強度排名 = 2。
- 市場層級：大盤對 MA200 / 大盤波動 / 大盤位階 / 大盤 EMA9 方向 = 4。
- 合計：**15 概念**。元件數 **2**；參數版本數 **2**。三者不相加。

| id | item | origin | definition | purpose | code | tests | reports | gap | depends_on | 來源資料 | PIT | 元件 | 模擬器串接 | 正式掃描 | 報告 | 掃描層級 | 原始方法涵蓋度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L3-G01 | PIT 產業別、市值級距、流動性級距、波動特性分群 | 本次新提 | 概念拆分=4：PIT industry；market-cap tier；liquidity tier；volatility cluster。 | 建立可跨時期比較的群組背景。 | src/astraquant/research/universe_engine.py::_all_pool（僅流動性 top-fraction 部分） | tests/test_universe_components.py | 無 | industry_pit 與 market_value/source price 存在；但官方產業 evaluator 尚未實作，市值級距/波動 clustering 未實作；整列 PIT/component 不完整。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L3-G02 | 主題名單（軍工航太、AI伺服器、技術護城河等） | owner 觀察 | 概念拆分=1：dated theme membership；每 member 必須 from/to/source。 | 建立 owner-defined theme universe 且避免現況回填。 | src/astraquant/research/universe_engine.py::_theme_group_mask；::_industry_theme_pool | tests/test_theme_universe.py；tests/test_universe_components.py | 無 | 軍工航太有 example；其他主題若無 dated membership 檔即不可推定。缺正式 cross-theme scan/report。 | 無 | 有 | 有 | 有 | 有 | 無 | 無 | NONE | FULL | 無 |
| L3-R01 | 個股相對強度：對所屬產業、對大盤（20/60/120 日） | 本次新提 | 概念拆分=1：relative strength；benchmark={industry,market}、horizon={20,60,120} 為參數版本。 | 衡量個股相對背景強度。 | 未實作 | 無 | 無 | price/index/industry source 有，但 PIT-safe benchmark join、feature component、simulator、scan/report 未建。 | L3-G01 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L3-R02 | beta、與大盤相關性、剔除 beta 後殘差波動 | 本次新提 | 概念拆分=3：beta；market correlation；beta-residual volatility。 | 描述市場暴露與 idiosyncratic risk。 | 未實作 | 無 | 無 | source price/index 有；window/estimator/available_at 未定義，後續階段皆缺。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L3-I01 | 產業相對大盤強度、產業在全市場強度排名 | 本次新提 | 概念拆分=2：industry-vs-market RS；cross-industry rank。 | 衡量產業 leadership。 | 未實作 | 無 | 無 | PIT industry/source index 有；aggregation、PIT feature、component、simulator、scan/report 未建。 | L3-G01 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L3-M01 | 大盤對 200 日均線、大盤波動、大盤位階 | 本次新提 | 概念拆分=3：index vs MA200；market volatility；market position/regime。 | 建立市場層級背景。 | 未實作 | 無 | 無 | TAIEX source 有，但 feature/available_at/component/simulator/scan/report 未建。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | NA | 無 |
| L3-M02 | 大盤 EMA9 方向背景（日線研究版本） | USER_PROVIDED_TRANSCRIPT／研究改編 | 概念拆分=1：將 EMA9 方向狀態套用於大盤，與個股 L2-T09 分開 lineage；不宣稱影片原文已指定相同大盤規則。 | 作為市場背景版本，避免把個股條件與大盤條件混成同一元件。 | 未實作 exact market evaluator；_ema_by_ticker 只提供 EMA 計算骨架。 | 無 | 無 | 待指定 benchmark/index series、EMA 初始化/暖機、斜率、缺值、CA/price semantics（如適用）、available_at 與成交時點。 | L2-T09;L3-M01 | 有 | 無 | 無 | 無 | 無 | 無 | NONE | SIMPLIFIED | 原文與研究改編分離：個股 EMA9 概念來自 USER_PROVIDED_TRANSCRIPT；大盤套用為待核定研究版本。 |

## 表四：出場

計數口徑：**「MA 與 EMA 分開計為 9 項待補；若合併 MA／EMA 則為 8 項。本表採分開計。」**

目前：**2 列已接上 canonical simulator；9 列待補。**

| id | item | origin | definition | purpose | code | tests | reports | gap | depends_on | 來源資料 | PIT | 元件 | 模擬器串接 | 正式掃描 | 報告 | 掃描層級 | 原始方法涵蓋度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EX-E01 | 固定停損 | repo 既有 | entry 後以 stop_fraction 形成 canonical stop policy；目前 executable config 使用固定 stop。 | 限制單筆 downside。 | src/astraquant/research/exit_engine.py::_fixed_stop_target；src/astraquant/portfolio/policy.py::PortfolioPolicyConfig | tests/test_config_engine.py；tests/test_strategy_simulator.py | SOURCE_PARAMETER_NEIGHBORHOOD.md | 已接 simulator 且曾有 full-trade 歷史 sensitivity；該歷史報告屬已接觸資料，不是獨立 OOS。 | 無 | 有 | 有 | 有 | 有 | 有 | 有 | FULL_TRADE | NA | 無 |
| EX-E02 | 時間／最長持有 | repo 既有 | 持有達 max_hold_sessions 時由 canonical policy 產生 exit。 | 限制持有期限。 | src/astraquant/research/exit_engine.py::_time_exit；src/astraquant/portfolio/policy.py::PortfolioPolicyConfig | tests/test_config_engine.py；tests/test_strategy_simulator.py | SOURCE_PARAMETER_NEIGHBORHOOD.md | 已接 simulator 且曾有 full-trade 歷史 sensitivity；該歷史報告屬已接觸資料，不是獨立 OOS。 | 無 | 有 | 有 | 有 | 有 | 有 | 有 | FULL_TRADE | NA | 無 |
| EX-E03 | 固定停利 | repo 既有 | 未定義；schema 可帶 target_pct，但目前非 null 會明確 UnsupportedComponentError。 | 測試固定 profit target exit。 | 未實作 | 無 | 無 | exit evaluator/simulator wiring/sweep/report 未實作；不得把 schema 宣告視為可用。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | FULL_TRADE | NA | 無 |
| EX-E04 | 跌破 MA | repo 既有 | 未定義 | 測試 MA break exit。 | 未實作 | 無 | 無 | 缺 exit timing/PIT、component、simulator wiring、full-trade scan/report。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | FULL_TRADE | NA | 無 |
| EX-E05 | EMA20 下方停損／跌破版研究改編 | repo 既有；USER_PROVIDED_TRANSCRIPT | 逐字稿原文是「停損放在 EMA20 下方」；這描述 stop placement，不等同「收盤跌破 EMA20 才出場」。收盤跌破 EMA20 僅登錄為可另行核定的研究改編。 | 保留 EMA20 作為停損位置參考的原文語意，並把 close-below-EMA20 與其他機械出場版本分離。 | 未實作；schema 有 EMA_BREAK 名稱，但 exit registry 無 evaluator，既有 MA_BREAK 僅支援 SMA。 | 無 | 無 | 停損距 EMA20 多遠、是否隨 EMA 更新、何種價格觸發、觸發後如何成交、決策與 fill timing 均待定；收盤跌破版若研究須另凍結，不得反寫成逐字稿原法。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | FULL_TRADE | SIMPLIFIED | 原文：stop placement 在 EMA20 下方；研究改編：close 跌破 EMA20。兩者不得混為同一規則。 |
| EX-E06 | 跌破布林中線 | repo 既有 | 未定義 | 測試 Bollinger midline break exit。 | 未實作 | 無 | 無 | 缺 exit timing/PIT、component、simulator wiring、full-trade scan/report。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | FULL_TRADE | NA | 無 |
| EX-E07 | ATR 移動停利 | repo 既有 | 未定義 | 測試 volatility-scaled trailing exit。 | 未實作 | 無 | 無 | 缺 ATR exit definition/timing、component、simulator wiring、full-trade scan/report。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | FULL_TRADE | NA | 無 |
| EX-E08 | 百分比移動停利 | repo 既有 | 未定義 | 測試 percent trailing exit。 | 未實作 | 無 | 無 | 缺 trail update/timing semantics、component、simulator wiring、full-trade scan/report。 | 無 | 有 | 無 | 無 | 無 | 無 | 無 | FULL_TRADE | NA | 無 |
| EX-E09 | Donchian 通道出場 | repo 既有 | 未定義 | 測試 Donchian channel exit。 | 未實作 | 無 | 無 | 缺 channel lookback/timing、component、simulator wiring、full-trade scan/report。 | L1-017 | 有 | 無 | 無 | 無 | 無 | 無 | FULL_TRADE | NA | 無 |
| EX-E10 | 一目均衡出場 | repo 既有 | 未定義 | 測試 Ichimoku exit。 | 未實作 | 無 | 無 | 缺 exact rule/timing、component、simulator wiring、full-trade scan/report。 | L1-016 | 有 | 無 | 無 | 無 | 無 | 無 | FULL_TRADE | NA | 無 |
| EX-E11 | RSI 失守（老手原始條件） | owner 觀察 | 原始條件：entry 後 RSI 失守 50 為 exit；精確 timeframe/decision timestamp 尚未凍結。 | 補齊 RSI 原始方法出場。 | 未實作 | 無 | 無 | 缺原始 timeframe source/PIT 與 exit evaluator/simulator/full-trade scan/report。 | L1-X03 | 無 | 無 | 無 | 無 | 無 | 無 | FULL_TRADE | NA | 無 |

## EMA9 來源、lineage 與待核定研究（不另建 inventory）

來源代號 EMA9-SRC-001：USER_PROVIDED_TRANSCRIPT，為 owner 提供的 Kathy Lien 影片文字摘要及逐字稿；目前沒有影片 URL，未核對原片。以下登錄只保存可研究概念，不宣稱為任何人的完整原法，也不宣稱已驗證有效。

共同依賴說明：EMA 計算方法、暖機／缺值與可信資料／時間契約是 L2-T09、L1-X06、L1-X07、L2-T10 的共用基礎，但不構成這些研究項目彼此的前置依賴；方向條件、回踩與交叉可各自獨立定義與研究。

版本 lineage：
- EMA9-INTRADAY-5M15M-001：影片文字材料的 5／15 分鐘語境；盤中項目必須等待 canonical 分 K、completed-bar available_at 與 session VWAP 契約，不用日線代理。
- EMA9-DAILY-ADAPT-001：日線研究改編；只繼承 EMA9 概念，不繼承盤中 timing 或效果主張。完整日線 close 資訊只能在其可用時間之後使用。

語意邊界：

| research_id | 原文有說 | 為機械化必須補的選擇 | 仍未定義 |
|---|---|---|---|
| L2-T09 | EMA9 方向；本輪登錄 B=close>EMA9 且 EMA9 上升 | EMA 初始化/暖機、EMA9 上升的 slope interval/equality、日線 available_at/成交對齊 | 缺值/歷史 gap 政策、最終 CA 研究座標核定 |
| L1-X06 | 回踩 EMA9 後確認 | touch 使用 low 或 close、容忍帶、確認發生在同 bar 或後續 bar | exact confirmation、5/15m 與日線各自 timing |
| L2-T10 | 價格同時高於 EMA9 與 session VWAP，或同時低於兩者；原文未指定兩條線的 slope 同向 | completed 5/15m bar、VWAP 累積起點與 price/volume 欄位、價格位置比較邊界 | canonical intraday source/PIT、session 邊界；不得自行加入 EMA9/VWAP 斜率條件 |
| L1-X07 | EMA9／EMA20 交叉 | cross 方向、等號邊界、first-cross/state | exact timeframe 與成交 timing |
| EX-E05 | 停損放在 EMA20 下方 | 停損距離、是否隨 EMA 更新、觸發價格與成交方式；close 跌破 EMA20 僅可作另行核定的研究改編 | exact stop update/trigger/fill timing |
| HYP-EMA9-001 | 第二次跌破／站回的敘述 | 若未來研究，需先定義「第二次」的事件計數、reset、break/reclaim 序列與 timeframe | 未機械化；不宣稱高勝率或有效 |

### 第一個待核定實驗：EXP-EMA9-001

固定既有進場 A，B = L2-T09 的日線 EMA9 方向條件；在相同母體、相同出場、相同成本下只比較 A、A+B、A 且非 B。不同时更動進場與出場，不挑最佳搭配。報告預先規劃：機會數、每筆淨期望值、勝率、平均賺賠、獲利集中度、相依性不確定性。

執行前必須凍結：EMA 初始化/暖機、CA 價格座標、斜率定義、缺值政策、訊號可用時間、成交時點；日線完整收盤資訊不得用於同日盤中提前成交。EMA 6／9／12 僅登錄為待核定鄰近週期方案，本項不掃描。

元件／資料依賴對照：

| research_id | 最小資料依賴 | 可重用部分 | exact 缺口 |
|---|---|---|---|
| L2-T09 | 待核定的 CA 一致研究價格 + 可信 session/availability contract | _ema_by_ticker 計算骨架 | EMA9 state filter、slope/missing/available_at 契約 |
| L1-X06 | 待核定的 CA 一致研究價格或 completed 5/15m OHLC + 共用 EMA 計算/資料契約 | _ema_by_ticker；L1-014 僅可參考結構 | EMA pullback/reclaim exact evaluator |
| L1-X07 | 同 timeframe 的待核定研究價格 + 共用 EMA 計算/資料契約 | _ema_by_ticker | EMA cross evaluator；SMA MA_GOLDEN_CROSS 不可代替 |
| L2-T10 | completed 5/15m OHLCV + session VWAP inputs + 共用 EMA 計算/資料契約 | 無 exact component | canonical intraday aggregation/PIT + VWAP evaluator |
| L3-M02 | 已指定的大盤 series + session/availability contract | EMA helper 概念可重用 | market EMA9 context evaluator |
| EX-E05 | 待核定的 EMA20 stop-placement 座標 + execution timing | exit contract 框架 | stop distance/update/trigger/fill 契約；close-break 研究改編若核定再另接 evaluator |
| EXP-EMA9-001 | 上述 L2-T09 + 已凍結 A/母體/出場/成本 + 時期治理 | 既有 research governance | 尚未 preregister/freeze，不得執行效果 |

正式測試若日後獲准，仍必須遵守既有資料 gate、EPOCH_GOVERNANCE 與多重檢定規格。

## 清單外 repo 既有元件

依「重複項目合併、共用以 depends_on 連結」規則，已在 L1/L2/L3/表外項目中出現的 registry 元件不再重複列。剩餘清單外既有元件補列數：**4**。

| id | item | origin | definition | purpose | code | tests | reports | gap | depends_on | 來源資料 | PIT | 元件 | 模擬器串接 | 正式掃描 | 報告 | 掃描層級 | 原始方法涵蓋度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EX-R01 | STABLE universe pool | repo 既有 | 同時消費 downside_rs_ratio、rv60_percentile、max_drawdown_ratio_to_index、large_holder_fraction/change、dividend streak、turnover_ratio_percentile 的 composite universe filter。 | 重用既有穩定型 universe component，不拆成假裝已存在的 L2 feature producers。 | src/astraquant/research/universe_engine.py::_stable_pool | tests/test_universe_components.py | 無 | 清單外既有元件；只消費 standardized 欄位，沒有負責產生那些 feature；source→feature/PIT producer 仍是缺口。 | 無 | 不適用 | 不適用 | 有 | 有 | 無 | 無 | NONE | NA | 清單外既有元件 |
| EX-R02 | FUNDAMENTAL_FLOOR universe pool | repo 既有 | 以 max loss streak、debt_ratio、financial exemption、revenue decline streak、roe_4q_avg 做 composite fundamental floor。 | 重用既有基本面 floor，不誤記成完整 L2 growth/quality feature matrix。 | src/astraquant/research/universe_engine.py::_fundamental_floor_pool | tests/test_universe_components.py | 無 | 清單外既有元件；依賴預先 standardized features，未提供完整 L2 features。 | 無 | 不適用 | 不適用 | 有 | 有 | 無 | 無 | NONE | NA | 清單外既有元件 |
| EX-R03 | COLUMN_THRESHOLD generic filter | repo 既有 | 對指定 numeric panel column 套 min/max threshold。 | 提供已存在 feature 欄位的通用條件器。 | src/astraquant/research/technical_components.py::column_threshold | 無 | 無 | 清單外既有元件；不負責來源/PIT/feature 計算，不能代替任何尚未實作的 L2/L3 feature。 | 無 | 不適用 | 不適用 | 有 | 有 | 無 | 無 | NONE | NA | 清單外既有元件 |
| EX-R04 | COLUMN_VALUE generic ranking | repo 既有 | 直接回傳指定 numeric panel column 作 ranking value。 | 提供已存在 feature 欄位的通用 ranking adapter。 | src/astraquant/research/technical_components.py::column_value | 無 | 無 | 清單外既有元件；不負責來源/PIT/feature 計算。 | 無 | 不適用 | 不適用 | 有 | 有 | 無 | 無 | NONE | NA | 清單外既有元件 |

## 統計摘要

| 區塊 | 概念／列數 | 元件數／完成數 | 參數版本／其他 |
|---|---:|---:|---:|
| L1 | 17 列 | 來源17；PIT15；元件15；模擬器15；正式掃描5；報告5 | 表外7 |
| L2 | 57 概念 | 8 元件 | 10 參數版本 |
| L3 | 15 概念 | 2 元件 | 2 參數版本 |
| 出場 | 11 列 | 2 已接 simulator | 9 待補 |
| 清單外 repo 既有元件 | 4 列 | 4 元件 | 不與 L2/L3 概念數相加 |

本表只盤點現況；不以「已實作」代替「已驗證可用」，也不把 candidate-level 掃描升格為 full-trade 證據。
