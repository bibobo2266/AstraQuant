# Baseline 方法庫 — 與現有引擎對帳

修訂 2026-09-30。**取代同日稍早的版本**，該版本錯誤地聲稱「引擎只有 VCP 一個觸發」，
並據此列出 18 個缺口。那個數字未經對帳，不可沿用。

實查 registry（`signal_engine.py` / `exit_engine.py`）結果：
**已註冊 16 個觸發、7 個過濾、2 個排序、4 個出場，合計 29 個元件。**

已註冊觸發：N_SESSION_HIGH、GAP_UP、VOLUME_SPIKE、MA_GOLDEN_CROSS、MACD_CROSS_ABOVE_ZERO、
KD_LOW_ZONE_GOLDEN_CROSS、RSI_CROSS、RSI_PULLBACK_RECLAIM、KD_SATURATION_RELEASE、
BOLLINGER_UPPER_BREAK、BOLLINGER_COMPRESSION_BREAKOUT、VCP_BREAKOUT、VCP_THREE_SEGMENT、
ANCHOR_REVERSAL、PULLBACK_RECLAIM、CONSECUTIVE_UP_DAYS
已註冊過濾：RSI、LONG_TERM_TREND_STRUCTURE、BOLLINGER_COMPRESSION、RSI_RELATIVE、
KD_SATURATION_STATE、OVERNIGHT_MARKET_CONTEXT、COLUMN_THRESHOLD
已註冊出場：FIXED_STOP_TARGET、TIME_EXIT、ATR_TRAILING、MA_BREAK

## A. 可直接重用（改 config 即可，無需寫程式）

| baseline 需要 | 現有元件 | 映射 |
|---|---|---|
| 突破 N 日高 | `N_SESSION_HIGH` | `lookback` = 20 / 60 / 250 |
| 固定百分比停損 | `FIXED_STOP_TARGET` | 僅 `stop_pct`（自進場價的比例）。**停利側未實作**：傳 `target_pct` 會拋 `UnsupportedComponentError` |
| ATR 移動停利 | `ATR_TRAILING` | 追蹤持倉最高價並只上移。**不可用來表達「自進場價 −N×ATR」的停損**（見下方 C 類 `ATR_FROM_ENTRY_STOP`）。且 smoothing 限 WILDER、trigger_field 限 CLOSE、execution 限 NEXT_OPEN |
| 跌破均線出場 | `MA_BREAK` | 週期為參數 |

**但 `N_SESSION_HIGH` 與來源實作有語意差異，必須記錄、不得默默對齊：**
- 引擎：`close > prior_high` 且 `前一日收盤 ≤ 前一日的 prior_high`（要求當日才首次穿越）
- 來源（李佛摩／歐尼爾／動能）：`price >= prior_high`，無首次穿越要求，且為 `>=`

差異會改變樣本數與進場時點。**本輪不改引擎去遷就來源**，改以「引擎版」執行並在報告註明；
若要測來源版，登記為另一個參數版本。

## B. 可重用計算，但需新增用途或介面

| 需要 | 現況 | 需要做的事 |
|---|---|---|
| 量倍數當**條件** | `VOLUME_SPIKE` 已存在，數學相同（前 N 日均量，分母不含當日） | 目前只註冊為 trigger，需另註冊為 filter。計算不必重寫 |
| 均線排列 | `LONG_TERM_TREND_STRUCTURE` 有 fast/slow + 斜率 + spread 區間 | 它**強制要求兩條均線皆上彎**，比來源的單純 `fast ≥ slow` 嚴格。兩者不等價：要嘛新增寬鬆版，要嘛承認用的是嚴格版並註明 |
| 最長持有 | `TIME_EXIT` 已存在 | Qullamaggie 是「60 日**無進展**才出場」，不是單純時間到。現有 TIME_EXIT 不等價，需新增無進展判定或改以別的方式表達 |
| 任何已成為 panel 欄位的數值條件 | `COLUMN_THRESHOLD` 是通用欄位門檻 filter | **這是最重要的一條**：只要特徵矩陣把某個值算成欄位，就不必寫新 evaluator，用 COLUMN_THRESHOLD 下 min/max 即可 |
| 價格相對單一 MA 條件 | 第 5 項已有 `close_to_ma120 = adjusted_close / SMA120 - 1`；`COLUMN_THRESHOLD min=0.0` 數值語意正確 | **計算已存在，但仍缺串接**：`ResearchConfigEngine` 只吃 caller-supplied panel，現行 canonical runner 尚未自動 join 第 5 項 feature parquet；不需新增 `PRICE_ABOVE_MA` evaluator |

