# 公司行動回溯調整的實際影響稽核

狀態：完成資料、特徵與候選資格一致性稽核，待第 5 項審查。

本稽核不計算任何策略效果；沒有執行 baseline、Round 2、ML，也沒有重跑 VCP Round 1。

## 固定來源與算法

- source revision：fb8b042b46dc38838d103544ca17da10286c7bfe
- build_adj：event ratio=after_price/before_price；歷史日乘其後事件正倍率；OHLC round(4)。
- daily_update_adj：事件日先回寫歷史 OHLC，再 append 當日 RAW；Trading_Volume、Trading_money 不乘因子。
- 有效 date-stock event rows：14,586；E1 結束後 event rows：7,823。
- knowledge-time 欄位候選：無；event.date>T 只代表晚於 T 生效，不等於 T 時未知。

## 方法與容差

- ratio rtol=0.0, atol=1e-06; boundary band=0.0001; 布林翻轉不用容差，門檻附近翻轉保留為診斷。
- RAW 到 stored adjusted 重建價格 tolerance=0.0001 TWD。
- factor-only 只移除 T 後事件的共同倍率；online RAW+event 是用目前 frozen 檔倒推的 counterfactual，不冒稱 contemporaneous snapshot。

- 合成：MA120 flips=0；N60 flips=0；close>=10 flip=True。

## E1 逐年結果

| year | feature_source_rows | feature_unique_stocks | future_factor_not_one_rows | ma120_comparable | ma120_value_diff_factor_only | ma120_gate_flips_factor_only | ma120_gate_flips_near_boundary | ma120_gate_flips_far_boundary | ma120_near_boundary | n60_comparable | n60_signal_flips_factor_only | n60_signal_flips_near_boundary | n60_signal_flips_far_boundary | n60_near_boundary | online_ma120_comparable | online_ma120_value_diff_vs_final | online_ma120_gate_flips_vs_final | online_n60_comparable | online_n60_signal_flips_vs_final | online_n60_excluded_online_history_incomplete | online_ma120_excluded_online_history_incomplete | online_events_applied | raw_close_missing_on_adjusted_rows | universe_source_rows | raw_close_missing | adjusted_close_missing | close_gate_raw_add_vs_adjusted | close_gate_raw_remove_vs_adjusted | close_gate_diff_unique_stocks | base_pass_raw_add_vs_adjusted | base_pass_raw_remove_vs_adjusted | final_universe_diff_threshold_both_priced | final_universe_diff_missing_data | final_universe_diff_ranking_knock_on | final_universe_raw_add_vs_adjusted | final_universe_raw_remove_vs_adjusted | final_universe_diff_unique_stocks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2016 | 455344 | 1930 | 380196 | 444439 | 0 | 0 | 0 | 0 | 543 | 449560 | 0 | 0 | 0 | 9840 | 331933 | 147713 | 25182 | 349560 | 1463 | 100000 | 112506 | 0 | 32918 | 461812 | 33335 | 6468 | 40915 | 2454 | 378 | 46148 | 2454 | 4392 | 1104 | 5424 | 10920 | 0 | 765 |
| 2017 | 480938 | 2023 | 391513 | 468450 | 0 | 0 | 0 | 0 | 522 | 474432 | 0 | 0 | 0 | 11344 | 346411 | 58551 | 6973 | 368970 | 101 | 105462 | 122039 | 1252 | 35532 | 485707 | 35562 | 4769 | 32242 | 2612 | 294 | 36692 | 2612 | 3720 | 927 | 3873 | 8520 | 0 | 780 |
| 2018 | 505260 | 2118 | 398296 | 493366 | 0 | 0 | 0 | 0 | 513 | 499121 | 0 | 0 | 0 | 8804 | 360932 | 50003 | 6683 | 393334 | 184 | 105787 | 132434 | 1296 | 40426 | 508333 | 40541 | 3073 | 27991 | 2454 | 284 | 30506 | 2454 | 3305 | 643 | 3060 | 7006 | 2 | 732 |
| 2019 | 522786 | 2244 | 393536 | 506152 | 0 | 0 | 0 | 0 | 628 | 514179 | 0 | 0 | 0 | 16206 | 363545 | 51863 | 6709 | 397815 | 330 | 116364 | 142607 | 1367 | 43305 | 524751 | 43401 | 1965 | 21095 | 1893 | 215 | 21869 | 1893 | 2233 | 236 | 2521 | 4990 | 0 | 651 |
| 2020 | 554451 | 2340 | 402060 | 540041 | 0 | 0 | 0 | 0 | 472 | 547500 | 0 | 0 | 0 | 11925 | 421588 | 77069 | 7020 | 445707 | 461 | 101793 | 118453 | 1371 | 51509 | 555123 | 51586 | 672 | 18199 | 2023 | 350 | 18292 | 2023 | 1938 | 48 | 2090 | 4066 | 10 | 631 |
| 2021 | 561939 | 2370 | 402269 | 550016 | 0 | 1 | 1 | 0 | 614 | 555568 | 0 | 0 | 0 | 12037 | 440602 | 70369 | 6702 | 459120 | 483 | 96448 | 109414 | 1477 | 51748 | 562214 | 51759 | 275 | 7894 | 2053 | 139 | 7899 | 2053 | 796 | 5 | 762 | 1513 | 50 | 446 |

