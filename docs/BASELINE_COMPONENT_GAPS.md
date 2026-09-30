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
| 固定百分比停損停利 | `FIXED_STOP_TARGET` | 需確認同時支援停損與停利兩側 |
| ATR 移動停利 | `ATR_TRAILING` | 週期與倍數為參數，李佛摩 14/3.0 在範圍內 |
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

**COLUMN_THRESHOLD 的存在改變了整份清單的結論。** 下方 C 類裡的多項
（相對強度、N 日漲幅、距高點百分比、區間位置、均量下限）本質上都是「算一個數、設門檻」，
若 queue 第 5 項的 PIT 特徵矩陣把它們產成欄位，就**不需要新的 evaluator**。
因此現在不應開工實作這些元件——會與第 5 項重複開發。

## C. 確實缺 evaluator（且不是欄位門檻能表達的）

| 元件 | 用在 | 說明 |
|---|---|---|
| `PRICE_ABOVE_MA` | 李佛摩、林區、巴菲特、美股隔夜 | 單條均線的狀態判定。若特徵矩陣產出 ma_N 欄位，可退化為 COLUMN_THRESHOLD 比較，需確認引擎是否支援欄位對欄位比較 |
| `BREAK_N_DAY_LOW`（出場） | 李佛摩(20)、動能(10) | 出場端沒有任何對應元件 |
| `FIXED_PCT_TARGET`（出場） | 麥克連 +10% | 視 FIXED_STOP_TARGET 是否已含停利側而定 |
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
B 類 4 項可重用計算需改介面、C 類 10 項確實缺 evaluator、D 類 3 項缺資料。

## 建議：只推薦一套完整基線 — 李佛摩

理由是它相對現有引擎的**最小新增能力最少**：

| 環節 | 狀態 |
|---|---|
| 觸發：突破 60 日高 | ✅ `N_SESSION_HIGH` lookback=60（採引擎的首次穿越語意，報告註明） |
| 條件：價 ≥ MA120 | ❌ 缺 `PRICE_ABOVE_MA`。若第 5 項特徵矩陣產出 ma_120 欄位且引擎支援欄位比較，可降為零新增 |
| 出場：ATR(14) × 3.0 | ✅ `ATR_TRAILING` |
| 出場：跌破 20 日低 | ❌ 缺 `BREAK_N_DAY_LOW` |

**最小新增：2 個 evaluator**（其中 1 個可能被特徵矩陣消化掉）。
相較之下短線動能要 3 個、Qullamaggie 要 8 個以上。

與 VCP Round 1 的比較條件必須完全對齊，否則數字不可比：
E1 2016-01-04~2021-12-31、同一 all_liquid 母體與 P2-060 凍結排除名單、
同一成本模型（0.1425%×2 + 0.3% 稅 + 單邊 0.1% 滑價）、次一共同交易日開盤進場、
每股票同時最多一筆持倉、無跨股票資金競爭、期末未平倉另列。

**本項不啟動實作，不跑 workflow，不插隊第 5 項。** 待第 5 項交付後，
先確認特徵矩陣產出哪些欄位，再決定 `PRICE_ABOVE_MA` 是否還需要獨立 evaluator。