**COLUMN_THRESHOLD 的存在改變了整份清單的結論。** 下方 C 類裡的多項
（相對強度、N 日漲幅、距高點百分比、區間位置、均量下限）本質上都是「算一個數、設門檻」，
若 queue 第 5 項的 PIT 特徵矩陣把它們產成欄位，就**不需要新的 evaluator**。
因此現在不應開工實作這些元件——會與第 5 項重複開發。

## C. 確實缺 evaluator（且不是欄位門檻能表達的）

| 元件 | 用在 | 說明 |
|---|---|---|
| `BREAK_N_DAY_LOW`（出場） | 李佛摩(20)、動能(10) | 出場端沒有任何對應元件 |
| `FIXED_PCT_TARGET`（出場） | 麥克連 +10% | 已確認：`FIXED_STOP_TARGET` 的停利側未實作，確實缺 |
| `ATR_FROM_ENTRY_STOP`（出場） | 60 日突破基線（3×ATR） | 自**進場價**減 N×ATR 的停損。`ATR_TRAILING` 追蹤最高價、`FIXED_STOP_TARGET` 用固定比例，兩者皆無法表達 |
| `MA_BIAS_EXIT`（出場） | 麥克連（離 MA5 正乖離 ≥10%） | — |
| `PARTIAL_TAKE_PROFIT`（出場） | Qullamaggie（浮盈 1R 賣 1/3、餘額移成本） | 會動到部位模型，是這批唯一的結構性改動 |
| `MA_BIAS_PERCENTILE` | 地板股 | 乖離的歷史分位須為 PIT expanding 分布 |
| `CONSOLIDATION_ATR_CONTRACTION` | Qullamaggie | 見下方「兩種收縮算法」 |
| `ENTRY_DAY_STRENGTH_CAP` | Qullamaggie | 見下方「追價上限」 |
| `EXCLUDE_LIMIT_UP` | Qullamaggie | 台股專屬，會影響相當比例樣本 |
| `WEEKLY_TREND_CONFIRM` | 麥克連 | 週線重採樣規則未定 |

## D. 缺 PIT 資料（不是寫程式能解決）

| 元件 | 缺什麼 |
|---|---|
| `INSTITUTIONAL_NET_BUY_STREAK` | 三大法人買賣超日資料 |
| `TRUST_VOLUME_RATIO_STREAK` | 投信買超股數／當日成交量 |
| `FUNDAMENTAL_THRESHOLD` | ROE／FCF／PE／PB／負債比／毛利／PEG，須為發布日 PIT |

`US_OVERNIGHT_RETURN` **不在此類**：panel 已含 `nasdaq_return`、`sox_return`、
`tsm_adr_return`、`twse_prev_close`，且已註冊 `OVERNIGHT_MARKET_CONTEXT` filter。
需確認的是介面（能否當觸發用、欄位定義與可用時間），不是資料有無。

## 已修正的無證據結論

以下為同日稍早版本中未經驗證的說法，一併更正：

**追價上限**：ATR 版本**是待測的替代方案，不是更合理的方案**。要測之前必須先定義分子——
是「自昨收的漲幅」還是「高於 pivot 的幅度」；並確認百分比與 ATR 的價格口徑一致
（還原價或 RAW）、以及該 ATR 在進場日開盤前是否已知。未定義前無法實作，也無法比較。

**兩種收縮算法**：VCP 三段嚴格版與 Qullamaggie 的 ATR 前後半段版是**替代版本**，
**不是互斥訊號**——同一檔同一天可能兩者皆成立。要比較須各自固定網格分別執行，
並回報兩者訊號集合的交集大小。

**美股隔夜與台指夜盤**：兩者可能相關，但**不能當成可共用或互相獨立驗證**。
夜盤產出是台指期，us_overnight 用的是美股代理報酬，口徑與可用時間都不同。
列為可能相關的背景資訊。

