# VCP Round 1：三段收縮完整進出場掃描

狀態：COMPLETE（E1 描述性研究）

## 結論邊界

- 本輪是 TRANSLATED 研究假設，不冒充老手原始 VCP 的完整裁量定義。
- 不宣告最佳策略、不宣告顯著、不宣告可出售或可實盤；不 promote、不解鎖 OOS。
- E1 只到 2021-12-31；期末未平倉不強制出場，也未讀取 E2 價格補完。
- 亂數對照／預期偽陽性數尚未完成，本輪無推論性存活名單。既有 placebo 使用不同訊號、共享資金、零摩擦與固定停損/時間出場，不能依原凍結契約直接移植到本輪。
- 多重檢定校正與跨時期穩定性尚未完成；圖上的連續區域只能稱候選高原。

## Run identity

- strategy version: vcp_round1_three_segment_v1
- epoch: E1：歷史開發期（2016-01-04～2021-12-31）
- source revision: 39eb22662f74a4591b1e57795174ffc2f7585f44
- code commit: 4b3b4c8c76f09c16f46fbe2863a3f772d3e8c3da
- P2-060 exclusion SHA: 379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134
- top-25%-turnover eligibility union distinct tickers: 1986；不是無條件全市場。
- P2-060 排除清冊 distinct tickers: 355。
- all_liquid 實際條件：四碼、close>=10、observed_trade、valid_ohlc、P2-060 排除、同日成交額 top 25%。
- 額外訊號流動性條件：訊號日前 20 日平均成交額 >= TWD 20,000,000。
- 成本：買0.1425%手續費；賣0.1425%手續費+0.3%證交稅；買賣各0.1%不利滑價。
- 指標／pivot：一致 CA 的 adjusted research coordinate；成交與現金損益：RAW execution + canonical CA accounting。
- config hashes: {"configs/examples/exits/vcp_round1_atr21_d21.yaml": "b6e8a49fb43304045f9a975816f7202bf02b909179ddd292a9f26114d01ad679", "configs/examples/signals/vcp_round1_three_segment_v1.yaml": "e52c7d7964421f4a1223f9a41c50c55c7fff98f683dc108cc8537fabfaccd0d7", "configs/research/vcp_round1_three_segment_v1.yaml": "157ca2cd8447b50a69427cbc1492fc58e8b5bebd7dbb485ca605ae621f3afd16"}
- pilot configs / runtime: 2 / 2.01s
- full configs / runtime: 108 / 89.11s
- feature cache hits / misses: 2130 / 30

## 掃描完整性

- 108 格：108；缺格：0。
- 有已平倉交易的 config：108。
- n_closed >= 100、可進高原圖色階的 config：62。
- 全部 signal_count：21756；entry_count：15097。
- 全部 n_closed：14818；n_open：279。
- 追價拒絕：6387；其他未成交：193。
- 已平倉統計受 E1 期末未平倉截尾影響；open positions 不混入 win/loss/payoff/expectancy。

## 哪些參數區域看起來較穩定？

本輪不事後新增高原通過門檻。以下只列各軸對其他三軸聚合後的 expectancy 中位數與 IQR；相鄰數值是否連續需與六張雙軸圖及 108 原始格共同閱讀，不能把單一最高格當成結論。

### base_len

| 值 | 有效 config | expectancy 中位數 | Q1 | Q3 | n_closed 中位數 |
|---:|---:|---:|---:|---:|---:|
| 25 | 21 | 0.215% | 0.061% | 0.387% | 208 |
| 35 | 17 | 0.311% | 0.015% | 0.512% | 170 |
| 50 | 12 | -0.781% | -1.191% | -0.627% | 154 |
| 65 | 12 | -0.550% | -0.685% | -0.416% | 151 |

### last_contraction

| 值 | 有效 config | expectancy 中位數 | Q1 | Q3 | n_closed 中位數 |
|---:|---:|---:|---:|---:|---:|
| 0.08 | 17 | 0.250% | -0.345% | 0.445% | 150 |
| 0.12 | 22 | -0.188% | -0.730% | 0.204% | 169 |
| 0.15 | 23 | -0.288% | -0.645% | 0.233% | 174 |

