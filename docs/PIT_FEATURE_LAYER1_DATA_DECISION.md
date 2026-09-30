# 第 5 項：稽核結案與最小資料修正決策

狀態：**稽核修復已驗收；資料方案待 Astra 核定；策略 gate 維持阻擋**。

接手 main：`40021764c960674768d05f81da17aed0de133ff8`。固定來源：`fb8b042b46dc38838d103544ca17da10286c7bfe`。本次只有來源品質、28 個股票日的價格重建與文件交接；沒有重跑完整 E1 稽核，也沒有查詢交易結果。查核方法與完整數字見 [查核證據](PIT_FEATURE_LAYER1_DATA_EVIDENCE.md)。

## 1. 核定建議

**推薦建立一個獨立版本 `layer1_60d_ma120_causal_raw_v2`：RAW 絕對股價資格＋事件生效時更新的因果價格座標＋既有 MA120/N60 語意；只建必要欄位，保留原 v1 與 VCP Round 1。** 本次只提出設計，不建立正式 config、不重建 artifact、不變更 gate。

先完成必要依賴的資料品質／截止證據驗收，再建 v2；不能先建數值後把 UNKNOWN 改成 VERIFIED。所需補件、可重用實作、驗收條件均列在下方，無須 owner 自行猜技術規格。

判斷依據：

1. 2016 的 `online_events_applied=0` 已定位：**稽核使用的 dividend_events 原表沒有 2016 事件**，不是 normalize 刪光、行情對齊漏掉或年度彙總錯置。同一 revision 的官方 ledger 卻有 1,244 筆 2016 除權息，因此不能把零事件解讀為沒有公司行動。
2. 目前 adjusted 檔存在多條建置／更新路徑，事件表不是其完整 provenance。RAW×這張表重建不一致，不足以證明來源價格錯誤，也不足以證明偷看未來。1216 已有缺漏事件的數值解釋；2330 已有歷史回寫的直接版本證據；1101 尚有超出既定 rounding 上界的殘差。
3. MA120 比值與 N60 次序在**整個比較視窗共同正倍率**下不變。不能否定這些公式；但既有 artifact 的 row membership 受 adjusted close≥10 影響，故不能整份放行。

## 2. 本輪結案範圍與不可更改的識別

三項程式修復／稽核交付已驗收：事件區間套用、online 自有可比較旗標、母體差異三分。真實資料可交易 PIT 適用性尚未全面通過。