factor-only 欄回答共同倍率本身；online 欄同時可能含 rounding、RAW 修訂、缺列等差異，不能直接歸因於未來事件。

## 來源重建一致性

| comparison | year | rows | comparable | match_within_0_00005 | mismatch | median_abs_diff | max_abs_diff |
|---|---|---|---|---|---|---|---|
| round_once | ALL_E1 | 3080718 | 2825280 | 1284782 | 1540498 | 0.001745 | 3876.8595 |
| round_once | 2016 | 455344 | 422426 | 114755 | 307671 | 0.357857 | 685.78316 |
| round_once | 2017 | 480938 | 445406 | 201037 | 244369 | 0.00196 | 501.74158 |
| round_once | 2018 | 505260 | 464834 | 218209 | 246625 | 0.000992 | 544.1422 |
| round_once | 2019 | 522786 | 479481 | 229546 | 249935 | 0.000632 | 730.43212 |
| round_once | 2020 | 554451 | 502942 | 250803 | 252139 | 0.000146 | 1853.8397 |
| round_once | 2021 | 561939 | 510191 | 270432 | 239759 | 4.7e-05 | 3876.8595 |
| sequential_round4 | ALL_E1 | 3080718 | 2825280 | 1164532 | 1660748 | 0.001747 | 3876.8596 |
| sequential_round4 | 2016 | 455344 | 422426 | 102206 | 320220 | 0.3578275 | 685.78316 |
| sequential_round4 | 2017 | 480938 | 445406 | 176929 | 268477 | 0.001963 | 501.74158 |
| sequential_round4 | 2018 | 505260 | 464834 | 194511 | 270323 | 0.00099 | 544.1421 |
| sequential_round4 | 2019 | 522786 | 479481 | 207941 | 271540 | 0.000626 | 730.43222 |
| sequential_round4 | 2020 | 554451 | 502942 | 230791 | 272151 | 0.00018 | 1853.8397 |
| sequential_round4 | 2021 | 561939 | 510191 | 252154 | 258037 | 0.000105 | 3876.8596 |

## all_liquid 母體

- UniverseCompiler 的 min_close_twd=10 讀 caller panel close；feature build 與 VCP Round 1 research panel 都傳 adjusted close。
- RAW close>=10 僅為診斷對照；P2-060、ticker regex、observed_trade、valid_ohlc、Trading_money、top25% 固定。
- E1 final all_liquid stock-day 差異：37,077；涉及 1,209 檔。

## 特徵影響分類

| classification | rows |
|---|---|
| INSUFFICIENT_EVIDENCE | 1 |
| PROVEN_AFFECTED_VALUE | 2 |
| PROVEN_AFFECTED_VIA_UNIVERSE | 12 |
| PROVEN_INVARIANT_TO_COMMON_POSITIVE_SCALE | 37 |
| PROVEN_INVARIANT_TO_SPECIFIED_STOCK_ADJUSTMENT | 20 |

- MA ratio、相對高低、returns/vol、ATR/close、Bollinger ratio、RSI、KD、CCI、Williams 等在完整回看窗共同正倍率下原值不變。
- MACD histogram/slope 是 price-unit，原值會縮放。
- persisted stock rows、percentile、tier 與 industry cross-section 仍可能因 eligible universe 改變而受影響。
- 值不變只解除這一項調整依賴，不代表發布時間或其他 PIT 條件通過。

## 差異案例

