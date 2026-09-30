# PIT 安全特徵矩陣第一層規格 v1

狀態：FROZEN_FOR_BUILD

本規格只定義 OWNER_PRIORITY_QUEUE 第 5 項的資料建置。它不評估策略效果、不啟動 VCP Round 2、不做 ML、IC、特徵排名、存活名單或參數最佳化。

## 一、範圍與版本

- 版本：\`pit_feature_matrix_layer1_v1\`
- 時期：E1（2016-01-04～2021-12-31）；2015-06-01 起只作 rolling 暖機。
- 母體：rolling 先在完整股票歷史計算，再套 \`configs/examples/universes/all_liquid.yaml\` 與凍結 P2-060 排除。
- 價格：股票技術特徵沿用 adjusted research coordinate；不得用 adjusted 價執行交易。
- 大盤：只用 \`data/futures/index_tri.parquet\` 的 FinMind TaiwanStockTotalReturnIndex / TAIEX 含息口徑。
- available_at：日線股票與大盤特徵均為 AFTER_SESSION_CLOSE；只供同日收盤後／後續決策使用，不宣稱盤中可得。
- 公式／參數／available_at 均進 FeatureCacheKey；source revision 由 workflow 固定並寫 manifest。

## 二、TEST_INVENTORY 對照

本輪實作 L2-T01～L2-T08、L3-G01、L3-R01、L3-R02、L3-I01、L3-M01。L3-G02 需要 dated theme membership；repo 沒有可持久讀取的 dated membership source，因此標 \`BLOCKED_DATA\`，不得用目前主題名單回貼歷史。

完整公式、單位、回看長度、平滑、是否包含當日、available_at、缺值處理、參數來源，以產物 \`out/pit_feature_matrix_layer1_v1_dictionary.csv\` 為機器可讀唯一對照。

### 參數來源原則

- MA20/60/120/250、RS 20/60/120 等：owner TEST_INVENTORY。
- MA slope 10：重用既有 LONG_TERM_TREND_STRUCTURE。
- ATR21：重用 VCP Round 1 的 Wilder ATR21 定義。
- Bollinger 14 / 2 / 120：重用既有 Bollinger config。
- RSI13/14/26：重用已登記 RSI / RSI_RELATIVE 版本；RSI14 slope 5 是例行研究實作選擇。
- KD 9/3/3、80/20：重用已登記 KD 版本。
- MACD histogram 12/26/9、CCI20、Williams %R14、beta60、market RV20、market position252、tercile分群：研究端明確實作版本，不冒充 owner／老手原始規則。
- \`turnover_value_ratio = Trading_money / market_value\` 是「成交金額／市值」value-turnover proxy，明確不稱為股份週轉率。

## 三、橫截面排名

- 僅對當日 all_liquid + P2-060 母體且該欄有效的股票排名。
- \`pandas rank(pct=True, method="average", ascending=True)\`；同值取平均名次。
- 有效標的少於 2 時 percentile 為 null，另列 unusable_dates。
- 原始值永遠保留；percentile 另以 \`<feature>_pct\` 保存。
- \`market_context\` 為單一市場序列，不做橫截面排名。

## 四、缺值與資料界線

- 一律 null；不補零、不 forward-fill。
- coverage 將暖機不足、PIT 產業缺失、市值缺失、TRI 缺失、分母為零與其他來源／幾何無效分開統計。
- PIT industry 僅在 \`valid_from <= date <= valid_to\` 使用；首個已知分類前保持 null。
- feature parquet 禁止 outcome、forward return、交易 exit 後資訊。

## 五、固定亂數對照

建立 10 個固定 seed（1001～1010）負對照欄。值由 date / stock_id / feature_id / seed 的穩定雜湊與 SplitMix64 產生；資料排序不影響值。它們只供未來 falsification 使用，本項不得查看效果。

## 六、儲存

版本化 parquet 寫入 gitignore 下的 \`artifacts/pit_feature_matrix_layer1_v1/\`，由 GitHub Actions artifact 保存；repo 只提交 dictionary、coverage、daily valid counts、unusable dates、available_at audit、manifest 與繁中報告。