### dry_up

| 值 | 有效 config | expectancy 中位數 | Q1 | Q3 | n_closed 中位數 |
|---:|---:|---:|---:|---:|---:|
| 0.5 | 5 | 0.073% | -0.632% | 0.215% | 120 |
| 0.65 | 23 | -0.060% | -0.730% | 0.348% | 155 |
| 0.8 | 34 | -0.019% | -0.532% | 0.302% | 186 |

### breakout_vol

| 值 | 有效 config | expectancy 中位數 | Q1 | Q3 | n_closed 中位數 |
|---:|---:|---:|---:|---:|---:|
| 1.5 | 28 | -0.043% | -0.639% | 0.239% | 243 |
| 2.0 | 21 | -0.006% | -0.551% | 0.319% | 174 |
| 2.5 | 13 | -0.054% | -0.469% | 0.373% | 127 |

## 交易機會與代價如何變化？

- config signal_count 範圍：23～662。
- config entry_count 範圍：18～478。
- 訊號到實際進場比例中位數：68.87%
- 每筆均以相同初始名目資金正規化；不同股價不改變交易統計權重。
- 主要執行摩擦直接體現在追價拒絕、其他未成交、成本後 net_return 與 blocked exit attempts；不另在報告層重扣成本。

## 是否主要依賴少數個股或交易？

- expectancy 前 25% 的有效 config 數：27。
- 高分組 pair 中觸發 >60% 贏家重疊警示的組數：25。
- overlap 檔保留股票集合與（股票、進場日）集合 Jaccard，以及各 config 移除前 1/3/5 大獲利交易後 expectancy。
- 參數組合的主要贏家重疊，需檢查高原是否依賴共同個股／行情。

## 下市／終止生命週期

- E1 母體中由現行 canonical fallback 建模、外部終止事實仍未確認的 terminal ticker 數：53。
- 受 UNVERIFIED_TERMINAL_CASHOUT 影響的已進場交易／未平倉記錄數（跨 config 計）：27。
- 這些交易保留並單獨標示；沒有只跑現存股票清單。

## 哪些結論仍無法成立？

- 無法成立：統計顯著性、預期偽陽性存活名單、多重檢定校正後優勢、E2 跨時期穩定性、E3 效果、獨立 OOS、可實盤／可出售判定。
- 無法把本輪三段收縮、ATR21×2.5 或 D21 說成老手唯一原始定義。
- 無法把候選高原視為已確認優勢；第二輪若改定義必須新增實驗版本與搜尋紀錄。

## 產物

- out/vcp_sweep_round1.csv — 108 格完整總表。
- out/vcp_sweep_round1_trades.csv — 成本後逐筆已平倉交易。
- out/vcp_sweep_round1_open_positions.csv — E1 期末未平倉。
- out/vcp_sweep_overlap.csv — top-20 overlap 與移除最大獲利敏感度。
- out/vcp_sweep_round1_pilot.csv — 先行 2-config 驗證紀錄。
- out/vcp_sweep_round1_signal_diagnostics.csv — 候選判定與未成交原因彙總。
- out/vcp_sweep_round1_manifest.json — source/config/code/cost/run manifest。

### 圖

- out/vcp_round1_axis_base_len.png
- out/vcp_round1_axis_last_contraction.png
- out/vcp_round1_axis_dry_up.png
- out/vcp_round1_axis_breakout_vol.png
- out/vcp_round1_heatmap_base_len_x_last_contraction.png
- out/vcp_round1_heatmap_base_len_x_dry_up.png
- out/vcp_round1_heatmap_base_len_x_breakout_vol.png
- out/vcp_round1_heatmap_last_contraction_x_dry_up.png
- out/vcp_round1_heatmap_last_contraction_x_breakout_vol.png
- out/vcp_round1_heatmap_dry_up_x_breakout_vol.png