**元件數**：不再使用未對帳的「18 個」。對帳後為：A 類 4 項可直接重用、
B 類 5 項可重用計算需改介面、C 類 10 項確實缺 evaluator、D 類 3 項缺資料。

## Config 狀態：四件事分開記錄

先前把「沒跑回測」寫成「語意相容 0/12」是錯的 —— 那是把「還沒做」講成「已判定不相容」。
四件事各自獨立：

| 層次 | 狀態 |
|---|---|
| 1. schema 載入 | **12/12 通過**（移除 provenance 後） |
| 2. 元件可解析 | 觸發 4/12 可解析；filter 逐份列於 drafts 檔頭註記 |
| 3. 與來源規則是否一致 | 逐項查核中，已知差異列於 `BASELINE_SOURCE_LEDGER.md`。**不是「不一致」，是「部分已知差異、其餘未查」** |
| 4. 完整來源回測 | **未完成**。無任何一套執行過，故不得標為可執行完整策略 |

## 建議：只推薦一套完整基線 — 60 日突破基線

**不稱為「李佛摩」。** 觸發語意已採引擎版（要求首次穿越、用 `>`），與來源不同；
來源亦為第三方實作，原始著作未取得。這是一套研究端定義的基線，
名稱為 `baseline_60d_breakout_v1`，來源關聯記於 ledger。

理由是它相對現有引擎的**最小新增能力最少**：

| 環節 | 狀態 |
|---|---|
| 觸發：突破 60 日高 | ✅ `N_SESSION_HIGH` lookback=60（採引擎的首次穿越語意，報告註明） |
| 條件：價 ≥ MA120 | ⚠️ **計算已存在但仍缺串接**。第 5 項已產出原值 `close_to_ma120 = adjusted_close / SMA120 - 1`，因此正確門檻是 `COLUMN_THRESHOLD min: 0.0`；不是 `min: 1.0`，也不是 percentile ≥0。現行 canonical runner 尚未自動把 feature parquet join 進 signal panel；且精確 AFTER_SESSION_CLOSE available_at 仍為 UNKNOWN |
| 出場：自進場價 −3×ATR(14) | ❌ 缺 `ATR_FROM_ENTRY_STOP`。**不是 `ATR_TRAILING`** —— 來源基準是進場價、不隨股價上移 |
| 出場：跌破 20 日低 | ❌ 缺 `BREAK_N_DAY_LOW` |

**目前最小缺口不是 3 個 evaluator。** 已確認 `PRICE_ABOVE_MA` 不需新增 evaluator；
現況為 **2 個確實缺的 exit evaluator**（`ATR_FROM_ENTRY_STOP`、`BREAK_N_DAY_LOW`）
加 **1 個 feature artifact → canonical panel 的 hydration/join 串接工作**。
`close_to_ma120` 的缺值會被 `COLUMN_THRESHOLD` 視為 filter 不通過，但不得在報告中把 null 解讀成「價格低於 MA120」。
精確決策時點的 available_at 仍待第 5 項 review1 證據補強。

與 VCP Round 1 的比較條件必須完全對齊，否則數字不可比：
E1 2016-01-04~2021-12-31、同一 all_liquid 母體與 P2-060 凍結排除名單、
同一成本模型（0.1425%×2 + 0.3% 稅 + 單邊 0.1% 滑價）、次一共同交易日開盤進場、
每股票同時最多一筆持倉、無跨股票資金競爭、期末未平倉另列。

**本項不啟動 baseline 實作或回測。** 第 5 項已確認 `close_to_ma120` 數值語意；
剩餘工作是 feature-panel 串接與 exact decision-time availability 證據，不是新增 `PRICE_ABOVE_MA` evaluator。


## 兩種比較不可混為一談

整套基線與 VCP Round 1 並排，回答的是 **「哪一套完整方法表現如何」**。
那不等於「VCP 的收縮條件有沒有額外價值」—— 後者必須固定出場與其他條件、
**只改進場定義**，才是對收縮條件本身的檢定。

兩種比較都值得做，但結論不可互相引用：
- 完整方法比較：多個元件同時不同，差異無法歸因到任一條件
- 只改進場定義：可歸因，但只回答那一個問題

本文件推薦的「60 日突破基線」屬於前者。要做後者需另立實驗版本。
