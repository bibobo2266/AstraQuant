# Baseline 方法庫 — 來源對照

以 config 名稱與版本關聯，不放進 config 本體（`SignalConfig` 設 `extra="forbid"`，
頂層額外欄位會使載入失敗；本輪不修改核心 schema）。

## 歸屬聲明

**以下全部為第三方實作，不等於原名家親自認可。**
「李佛摩」「巴菲特」「歐尼爾」「林區」「葛拉漢」「雷浩斯」等命名出自該 repo 作者，
是他們對該人物公開論述的詮釋。原始著作全文**未取得、未核對**，因此本文件
不替任何參數的原始歸因背書。Qullamaggie 同理，該檔為台股改編版，非本人發布。

參數性質一律標為 **TRANSLATED**：代表「有人在台股用過這組數字」，
不代表「這組數字有效」，也不代表「該名家本人用這組數字」。
原作者的績效宣稱不採用（多數未見 PIT、下市處理與足額成本）。

## 來源明細

| config | 來源 repo | commit | 檔案 | 位置 | 抄錄方式 |
|---|---|---|---|---|---|
| baseline_livermore_v1 | Joyen09/tw-stock-strategy-framework | aafe2bf | src/strategies/livermore.py | `DEFAULTS` | 原文抄錄 |
| baseline_oneil_v1 | 同上 | aafe2bf | src/strategies/oneil.py | `DEFAULTS` | 原文抄錄 |
| baseline_momentum_v1 | 同上 | aafe2bf | src/strategies/momentum.py | `DEFAULTS` | 原文抄錄 |
| baseline_floor_v1 | 同上 | aafe2bf | src/strategies/floor.py | `DEFAULTS` | 原文抄錄 |
| baseline_mclean_v1 | 同上 | aafe2bf | src/strategies/mclean.py | `DEFAULTS` | 原文抄錄 |
| baseline_trust_v1 | 同上 | aafe2bf | src/strategies/trust.py | `DEFAULTS` | 原文抄錄 |
| baseline_raiho_v1 | 同上 | aafe2bf | src/strategies/raiho.py | `DEFAULTS` | 原文抄錄 |
| baseline_lynch_v1 | 同上 | aafe2bf | src/strategies/lynch.py | `DEFAULTS` | 原文抄錄 |
| baseline_graham_v1 | 同上 | aafe2bf | src/strategies/graham.py | `DEFAULTS` | 原文抄錄 |
| baseline_buffett_v1 | 同上 | aafe2bf | src/strategies/buffett.py | `DEFAULTS` | 原文抄錄 |
| baseline_us_overnight_v1 | 同上 | aafe2bf | src/strategies/us_overnight.py | `DEFAULTS` | 原文抄錄 |
| baseline_qullamaggie_v1 | gpwork4u/qullamaggie-tw-backtest | 5b1cb5b | STRATEGY.md | 全文 | 散文轉譯為參數 |

commit 已固定：
- `Joyen09/tw-stock-strategy-framework` @ `aafe2bf23f587fba13ec52c6e41af97918ace097`（2026-09-22）
- `gpwork4u/qullamaggie-tw-backtest` @ `5b1cb5bb0843357373d774019a3336a1e16f18ce`（2026-05-15）

兩者皆為當日 HEAD，非發布標籤；作者日後可能改寫，引用時以上述 SHA 為準。

## 逐項改寫與語意不明處

| config | 問題 |
|---|---|
| 全部突破類 | 來源用 `price >= prior_high` 無首次穿越要求；引擎 `N_SESSION_HIGH` 要求首次穿越且為 `>`。**已知語意差異，本輪採引擎版並註明**，未改引擎遷就來源 |
| livermore | **出場語意誤讀已更正**：程式為 `price <= entry - 3×ATR`，基準是**進場價**，不是持倉最高價。這是錨在進場價、距離隨當期 ATR 伸縮的停損，**不會隨股價上漲上移**。作者的訊息字串寫「ATR 移動停損」，但數學不是移動停損 —— 先前據該字串映射到 `ATR_TRAILING` 是錯的 |
| livermore | 出場有兩條（ATR 距離停損、跌破 20 日低），來源未說明兩者同時成立時如何處理 |
| 全部 | 本批教訓：來源的 docstring／訊息字串與實際算式可能不符，一律以算式為準 |
| oneil | 來源 docstring 提及 EPS 年成長 ≥25% 與 RS ≥1，但 `requires_fundamentals = False`，程式中 `rs_ok = True` 直接放行。**實際上這兩條沒有生效**，config 中保留為待實作條件，不可當成來源已驗證的規則 |
| qullamaggie | 「突破過去 10–20 日高點」為區間非定值，本批取 15 作為研究端選定值（TRANSLATED）。「整理期間波動收斂：後半段 ATR < 前半段 ATR」未定義前後半段如何切分 |
| qullamaggie | 進場日強度上限 `漲幅 ≤ 2/3 × ATR(20)` 未定義分子基準（自昨收或自 pivot），亦未定義 ATR 的價格口徑 |
| mclean | 「紅＝投信外資同買 0.9／藍＝單邊連買 0.65」是 strength 權重，本引擎無對應概念，未轉譯 |
| floor | 乖離分位「只用昨日以前」的分布，來源未說明是 expanding 還是固定窗口 |
| trust | 來源註明 spec 原版投量比為 0.10，作者改為 0.03「針對中小型股」。**這是作者的改寫，不是原規則** |
| raiho | 來源註明「spec 無此條」的 20% 停損為作者自加 |
| lynch / raiho | 多個參數預設為 0.0 代表關閉，來源以此表達「原行為」，轉譯時已略去 |
| us_overnight | 來源以收盤價成交，作者自述放棄開盤跳空、屬偏保守估計。與本引擎的次日開盤成交不同 |
| 全部出場 | 來源均未說明盤中觸價或收盤確認。本批一律視為收盤確認、次一交易日開盤成交，與 VCP Round 1 一致 |

## 未取得的來源

- 原始著作全文（李佛摩、歐尼爾、林區、葛拉漢等）：未取得，不替歸因背書
- Qullamaggie 本人發布的原始規則：未取得
- `wirelessr/three-gate-screener` 的方法論與教訓文件：尚未閱讀
