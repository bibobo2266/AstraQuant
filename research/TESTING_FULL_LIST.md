# AstraQuant 完整待測清單與安排狀態

資料截點：2026-10-09（本輪已讀repo紀錄）。這是上一份 Excel 的 Markdown 版本，並非即時巡查。

## 使用規則

- 本表整理現有需求與 repo 紀錄，不是新派工指令，也不授權執行任何測試。
- 「已排執行」表示已列入執行安排；是否已接工、啟動或交付，以「目前做到哪」及來源紀錄為準。
- 「已有驗收紀錄」引用 repo 已存在的驗收，並非本次重新驗收；工程通過不代表策略有效。
- 舊 findings 不作為任何指標有效或無效的證明。
- 94 列包含研究階段、策略版本、條件、診斷和共用工具，並非 94 個獨立策略；對照項目避免重複計數。
- 不因本表更改 main、資料 gate、E1/E2/E3 使用範圍或已定案參數。

## 安排概況

| 安排狀態 | 列數 |
|---|---:|
| 已有驗收紀錄 | 2 |
| 已排執行 | 8 |
| 後續已規劃 | 3 |
| 規則已定未排 | 5 |
| 已登錄未排 | 68 |
| 暫緩 | 4 |
| 共用工具 | 4 |

目前唯一優先是布林四格與必要的 S3 工程／真實驗帳。最新已讀紀錄中 Sol-E 已接工工程修正，四格尚未啟動。KK A/B 規則已定，但未排執行；疊加與參數高原屬後續。

## 比較指標

每格八欄：筆數／扣成本勝率／平均賺／平均賠／賠率／每筆期望值／持有天數中位數／資金占用天數。

MFE／MAE 為診斷，不代替完整進出場、成本與資金占用的結果。

## 完整清單