- 修復 `d0c0c6f`；舊報告 `2c94107`；新報告 `fcfeffd`；執行 run [36702638509](https://github.com/bibobo2266/AstraQuant/actions/runs/36702638509)。計算與 artifact 上傳成功，回寫失敗後取回，未重算。
- 母體差異：門檻 **16,384**、缺資料 **2,963**、排名連帶 **17,730**，合計 **37,077**；三類互斥。
- `online_events_applied=6,763` 是新版已處理事件總數，不是新補回數；本次不測新舊差集。
- N60 翻轉 **15,549→3,022** 是事件修正及可比較樣本修正的合併變化，各自貢獻未分離。2016 的 **1,463** 仍是既有描述性翻轉數，沒有把它逐筆歸因於缺漏事件。
- 原 `out/ca_adjustment_invariance_*` 及所有 VCP Round 1 產物不改寫。新證據使用 `out/layer1_data_decision/`。

## 3. 保留與改版的界線

| 項目 | 處理 |
|---|---|
| MA120 | 保留 `close/SMA120−1` 與 `COLUMN_THRESHOLD min=0.0`；不是分位、不是 ≥1；v2 改的是有版本標記的輸入價格座標。 |
| N60 | 保留 `N_SESSION_HIGH lookback=60` 的 strict `>`、首次穿越及既有 row/null/warmup 語意；不是來源方法的 `>=`。 |
| hydration | 保留 `feature_panel_integration.py` 的 exact-key join、requested columns、null reason、checksum、版本與 availability gate；不另建 loader。 |
| prior20 amount | 沿用 VCP 的 common-session `shift(1).rolling(20)`；今日 amount 不進入此前置均額；不得拿包含當日的 `amount_mean20_twd` 代替。 |
| RAW execution、成本、CA accounting | 重用 canonical 既有路徑；必要輸入的可用性仍要驗收；既有功能可重用不代表來源已全面通過。 |
| 共同尺度不變的其他公式／測試 | 保留；本次不重算 43 個特徵、61 個版本。 |
| 舊 v1 與 Round 1 | 永久保留作原口徑的描述性結果，不覆蓋、不改標成新版本。 |

## 4. 唯一推薦的資料版本設計

### 4.1 絕對股價資格使用 RAW

新版本明確分開 `universe_close_raw`、`signal_price_causal`、`execution_price_raw`，不可覆寫同一個 `close` 後讓三種用途混用。

- `min_close_twd=10` 改讀當日 RAW close；「當日 RAW」是價格經濟語意，**不是聲稱 frozen RAW 就是當時快照**。
- 保留原四碼普通股、observed_trade、valid_ohlc、P2-060 排除 SHA `379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134`、成交額 top25% 排名／tie 語意與 prior20 流動性條件。
- 母體仍按完整當日 eligible pool 排名。不能只在舊 artifact 存在的 rows 換 RAW close，因為原先被排除的股票會缺列，也會影響其他股票排名。
- RAW 缺值／非法值維持明確原因；不得拿 adjusted 補值或新增排除名單。若新發現的資料缺口使契約不能成立，阻擋該研究版本並提交範圍修訂審查，不靜默縮小母體。

### 4.2 因果價格座標

**需要新的可驗證座標。不能把現行 online RAW＋dividend_events 直接當完成品。**

建議與待核定基線的出場座標一致：在事件生效時，把早於事件的 rolling OHLC 與相關策略價格狀態轉成 `P_post=(P_pre−c)/m`；`c` 是每一事件前股份現金權利，`m` 是明確 share multiplier。先處理事件，再加入當日 RAW。現金與股數的會計處理仍由 canonical ledger 負責，不把現金再加入策略價格或重複計入損益。

這是 **TRANSLATED 新版本語意**，不是重現 FinMind 的 after/before 倍率。cash 的平移與比例調整不是同一算式，不應要求新座標逐值等於 stored adjusted。只要完整比較集合接受同一正仿射轉換，大小次序可維持；但分段事件、MA 比值大小、ATR 及缺值仍需實測。MA denominator 非正或無法唯一轉換時，明確阻擋，不猜價。

直接重用 `src/astraquant/data/corporate_actions.py` 的已校正 normalized cash/stock view：採用 Cash/StockExDividendTradingDate、分開 cash/stock 生效日、加計 statutory surplus、保留 known_at/payment_at 與來源。不得把 legacy ledger 的 FinMind `event_date` 當除息日，也不得跨來源套同一 rights_ratio 單位。

對 source event 的「依序各處理一次」沿用已驗收順序；**不把來源重現用的 round(4) 自動帶入新座標**。推薦 v2 技術座標保留浮點精度、不逐事件四捨五入；成交價仍遵循既有 RAW 執行規則。精度契約須寫入 manifest 並測試事件前後的 gate/邊界，不在正式來源檔回寫。

已有來源能支持部分標的／事件的建置，例如 1216、2330 的 2016 cash ex-date、金額及較早公告；**現有來源尚不足以證明全 E1、整個研究母體的事件完備性、修訂一致性與截止可得性**。需要的是必要期間的事件對帳與來源契約補證，不是另一套資料平台。不能由 adjusted/RAW 價差反推未知 CA 後當作已知事件。single successor／複合 CA 依既有基線規格保留重置或阻擋；本次不實作。

### 4.3 最小受影響產物

核定後才變更：

| 位置／產物 | 最小修改 |
|---|---|
| 既有 universe compiler/caller＋新版本 config | 指定 RAW 絕對資格欄；保留舊 config 行為，記錄母體版本、exclusion SHA、排名規則。 |
| `scripts/pit_feature_matrix_layer1.py` 與既有 source builder | 在既有輸入邊界接上經驗證的事件座標；先完成原 rolling history 再做 universe eligibility，不用先篩掉歷史 rows。 |
| v2 必要 stock artifact | 只輸出必要 MA120 與 metadata；N60 使用同一有版本的 causal panel；prior20 amount 使用既有正確口徑。保留暖機／缺值原因，不產生未驗收欄。 |
| v2 manifest／availability config／QA | 新 formula/data/universe version、price coordinate、source hashes、cutoff 證據 ID、事件覆蓋、warmup、null contract；受控 hydration 指向新版本，舊 gate 不就地放寬。 |
| 其他 percentile、tier、industry ranks、亂數對照 rows | 如未來要沿用整份矩陣，因母體改變必須另版重建 rows／橫截面統計；此次最小 MA120/N60 路徑不需要先重建這些無關欄。亂數原值算法及種子可保留，但樣本支撐需依新母體重新對帳。 |
| 搜尋清冊／比較 manifest | 登錄新資料與方法版本、與舊結果的差異；未完成亂數／多重檢定校準仍只稱描述性研究。 |

## 5. 必要依賴、發布證據及精確阻擋點

不另設比既有 `available_at < T+1 00:00` 更嚴格的截止。也不把缺少秒數直接判定洩漏。

| 依賴 | 已證實 | 缺少的具體證據／下一個可驗收交付 | 現在用途 |
|---|---|---|---|
| RAW OHLC、Trading_money | 固定 blob、日期與 source 欄可核對；樣本 RAW 來自 TWSE_MI_INDEX；部分歷史檔是 2026 回補。 | 針對必要來源 TWSE/TPEx/FinMind，各列**適用於研究期間**的官方發布規則、歷史資料契約或可追溯接收紀錄，證明截止前可取得；另列歷史回補／修訂政策。2026 工作流排程不能回貼 E1。 | 品質診斷可用；真實策略可用性維持 UNKNOWN。 |
| observed_trade/valid_ohlc/tradability | 可重現來源欄位；是 RAW／交易限制資料的衍生輸入。 | 區分可由已驗收 RAW 當日重建的 flags 與另需官方限制價／停牌／可交易規則的欄；沿用 canonical 契約驗證每個必要來源，不將完整 reference 表存在視為 PIT 證明。 | 不解除 gate。 |
| cash/stock CA | 2016 normalized 所需來源確實存在；1216 公告 2016-07-20 17:17:55、除息 08-04；2330 公告 06-08 15:26:18、除息 06-27。這些明確早於生效日前截止，不需硬要求額外秒級快照。 | 事件身分、ex-date、cash/share units 與官方事件對帳；範圍內缺配對、衝突、known_date 缺漏／晚於截止要逐項列出。來源欄位及較早公告可支持局部證據，不能推成全母體 VERIFIED。 | 這些案例支持方案可建置；不是整體策略放行。 |
| adjusted v1、其母體／排名 | 共同尺度不變有公式證據；membership 改變有實證；來源事件表不完備。 | 新版替代必要輸入；不得只改狀態字串。 | 現有 artifact 仍 UNAVAILABLE for tradable PIT。 |
| price-unit MACD、產業／TRI、其他 L1 欄 | 各有獨立依賴。 | 不納入本次 60D＋MA120 必要輸入；保留原狀態，未驗收欄仍阻擋。若未來市場背景規則需要它們，另補其適用期間證據。 | 不能因最小子集通過就解鎖全矩陣。 |

「台灣盤後資料通常當天可得」目前只能列研究假設，不能代替歷史規則證據。這次在固定來源及既有文件中**未取得**全面 E1 EOD 截止與修訂契約；不能宣稱永遠無法取得。若供應方明示歷史契約／版本紀錄已不存在，才將該證據列為無法取得，相關版本維持阻擋，不改截止時間湊通過。

## 6. 若只能採有限期間

完整 E1 尚不能直接批准。**有限期間候選為 2018-01-02～2021-12-31，以 2017 作暖機／事件對帳期間**，理由只在事件表從 2017 起、避免依賴未覆蓋的 2015/2016 rolling history；沒有看策略效果，也沒有實際改期間。

此候選不是「2017 起資料已乾淨」的宣告：必須證明每個必要 rolling window 不跨入未覆蓋期間、事件身分與公告符合 cutoff、RAW/amount/tradability 證據通過。停牌／缺 row 使 120-history 不足時按既定暖機契約列原因；不能新排除標的或用較短視窗補足。若整體研究契約仍不成立，該有限方案也不得執行。現有證據尚沒有一段已全面綠燈的期間。

完整 E1 的修正路徑相同，只是事件對帳及可得性證據須涵蓋 2015 暖機到 2021；既有 normalized view 是補足 2016 的候選依賴，不能只依賴缺 2016 的 dividend_events。Astra 必須明確核定版本與期間後才能實作，Sol 不自行刪年、改母體或解除 gate。

## 7. 最小驗收與 VCP 比較限制

核定後的資料驗收只需涵蓋必要輸入：

1. 固定來源、事件身分及經濟欄位對帳；未解事件不靜默略過，不調寬既有 ratio 範圍來製造一致。
2. 未來事件增刪不能改寫較早 T 的因果座標；cash／stock／跨無行情日／多事件／非正座標／暖機 null 各驗一次。N60 strict/first-cross 與 MA120≥0 的既有邊界維持。
3. 以 RAW pool 重建必要 membership，對帳門檻、缺資料、排名連帶；數值差異是新版本差異，不要求等於舊 v1。
4. 每個必要來源有適用期間的截止證據 ID；未通過保持 fail closed；新 artifact hash/version/null/row-count 驗證通過後才能提策略研究。

VCP Round 1 保留原 108 格與全部輸出，不修改也不重跑。RAW 母體與因果價格座標可能同時改變樣本及訊號；新基線與 Round 1 只能並列為**不同資料／方法版本的描述性結果**，不能說是共同母體的乾淨比較，更不能把差異歸給進場規則。若另採有限期間，既有全 E1 Round 1 更不具相同期間口徑。未來如需公平比較，須另授權新的共同資料版本實驗；不得覆寫 Round 1 或暗中啟動 Round 2。

## 8. 工程交接與停止點

接手時遠端僅 main、無 open PR，最新同檔修改者 Claude 的 `4002176` 已包含解讀更正與 workflow 修改。本次以該 HEAD 起獨立工作分支，提交前再核對 main；不改任何 workflow，避免覆蓋其工程交付。

回寫 workflow 的新行為屬 `4002176` 工程事項，本次未驗收；若仍需修復／驗證，另列工程任務，保留 artifact、不得重跑計算取代回寫。

**停止：交由 Astra 核定第 5 項最小資料修正方案。** 本文件不是第 5 項全面通過、可執行策略、獨立 OOS 或 edge 宣告。
