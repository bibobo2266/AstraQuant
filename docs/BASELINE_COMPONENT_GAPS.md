# 基準庫所需元件清單

12 份進場 config 已寫入 `configs/examples/signals/baseline_*_v1.yaml`。
本清單列出引擎目前缺、必須補上才跑得動的元件。**現有引擎只有 VCP_THREE_SEGMENT 一個觸發。**

排序依「補一個解鎖幾套方法」，不是依實作難度。

## 第一優先 — 補 4 個解鎖 5 套

| 元件 | 解鎖 | 說明 |
|---|---|---|
| `BREAKOUT_N_DAY_HIGH` | 李佛摩、歐尼爾、動能、Qullamaggie | 一個元件吃三種窗口（20/60/250）。收盤突破，前高不含當日 |
| `VOLUME_MULTIPLE` | 歐尼爾、動能、Qullamaggie、地板股 | 當日量 ÷ N 日均量 ≥ 倍數。分母不含當日 |
| `PRICE_ABOVE_MA` | 李佛摩、林區、巴菲特、美股隔夜 | 收盤 ≥ SMA(N) |
| `MA_STACK` | 動能、Qullamaggie | 快線 ≥ 慢線 |

補完這四個，**李佛摩與短線動能兩套的進場即可完整跑**，其餘三套差條件層。

## 第二優先 — 出場元件（沒有這些，任何一套都收不了尾）

| 元件 | 用在 |
|---|---|
| `BREAK_N_DAY_LOW` | 李佛摩(20)、動能(10) |
| `FIXED_PCT_STOP` | 歐尼爾 −8%、動能 −5%、地板 −4%、麥克連 −7%、投信 −7%、雷浩斯 −20% |
| `FIXED_PCT_TARGET` | 麥克連 +10% |
| `MA_BIAS_EXIT` | 麥克連（離 MA5 正乖離 ≥10%） |
| `MAX_HOLD_DAYS` | Qullamaggie（60 日無進展） |
| `PARTIAL_TAKE_PROFIT` | Qullamaggie（T+3~T+5 浮盈 ≥1R 賣 1/3，餘額移到成本） |

`ATR_TRAILING` 與 `MA_BREAK` 已存在（VCP Round 1 在用），只需擴充參數範圍。
`PARTIAL_TAKE_PROFIT` 涉及分批與移動停損基準，是這批裡唯一會動到部位模型的，建議最後做。

## 第三優先 — 條件層

| 元件 | 用在 |
|---|---|
| `RETURN_OVER_N_DAYS` | Qullamaggie（60日 ≥30%、120日 ≥20%） |
| `PCT_FROM_N_DAY_HIGH` | Qullamaggie（距 60 日高 ≤10%） |
| `RANGE_POSITION` | 雷浩斯(120日下40%)、投信認養(60日下半部) |
| `RELATIVE_STRENGTH_VS_INDEX` | 歐尼爾（RS ≥1） |
| `MIN_AVG_VOLUME` | 投信認養 |
| `CONSOLIDATION_ATR_CONTRACTION` | Qullamaggie（寬鬆版收縮，與 VCP 嚴格版互斥對照） |

## 第四優先 — 台股執行細節

| 元件 | 說明 |
|---|---|
| `ENTRY_DAY_STRENGTH_CAP` | 追價上限綁 ATR 而非固定百分比。**比 VCP Round 1 的 pivot×1.05 更合理**：小型股 5% 可能只是半根 ATR，大型股 5% 是三根 |
| `EXCLUDE_LIMIT_UP` | 突破日漲停直接放棄，等次日。台股專屬，會影響相當比例的樣本 |
| `MA_BIAS_PERCENTILE` | 地板股。乖離的歷史分位必須用 PIT expanding 分布，不可用全期分布回貼 |

## 受阻 — 缺資料源

| 元件 | 缺什麼 |
|---|---|
| `INSTITUTIONAL_NET_BUY_STREAK` | 三大法人買賣超日資料 |
| `TRUST_VOLUME_RATIO_STREAK` | 投信買超股數／當日成交量 |
| `FUNDAMENTAL_THRESHOLD` | ROE／FCF／PE／PB／負債比／毛利／PEG，且須為 PIT（發布日而非財報所屬期） |
| `US_OVERNIGHT_RETURN` | 美股隔夜報酬。與現有台指夜盤產出重疊，可共用 |
| `WEEKLY_TREND_CONFIRM` | 週線重採樣規則需確認（週五收盤或最後交易日） |

籌碼與基本面四個元件依訪談表的分層本就留待後續，此處只登記，不建議現在做。

## 建議順序

1. 第一優先 4 個 + `BREAK_N_DAY_LOW` + `FIXED_PCT_STOP`
2. 先跑李佛摩與短線動能兩套完整進出場，拿到第一組可比較的基線
3. 再依結果決定往條件層或往其他方法擴充

**不建議一次把 18 個元件全建。** 理由與 VCP Round 1 相同：先跑通一套完整流程，
才知道該優先補哪幾個；照清單全建，最後用到的通常只有幾個。
