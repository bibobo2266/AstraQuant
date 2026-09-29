# Path Diagnostic Closeout Audit

狀態：COMPLETE

本檔只封口 queue 第 1 項的三個驗證尾件；不新增訊號、不改參數網格、不執行新 sweep，也不把候選路徑診斷升格為完整交易證據。

## 1. 漲跌停來源

路徑診斷的漲跌停來源可追溯到 source repo 的 FinMind 官方日限制價資料鏈：

1. `bibobo2266/minervini_picks/scripts/fetch_finmind_execution_year.py` 呼叫 FinMind dataset `TaiwanStockPriceLimit`，產生 `price_limit_finmind_<year>.parquet`。
2. `bibobo2266/minervini_picks/scripts/assemble_finmind_execution.py` 將該資料與 PIT 市場身分對齊後寫入 `data/reference/price_limit_<year>.parquet`，欄位包含 `reference_price`、`limit_up`、`limit_down`。
3. AstraQuant `scripts/source_path_diagnostics.py::_load_price_limits` 僅讀取上述 `data/reference/price_limit_*.parquet`；`_normalize_price_limit_frame` 直接接受 `limit_up` / `limit_down`。
4. `src/astraquant/research/path_diagnostics.py::count_limit_states` 只使用傳入的每日上下限；未知時累計 `limit_price_unknown_days`，沒有昨收固定乘數 fallback。

目前 source repo `data/reference` 可見的 price-limit 年檔為 2015、2016、2017、2018。E1 後續年度若無明示來源限制價，必須維持 `limit_price_unknown`，不得由歷史 7%/10% 規則自行補值。

注意：source repo 的 `scripts/build_tradability.py` 另有以昨收與歷史漲跌幅近似鎖停的舊流程；它不是本路徑診斷的限制價來源，也不得拿來填補本項的未知限制價。

## 2. 60 日對照

既有 60-session 候選級報告與目前 5/10/20 路徑診斷不是同一統計量，對照如下：

| 項目 | 舊 60-session 候選 outcome | 現行 5/10/20 路徑診斷 |
|---|---|---|
| 進場基準 | 訊號日 adjusted close | 訊號日次一共同交易日 RAW open |
| 終點／窗口 | 第 60 個 source session 的 adjusted close | 5/10/20 個共同交易日內 RAW intraday high/low |
| CA 處理 | adjusted 價格隱含調整 | 一單位初始部位的 CA-aware `V_t` |
| 主要量 | forward return / demeaned forward return | MFE / MAE / days-to-extrema / order_state |
| 跨 epoch | 舊產物生成時未按新治理逐窗 purge | 每個 5/10/20 窗口獨立 purge |
| 證據層級 | CANDIDATE | CANDIDATE |

因此 60 日只能作舊口徑參照，不能拿來驗證 5/10/20 數值應相等，也不能把兩者混成單一效果統計。舊 60 日產物涵蓋治理上線前的全期資料，且晚期 forward window 可能延伸進 E3；本封口只確認定義與 lineage，不重新報告其中效果數字。

## 3. Anchor-DOWN 驗算

Anchor-DOWN 工作流在 `.github/workflows/source_observation_sweeps.yml` 明示 `OUTCOME_DIRECTION: SHORT`。核心 `directional_extrema(..., direction=SHORT)` 定義為：

- favorable = `1 - V_t^low`
- adverse = `1 - V_t^high`
- MFE = 最大 favorable
- MAE = 最小 adverse

機械例：entry_ref = 100；若路徑最低值到 80、最高值到 110，則 SHORT MFE = +20%，MAE = -10%。此驗算已加入 `tests/test_path_diagnostics.py::test_anchor_down_short_direction_manual_check`；它只驗公式與方向，不讀取或判讀 E3 效果。

## Closeout

- 漲跌停來源：來源鏈已辨識，缺年維持未知，不補推定值。
- 60 日對照：已完成口徑與治理差異對照，不重跑、不混用效果。
- Anchor-DOWN：SHORT 方向與手算例已測試。