| case_type | date | stock_id | close_to_ma120_current | close_to_ma120_online_asof | n60_current | n60_online_asof | adjusted_close | raw_close | Trading_money | adjusted_turnover_pct | raw_turnover_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ONLINE_MA120_GATE_FLIP | 2018-10-08 00:00:00 | 0050 | 0.00036707705 | -0.0040099599 |  |  |  |  |  |  |  |
| ONLINE_MA120_GATE_FLIP | 2018-10-09 00:00:00 | 0050 | 0.0032508957 | -0.0010699251 |  |  |  |  |  |  |  |
| ONLINE_MA120_GATE_FLIP | 2019-08-07 00:00:00 | 0050 | 0.0032189589 | -0.0042530597 |  |  |  |  |  |  |  |
| ONLINE_MA120_GATE_FLIP | 2019-08-13 00:00:00 | 0050 | 0.0014267604 | -0.0058212058 |  |  |  |  |  |  |  |
| ONLINE_MA120_GATE_FLIP | 2019-08-28 00:00:00 | 0050 | 0.0052904006 | -0.0012112177 |  |  |  |  |  |  |  |
| ONLINE_MA120_GATE_FLIP | 2020-02-03 00:00:00 | 0050 | 0.030346109 | -0.0015370312 |  |  |  |  |  |  |  |
| ONLINE_MA120_GATE_FLIP | 2020-02-24 00:00:00 | 0050 | 0.022325437 | -0.0052488488 |  |  |  |  |  |  |  |
| ONLINE_MA120_GATE_FLIP | 2020-02-25 00:00:00 | 0050 | 0.024009957 | -0.0033460803 |  |  |  |  |  |  |  |
| ONLINE_MA120_GATE_FLIP | 2020-02-26 00:00:00 | 0050 | 0.012632467 | -0.01416212 |  |  |  |  |  |  |  |
| ONLINE_MA120_GATE_FLIP | 2020-02-27 00:00:00 | 0050 | 0.0025060467 | -0.02376801 |  |  |  |  |  |  |  |
| ONLINE_MA120_GATE_FLIP | 2020-03-03 00:00:00 | 0050 | 4.9616596e-05 | -0.025659824 |  |  |  |  |  |  |  |
| ONLINE_MA120_GATE_FLIP | 2020-03-04 00:00:00 | 0050 | 0.005882809 | -0.01972187 |  |  |  |  |  |  |  |
| ONLINE_N60_FLIP | 2017-02-08 00:00:00 | 0050 |  |  | True | False |  |  |  |  |  |
| ONLINE_N60_FLIP | 2017-02-15 00:00:00 | 0050 |  |  | False | True |  |  |  |  |  |
| ONLINE_N60_FLIP | 2017-09-01 00:00:00 | 0050 |  |  | True | False |  |  |  |  |  |
| ONLINE_N60_FLIP | 2018-07-24 00:00:00 | 0050 |  |  | False | True |  |  |  |  |  |
| ONLINE_N60_FLIP | 2019-07-22 00:00:00 | 0050 |  |  | True | False |  |  |  |  |  |
| ONLINE_N60_FLIP | 2021-02-17 00:00:00 | 0050 |  |  | True | False |  |  |  |  |  |
| ONLINE_N60_FLIP | 2021-04-26 00:00:00 | 0050 |  |  | True | False |  |  |  |  |  |
| ONLINE_N60_FLIP | 2018-01-03 00:00:00 | 0051 |  |  | True | False |  |  |  |  |  |
| ONLINE_N60_FLIP | 2019-12-25 00:00:00 | 0051 |  |  | True | False |  |  |  |  |  |
| ONLINE_N60_FLIP | 2019-12-27 00:00:00 | 0051 |  |  | True | False |  |  |  |  |  |
| ONLINE_N60_FLIP | 2020-01-02 00:00:00 | 0051 |  |  | True | False |  |  |  |  |  |
| ONLINE_N60_FLIP | 2020-11-26 00:00:00 | 0051 |  |  | True | False |  |  |  |  |  |
| RAW_CLOSE_GATE_ADDS | 2016-01-04 00:00:00 | 1108 |  |  |  |  | 5.976258 | 10 | 813850 |  |  |
| RAW_CLOSE_GATE_ADDS | 2016-01-04 00:00:00 | 1218 |  |  |  |  | 8.195481 | 11.8 | 4841686 |  |  |
| RAW_CLOSE_GATE_ADDS | 2016-01-04 00:00:00 | 1220 |  |  |  |  | 6.699391 | 10.65 | 571160 |  |  |
| RAW_CLOSE_GATE_ADDS | 2016-01-04 00:00:00 | 1229 |  |  |  |  | 6.153917 | 19 | 9177138 |  |  |
| RAW_CLOSE_GATE_ADDS | 2016-01-04 00:00:00 | 1231 |  |  |  |  | 9.443165 | 28.2 | 2595029 |  |  |
| RAW_CLOSE_GATE_ADDS | 2016-01-04 00:00:00 | 1235 |  |  |  |  | 5.2923 | 19.2 | 280080 |  |  |

## VCP Round 1 依賴

- shared all_liquid path=True；狀態=待影響評估。
- 原結果保留、不重跑、不宣告績效失效；若母體翻轉，後續比較不得稱為乾淨共同基準。

## 最小修正方案（提案，不執行）

- 保留：已證明尺度不變的公式與測試、MA120 >=0 evaluator、hydration/checksum/null contract、既有 Round 1 結果檔。
- 另建版本：若 owner 核定 PIT-safe absolute-price universe，依 eligible membership 的 feature rows/percentile/tier 需新版本重建；不必推倒尺度不變公式。
- MACD price-unit 原值需在核定 causal coordinate 另驗。
- 尚缺：完整 E1 receipt/publish/known-time；目前 frozen RAW 不是 contemporaneous snapshot；其他 EOD/RAW/TRI/industry cutoff evidence 維持原 gate。

## 停止點

不改正式母體、不重建正式 feature artifact、不修改或重跑策略結果；停在第 5 項公司行動影響稽核驗收。