| ID | 分類 | 要測的項目 | 安排狀態 | 目前做到哪 | 缺口／下一步 | 對照項目 | 來源 |
|---|---|---|---|---|---|---|---|
| S1 | 目前研究 | PIT 資格面板：量、成交額代理、週趨勢、RS、營收YoY、EPS YoY、EPS加速、產業排除旗標 | 已有驗收紀錄 | repo 記錄面板與10筆逐欄對照已驗收；excl_ok=True，第一輪不排產業；基本面可用日仍屬來源估計 | 沿用固定版本；不把面板完成當成篩選條件有效證明 | L2-T01、L2-T05、L2-G01、L2-G02 | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6049981063 |
| S2 | 目前研究 | eligibility／decisions／fills／equity 共用帳本與 synthetic 成交測例 | 已有驗收紀錄 | repo 記錄指定 S2 缺測已解除；假資料與真實 S3 驗帳是不同驗收 | 不以 synthetic 結果代替真實交易績效 | S3、PAPER | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6049981063 |
| S3-ENGINE | 目前研究 | 真實成交、公司事件、驗帳、存檔讀回與續跑 | 已排執行 | Sol-E 已接工；最新已讀紀錄仍未提交完整修正，四格尚未啟動 | 集中交修正與真實重播證據；必要審查通過後續四格 | R1-A1～A4 | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6071836256 |
| R1-A1 | 目前研究 | 訊號日收盤買 × SMA20 出場 | 已排執行 | 已固定四格且列唯一優先；最新已讀紀錄仍未啟動真實四格 | 等待必要工程／真實驗帳審查；交八欄與逐筆帳本 | L1-013、EX-E01、EX-E04、EX-E11 | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6056092668 ; https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6071836256 |
| R1-A2 | 目前研究 | 次日開盤買 × SMA20 出場 | 已排執行 | 已固定四格且列唯一優先；最新已讀紀錄仍未啟動真實四格 | 等待必要工程／真實驗帳審查；交八欄與逐筆帳本 | L1-013、EX-E01、EX-E04、EX-E11 | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6056092668 ; https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6071836256 |
| R1-A3 | 目前研究 | 訊號日收盤買 × SMA20 或 RSI13<50 出場 | 已排執行 | 已固定四格且列唯一優先；最新已讀紀錄仍未啟動真實四格 | 等待必要工程／真實驗帳審查；交八欄與逐筆帳本 | L1-013、EX-E01、EX-E04、EX-E11 | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6056092668 ; https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6071836256 |
| R1-A4 | 目前研究 | 次日開盤買 × SMA20 或 RSI13<50 出場 | 已排執行 | 已固定四格且列唯一優先；最新已讀紀錄仍未啟動真實四格 | 等待必要工程／真實驗帳審查；交八欄與逐筆帳本 | L1-013、EX-E01、EX-E04、EX-E11 | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6056092668 ; https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6071836256 |
| S4-1b | 後續研究 | 資訊疊加：十格比較 | 後續已規劃 | 驗收階段已登錄十格；目前指示不執行1b，未確認十格逐一凍結定義 | 四格之後才排；先確認各格增減哪些資訊，保持其餘交易規則相同 | L2、L3 | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6040107042 ; https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6071795412 |
| S5-1c | 後續研究 | 參數高原：六格鄰近版本 | 後續已規劃 | 驗收階段已登錄六格；目前指示不執行1c，未確認六格具體參數 | 不要追最佳單格；需凍結鄰近參數與比較規則 | S4-1b | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6040107042 ; https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6071795412 |
| PAPER | 每日研究 | 每日 paper trade 帳本：先寫意圖，隔日回填，同一 metrics | 規則已定未排 | 本對話已要求與回測同schema；未找到每日實際接工或帳本交付紀錄 | 接每日候選與可成交資料；保存意圖、拒絕、成交與未平倉 | S2 | 本對話：第1步帳本規格 |
| KK-ENTRY | KK週線 | 週RSI6上穿13＋週收盤>六週均＋六週均上升＋五週均量>十週均量；下週首交易日開盤買 | 規則已定未排 | 已記錄 owner 核准；最新優先指示暫不擴張 KK | 獨立研究；原文「13」的機械欄位須依已核定原始規格核對，不自行補猜 | KK-A、KK-B | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6053548339 ; https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6071795412 |
| KK-A | KK週線 | 相同KK進場；A只用成交價×0.93盤中停損 | 規則已定未排 | 已登錄；跳空按實際可成交價；尚無接線或真實A結果 | 與B分開，不加SMA20、不加碼、不期末強平 | KK-ENTRY | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6053548339 |
| KK-B | KK週線 | 相同KK進場；B日線同一支撐Anchor連破兩個收盤，次日開盤全部退出 | 規則已定未排 | 已登錄；尚無接線或真實B結果 | 固定同一Anchor身分與失守計數；不與A的7%停損合併 | KK-ENTRY、L1-004/005（用途不同） | https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6053548339 |
| POOL-01 | 你的選股流程 | Minervini 選股／screen_combo 產出的實際候選池 | 已登錄未排 | 本對話已指定為實際選股來源；未確認整套email池已接入新研究。S1面板不等於這些完整流程 | 保存當日候選與規則版本，接入相同交易帳本；舊60/250日持有結果不沿用為新結論 | S1 | 本對話：owner 說明實際交易流程 |
| POOL-02 | 你的選股流程 | 題材漏斗產出的實際候選池 | 已登錄未排 | 本對話已指定為實際選股來源；未確認整套email池已接入新研究。S1面板不等於這些完整流程 | 保存當日候選與規則版本，接入相同交易帳本；舊60/250日持有結果不沿用為新結論 | L3-G02 | 本對話：owner 說明實際交易流程 |
| POOL-03 | 你的選股流程 | 每日動能 email 候選池 | 已登錄未排 | 本對話已指定為實際選股來源；未確認整套email池已接入新研究。S1面板不等於這些完整流程 | 保存當日候選與規則版本，接入相同交易帳本；舊60/250日持有結果不沿用為新結論 | S2 | 本對話：owner 說明實際交易流程 |
| POOL-04 | 你的選股流程 | ELEC 三張卡／三條件篩選候選池 | 已登錄未排 | 本對話已指定為實際選股來源；未確認整套email池已接入新研究。S1面板不等於這些完整流程 | 保存當日候選與規則版本，接入相同交易帳本；舊60/250日持有結果不沿用為新結論 | S2 | 本對話：owner 說明實際交易流程 |
| DIR-01 | 方向與訊息 | minervini_picks appdaily.py 扣抵值作方向資訊 | 已登錄未排 | 本對話需求；未找到本輪扣抵值效果比較的接工或交付紀錄 | 保留方向資訊用途；定義加／不加時的交易行為 | S4-1b | 本對話：owner 說明扣抵值用途 |
| DIR-02 | 方向與訊息 | Anchor UP／DOWN 作方向背景，再疊進場訊號 | 已登錄未排 | Anchor元件與舊候選報告已有；這個方向疊加用途尚未確認安排 | 與Anchor直接進場、KK支撐出場分開定義 | L1-004、L1-005、S4-1b | 本對話；https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| NEWS-01 | 方向與訊息 | 管理階層重大訊息／重大事件是否有幫助 | 已登錄未排 | 本對話有需求；未在已讀待測表找到獨立項目或派工 | 先定義事件、當時可知時間與比較方式，不用事後新聞分類 | S4-1b | 本對話：owner 問如何證明重大訊息有用 |
| RS-SHORT | 後續研究 | rs_short=True 的120日組：含／不含兩版對照 | 後續已規劃 | owner 已要求面板保留旗標；後續S3對照要求存在，最新固定四格尚未納入額外版本 | 另列對照，不默默把固定四格擴成八格；不改全市場250日分母 | S1、S3 | 本對話：S1核准三點補充 |
| DIAG-01 | 診斷 | MFE／MAE、先賺後賠／先賠後賺、5/10/20日路徑 | 已登錄未排 | queue 有舊路徑診斷完成紀錄；未確認新R1/KK交易上的診斷已排 | 只作進出場診斷，不替代完整交易與主要KPI | S3、KK | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/OWNER_PRIORITY_QUEUE.md |
| EXP-EMA9-001 | EMA研究 | 固定進場A，比較 A、A＋EMA9方向、A且非EMA9方向 | 規則已定未排 | 總表列為待核定實驗，並非已放行或接工 | 先凍結EMA暖機、斜率、價格座標、缺值、可用時間與成交時點 | L2-T09 | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| HYP-EMA9-001 | EMA研究 | 第二次跌破／站回EMA9的假說 | 已登錄未排 | 有概念紀錄；未機械化，沒有有效性證明 | 定義第二次計數、重置與事件順序 | L1-X06、L2-T09 | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-001 | 進場觸發 | 250日新高突破 | 已登錄未排 | 有舊元件／掃描紀錄；舊效果結論不沿用，新驗證未排 | 新交易驗證未排；已有候選掃描，但 SOURCE_ONEIL_TAIWAN_SWEEP 同時帶 LONG_TERM_TREND_STRUCTURE，並非裸 N_SESSION_HIGH 的獨立 surface。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-002 | 進場觸發 | 布林壓縮後突破（日線） | 已登錄未排 | 有舊元件／掃描紀錄；舊效果結論不沿用，新驗證未排 | 新交易驗證未排；只涵蓋日線；60 分鐘原始版本缺 canonical 盤中來源。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-003 | 進場觸發 | VCP 收縮後突破（機械化第一版） | 已登錄未排 | 有舊元件／掃描紀錄；舊效果結論不沿用，新驗證未排 | 新交易驗證未排；原始 discretionary VCP 的突破前進場、突破後加碼仍未涵蓋；round2 min_amplitude_3/output-schema 修正已實作測試但尚未掃描、無 round2 報告。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-004 | 進場觸發 | Anchor 反轉 UP | 已登錄未排 | 有舊元件／掃描紀錄；舊效果結論不沿用，新驗證未排 | 新交易驗證未排；無。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-005 | 進場觸發 | Anchor 反轉 DOWN | 已登錄未排 | 有舊元件／掃描紀錄；舊效果結論不沿用，新驗證未排 | 新交易驗證未排；無。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-006 | 進場觸發 | 跳空上漲 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；缺正式 source parameter sweep 與落盤報告。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-007 | 進場觸發 | 爆量 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；缺正式 source parameter sweep 與落盤報告。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-008 | 進場觸發 | 均線黃金交叉 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；缺正式 source parameter sweep 與落盤報告。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-009 | 進場觸發 | MACD 柱狀值上穿零 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；實作名稱存在但機械定義不符目標：目前是 MACD 線，不是 histogram；需修正後才可視為驗證可用；另缺正式 sweep/report。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-010 | 進場觸發 | KD 低檔黃金交叉 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；缺正式 source parameter sweep 與落盤報告。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-011 | 進場觸發 | RSI 穿越門檻 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；現有 SOURCE_RSI_DAILY_SWEEP 是 RSI_PULLBACK_RECLAIM 日線代理，不是本 RSI_CROSS 的正式 sweep；本列仍缺 sweep/report。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-012 | 進場觸發 | KD 解除鈍化 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；缺正式 source daily sweep 與報告；現有測試直接驗 state，release 尚無獨立結果報告。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-013 | 進場觸發 | 布林上軌突破（單純） | 已排執行 | 21／2.1／ddof0版本進入R1四格；其他上軌突破版本未排 | 先完成固定四格；不等於已驗證所有布林版本 | R1-A1～A4 | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-014 | 進場觸發 | 一般回檔後重新站回 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；缺正式 source parameter sweep 與落盤報告。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-015 | 進場觸發 | 連續上漲天數 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；缺正式 source parameter sweep 與落盤報告。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-016 | 進場觸發 | 一目均衡表轉折 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；來源日 OHLC 可用，但 exact trigger/available_at 尚未定義；schema 名稱存在、registry 無 evaluator。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-017 | 進場觸發 | Donchian 通道突破 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；需先定義；若採 prior-only N-session high 版本，直接重用 L1-001，不另建元件。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-X01 | 進場表外 | 布林壓縮 60 分鐘版 | 暫緩 | 原始盤中／跨市場方法暫緩；日線代理不算原法完成 | DEFERRED：缺 canonical 盤中來源、completed-bar available_at、聚合邊界與快照/hash 契約。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-X02 | 進場表外 | VCP 突破前進場 / 突破後加碼 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；現行 VCP 只涵蓋機械化 breakout；前置 entry/add-on 未實作。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-X03 | 進場表外 | RSI 多時間框架 SOP | 暫緩 | 原始盤中／跨市場方法暫緩；日線代理不算原法完成 | DEFERRED：缺 canonical 60m/15m 來源與 completed-bar PIT；現有報告僅日線代理。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-X04 | 進場表外 | 夜盤＋美股背景疊加 | 暫緩 | 原始盤中／跨市場方法暫緩；日線代理不算原法完成 | DEFERRED（owner 暫緩）：缺可驗 known_at 的 canonical 夜盤/海外來源與跨市場時區/假日映射。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-X05 | 進場表外 | O'Neil 長期趨勢結構 | 已登錄未排 | 有舊元件／掃描紀錄；舊效果結論不沿用，新驗證未排 | 新交易驗證未排；無獨立 full-trade 結論；現有產物是 candidate-level surface。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-X06 | 進場表外 | EMA9 回踩後確認 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；待凍結 touch 定義（low/close、容忍帶）、confirmation 條件、同 bar/次 bar、EMA 初始化/暖機、缺值、available_at 與成交時點；影片 5/15 分鐘版本另走 intraday lineage。EMA 計算與資料契約為共用依賴，不要求先完成 L2-T09。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L1-X07 | 進場表外 | EMA9／EMA20 交叉 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；待凍結 EMA 初始化/暖機、cross 方向與首次穿越定義、缺值、時間框架、available_at/成交時點；日線與 5/15 分鐘不得混為同一版本。EMA 計算與資料契約為共用依賴，不要求先完成 L2-T09。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-T01 | 技術條件 | 趨勢位階（對 MA20/60/120/250 位置、均線排列、斜率） | 已登錄未排 | S1涵蓋其中部分資格條件；整個bundle的獨立交易貢獻未排 | 新交易驗證未排；缺完整四均線 feature component、PIT feature matrix、canonical simulator field plumbing、正式掃描與完整報告；現有 LONG_TERM_TREND_STRUCTURE 僅兩均線代理。 | S1 | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-T02 | 技術條件 | 距 250 日高低點百分比、距前高天數 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；ADJ 歷史可計算，但 AstraQuant 未建立 PIT feature/available_at、component、simulator plumbing、scan/report。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-T03 | 技術條件 | ATR%、20/60 日波動、波動比 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；日 OHLC source 有；feature/PIT/component/simulator/scan/report 未完成。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-T04 | 技術條件 | 布林帶寬與其歷史分位、通道內位置 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；現有 BOLLINGER_COMPRESSION 只回傳 boolean，未提供三個要求的連續 feature bundle；需 feature matrix/PIT/sim plumbing/正式掃描。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-T05 | 技術條件 | 量能比（5/20、20/60）、20 日均額、週轉率、量縮比、上漲日量佔比 | 已登錄未排 | S1涵蓋其中部分資格條件；整個bundle的獨立交易貢獻未排 | 新交易驗證未排；OHLCV/Trading_money source 有；完整 bundle 未建立，缺 PIT component/simulator/scan/report。 | S1 | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-T06 | 技術條件 | RSI 各週期與差值與斜率 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；RSI level 與 fast>slow 已有，但 numeric difference/slope 未實作；整列六階段未完整。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-T07 | 技術條件 | KD 各值與高低檔鈍化天數 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；K/D helper 與 boolean sustained-state 有，但未提供可重用 numeric K/D + saturation-days feature bundle；缺正式 sweep/report。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-T08 | 技術條件 | MACD 柱與斜率、CCI、威廉指標 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；現行 macd_cross_above_zero 實際是 MACD line cross，不能代替 histogram/slope；CCI/Williams 也未實作。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-T09 | 技術條件 | EMA9 方向狀態（日線研究改編） | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；實驗前需凍結 EMA 初始化/暖機、斜率定義與等號、待核定的 CA 一致研究價格、缺值政策、訊號 available_at 與成交時點；完整日線 close 不得假裝盤中提前可知。EMA 計算與資料契約為共用依賴，方向條件可獨立研究，不以回踩或交叉完成為前置。 | EXP-EMA9-001 | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-T10 | 技術條件 | 價格同側於 EMA9＋session VWAP（盤中） | 暫緩 | 原始盤中／跨市場方法暫緩；日線代理不算原法完成 | DEFERRED：KBar source family 存在但 canonical 5/15 分鐘聚合、completed-bar available_at、session VWAP 定義/重置時點與 PIT 契約未完成；禁止以日線 close/amount 冒充。不得自行加入 EMA9/VWAP 斜率條件。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-C01 | 籌碼條件 | 外資／投信／自營 5 日與 20 日淨買超、三大法人合計 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；data/inst source family 有，但 available_at/PIT 尚未完成 runtime audit，AstraQuant feature/component/simulator/scan/report 皆缺。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-C02 | 籌碼條件 | 外資持股比例與變化 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；尚未確認 canonical source 欄位與 available_at；後續階段皆缺。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-C03 | 籌碼條件 | 融資餘額變化、融券餘額變化、券資比 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；margin source family 有且 FUNDAMENTAL_PIT_AUDIT 驗過 available_date=date，但 feature/component/simulator/scan/report 未建。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-C04 | 籌碼條件 | 借券賣出餘額變化 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；未確認 canonical 欄位與 PIT；其餘階段皆缺。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-C05 | 籌碼條件 | 千張大戶持股比例與四週變化 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；STABLE pool 只消費 standardized large_holder 欄位，AstraQuant 尚未建立 source→feature 的 canonical producer/PIT；缺正式 scan/report。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-C06 | 籌碼條件 | 當沖比例 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；canonical source/available_at 未確認；後續階段皆缺。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-G01 | 基本面成長 | 月營收 YoY（1月／3月均／12月均）、MoM、YoY 加速度、12月累計 YoY | 已登錄未排 | S1涵蓋其中部分資格條件；整個bundle的獨立交易貢獻未排 | 新交易驗證未排；month_revenue source/PIT 已 audit；feature producer/component/simulator/scan/report 未建。 | S1 | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-G02 | 基本面成長 | EPS YoY（單季／四季均）、EPS QoQ、單季營收 YoY | 已登錄未排 | S1涵蓋其中部分資格條件；整個bundle的獨立交易貢獻未排 | 新交易驗證未排；financials source/PIT 已 audit，但 exact feature producer/component/simulator/scan/report 未建。 | S1 | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-G03 | 基本面成長 | EPS 連續成長季數 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；pool evaluator 已有，但 canonical source→eps_yoy_positive_streak producer 未接；因此正式 scan/report 未完成。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-Q01 | 基本面品質 | 毛利率與年增、營益率與年增、淨利率 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；financials source/PIT 有，但 feature producer/component/simulator/scan/report 未建。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-Q02 | 基本面品質 | ROE、ROA、營運現金流對淨利比 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；financials source/PIT 有；FUNDAMENTAL_FLOOR 只消費 roe_4q_avg，未建立本完整 bundle。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-Q03 | 基本面品質 | 存貨週轉變化、負債權益比 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；balance/financial source 有；PIT audit 支援 financials，但 exact feature/component 未建；debt_ratio 不能等同 debt/equity。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-V01 | 估值條件 | 本益比自身三年分位、股價淨值比自身三年分位 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；stock_per source family 有，但 available_at/PIT 尚未 audit；feature/component/simulator/scan/report 未建。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L2-V02 | 估值條件 | 殖利率、本益比相對同業、股價淨值比相對同業 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；valuation/dividend/industry source families存在，但跨源 available_at 與 feature join 尚未驗；後續階段皆缺。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L3-G01 | 族群與背景 | PIT 產業別、市值級距、流動性級距、波動特性分群 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；industry_pit 與 market_value/source price 存在；但官方產業 evaluator 尚未實作，市值級距/波動 clustering 未實作；整列 PIT/component 不完整。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L3-G02 | 族群與背景 | 主題名單（軍工航太、AI伺服器、技術護城河等） | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；軍工航太有 example；其他主題若無 dated membership 檔即不可推定。缺正式 cross-theme scan/report。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L3-R01 | 族群與背景 | 個股相對強度：對所屬產業、對大盤（20/60/120 日） | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；price/index/industry source 有，但 PIT-safe benchmark join、feature component、simulator、scan/report 未建。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L3-R02 | 族群與背景 | beta、與大盤相關性、剔除 beta 後殘差波動 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；source price/index 有；window/estimator/available_at 未定義，後續階段皆缺。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L3-I01 | 族群與背景 | 產業相對大盤強度、產業在全市場強度排名 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；PIT industry/source index 有；aggregation、PIT feature、component、simulator、scan/report 未建。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L3-M01 | 族群與背景 | 大盤對 200 日均線、大盤波動、大盤位階 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；TAIEX source 有，但 feature/available_at/component/simulator/scan/report 未建。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| L3-M02 | 族群與背景 | 大盤 EMA9 方向背景（日線研究版本） | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；待指定 benchmark/index series、EMA 初始化/暖機、斜率、缺值、CA/price semantics（如適用）、available_at 與成交時點。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-E01 | 出場 | 固定停損 | 已排執行 | R1已定成交×0.93／結構停損取較近；KK-A另立 | 等待四格完整真實帳本；其他停損／MA版本未排 | R1、KK-A | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-E02 | 出場 | 時間／最長持有 | 已登錄未排 | 總表有元件或部分元件；未確認新研究接工 | 新交易驗證未排；已接 simulator 且曾有 full-trade 歷史 sensitivity；該歷史報告屬已接觸資料，不是獨立 OOS。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-E03 | 出場 | 固定停利 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；exit evaluator/simulator wiring/sweep/report 未實作；不得把 schema 宣告視為可用。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-E04 | 出場 | 跌破 MA | 已排執行 | SMA20收盤跌破、次日開盤出場已進入R1四格 | 等待四格完整真實帳本；其他停損／MA版本未排 | R1-A1～A4 | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-E05 | 出場 | EMA20 下方停損／跌破版研究改編 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；停損距 EMA20 多遠、是否隨 EMA 更新、何種價格觸發、觸發後如何成交、決策與 fill timing 均待定；收盤跌破版若研究須另凍結，不得反寫成逐字稿原法。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-E06 | 出場 | 跌破布林中線 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；缺 exit timing/PIT、component、simulator wiring、full-trade scan/report。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-E07 | 出場 | ATR 移動停利 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；缺 ATR exit definition/timing、component、simulator wiring、full-trade scan/report。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-E08 | 出場 | 百分比移動停利 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；缺 trail update/timing semantics、component、simulator wiring、full-trade scan/report。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-E09 | 出場 | Donchian 通道出場 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；缺 channel lookback/timing、component、simulator wiring、full-trade scan/report。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-E10 | 出場 | 一目均衡出場 | 已登錄未排 | 總表尚無完整元件；本輪未逐項核最新版程式 | 新交易驗證未排；缺 exact rule/timing、component、simulator wiring、full-trade scan/report。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-E11 | 出場 | RSI 失守（老手原始條件） | 已登錄未排 | R1已排日線RSI13<50出場；老手原始多時間框架版本仍未排 | 日線代理與原始盤中RSI出場分開，不互相代替 | R1-A3/A4、L1-X03 | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-R01 | 共用工具 | STABLE universe pool | 共用工具 | 既有共用元件，並非獨立策略 | 清單外既有元件；只消費 standardized 欄位，沒有負責產生那些 feature；source→feature/PIT producer 仍是缺口。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-R02 | 共用工具 | FUNDAMENTAL_FLOOR universe pool | 共用工具 | 既有共用元件，並非獨立策略 | 清單外既有元件；依賴預先 standardized features，未提供完整 L2 features。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-R03 | 共用工具 | COLUMN_THRESHOLD generic filter | 共用工具 | 既有共用元件，並非獨立策略 | 清單外既有元件；不負責來源/PIT/feature 計算，不能代替任何尚未實作的 L2/L3 feature。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |
| EX-R04 | 共用工具 | COLUMN_VALUE generic ranking | 共用工具 | 既有共用元件，並非獨立策略 | 清單外既有元件；不負責來源/PIT/feature 計算。 |  | https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md |

## 來源與限制

- 舊元件清單：[TEST_INVENTORY.md 固定版本](https://github.com/bibobo2266/AstraQuant/blob/51d14027c705f3bca74f0daad181c313145cafb4/docs/TEST_INVENTORY.md)。用於補齊已登錄項目，不能視為最新完成狀態或策略有效性證據。
- 執行安排：各列 issue #6 來源連結；本次已讀的最新接工紀錄為 [6071836256](https://github.com/bibobo2266/AstraQuant/issues/6#issuecomment-6071836256)。
- 資料與元件沒有在本次逐項重新驗收；未找到排程、接工或定義的項目已標註缺口，不自行補規則。
