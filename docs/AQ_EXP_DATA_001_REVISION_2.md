# AQ-EXP-DATA-001 revision 2 — producer 與逐日資料契約

狀態：REVIEW_READY（工程／合成契約）；真實受影響筆數尚未核驗。
依據 issue #6 comment `5981858432`；schema 固定於 `5985511174`。
本輪重用既有證據，未重跑 coverage、未讀 E2/E3、未計算真實策略效果。
原 458,315 股票日、272,280／59.41% 均保留為 v1 暫報，不是完整交易可用率。

## 1. Producer、版本、指令與 manifest

以下均為已實際讀取的固定程式／workflow／摘要，不是推測位置：

| 項目 | 固定位置／版本 |
| --- | --- |
| private repository | `bibobo2266/tradestation` |
| producer revision | `20162dc7ad4014cfd5983d309ab3826167b69a71` |
| producer path | `scripts/astraquant_aq_exp_data_001.py` |
| producer Git blob | `fa6b2729e36351eb0cadc3097547fc1a66d0e33f` |
| workflow path | `.github/workflows/aq_exp_data_001.yml`，同 revision |
| workflow Git blob | `8d2be23b1cd001fe9e23289e8ce34254e29b5cd2` |
| workflow run | `37213806645`，attempt 1，SUCCESS |
| output commit | `8226478d0bcb5dc1ae66c08701535f4f1d579a35` |
| output directory | `private/astraquant/aq_exp_data_001_e1_coverage_v1/` |
| summary | `aq_exp_data_001_summary.json`，blob `6f3b210a02d9e518f24cebca5b8698346b8e0156` |
| row table | `aq_exp_data_001_eligibility_reason_rows.parquet`，blob `bf226d682470f7e83f7175afe6fff6e0167ef476`，2,718,958 bytes |

公開可讀機器 manifest：`out/aq_exp_data_001_r2_manifest.json`，包含 producer SHA256、固定輸入與限制。
私有程式及逐列資料不複製到此 repo。

歷史 workflow 的計算指令如下，**本輪未執行**：

```bash
python delivery/scripts/astraquant_aq_exp_data_001.py \
  --source-root source_runtime/minervini_picks/data \
  --astra-root AstraQuant \
  --private-evidence-root evidence_input \
  --output-dir delivery/private/astraquant/aq_exp_data_001_e1_coverage_v1
```

四個 checkout 分別為 producer 上述 revision、source
`fb8b042b46dc38838d103544ca17da10286c7bfe`、Astra contract
`1e184908f17c7e612fad636f30b61071ed916a56`、evidence
`abdc6e18f13710f830000bc946e63ca1c151dcfe`。
輸入為 source `data/raw/prices_raw_2015.parquet` 至 `prices_raw_2021.parquet`、
`data/reference/tradability.parquet`；Astra `docs/SOURCE_CA_PIT_EXCLUSIONS.csv`；
evidence `private/astraquant/ca_dividend_component_reconciliation/v1-9914525f/event_reconciliation.csv`。
exclusion 與 event 檔 SHA256 沿用 v1 manifest；沒有重查事件。
歷史環境是 Python 3.11，pandas/numpy/pyarrow 未鎖版本，因此不能保證 Parquet 位元組跨環境一致。
Git blob 是物件 identity，不能當成 runner 的 `table_sha256`。

安全公式摘要：`load_panel` 以 tradability 左接 RAW；`add_universe` 沿用 close≥10、
有效觀測、當日 Trading_money 排名百分位≤0.25 與既有排除名單。
`add_c_states` 計算共同列／有效 bar 暖機；`build_b_exposures` 把既有 B 事件傳播到輸出列；
`feature_state` 保留 A/B/C 獨立 flags。四項 numeric 交集且無 B 才取得限制性 label。
producer 是依賴／可算性 proxy，沒有執行正式策略或算出逐列 ATR/N60 訊號值。

## 2. 正式契約合成核對

正式來源基準：`6cf63b4f4f9d48999dbd0671bdaa444a5a612905`。
比較 `Baseline60DExitState.observe_bar`、`build_causal_raw_v2_features` 與正式
`technical_components.n_session_high`；不 mock 核心計算。

| 案例 | 固定 producer v1 | 正式契約／結果 |
| --- | --- | --- |
| 14 valid bars，close/open=100；第一根 H/L=103/97，其餘101/99 | ATR C，要求15根 | 第一 TR=6，其餘13個TR=2；ATR14=32/14 |
| 同組第15根 H/L=101/99 | ATR 非C | 最後14個TR皆2，ATR14=2 |
| 15共同 sessions 中一根停牌 | valid序列累計 | 第14個有效 bar 才 ready；audit span=15、skipped=1 |
| 第22根 high=90、open/close=100、low=99，但來源 flag=True | positive OHLC 被算 valid、ATR非C | 正式拒絕 INVALID_OHLC_GEOMETRY |
| 已暖機後當日 high 缺值 | ordinal充足，ATR仍非C | 正式拒絕當日 bar，不提供當日 ATR 評估 |
| N60 第61個共同 session | C | UNKNOWN，缺第61個 prior close |
| N60 第62個共同 session 首次突破 | 62-row可算 | True；current > prior60 max 且 previous ≤ previous-prior60 max |
| 今日等於 prior high／昨天已突破 | 可算 | False；可算不表示觸發 |
| 62-row中保留停牌／缺值列 | C | nullable UNKNOWN，不能當 False 或刪列壓縮 |

ATR 差異不是已核准的保守資格政策；是已確認的 producer／正式契約不一致。
只修 15→14 時，真實 ATR feature 受影響數 **UNKNOWN，範圍0～399**（v1 ATR C總數399）。
四項交集在此**單一暖機修正**下增量必為0：第14個有效 bar 仍不滿 LOW20 的21根需求。
這不替 OHLC／日曆其他缺陷背書，也不重申272,280已核驗。

N60 定義是 current 加 prior61，共62個共同 session；
今日 prior window=[t−60,t−1]，昨日 prior window=[t−61,t−2]。
current 嚴格大於、previous 小於等於；不含 current 的兩個60窗各自對齊。
正式 causal evaluator 保留 UNKNOWN；boolean trigger 的 False 不能代替 eligibility。
兩者都依賴呼叫端提供完整 session panel。producer 只沿每檔 tradability 列排序計數，
沒有重建或驗證完整共同日曆；刪掉一個 session 後仍可能在62列宣稱可算。
因此公式／窗口寬度一致，**真實共同日曆完整性未核驗**。

合成 B 傳播另核對 event 所在 index62：MA120 119個共同輸出至180、
N60 61個至122；index65停牌時 ATR14 14個有效輸出至76、LOW20 20個至82。
這是既有 proxy 的邊界核對，不是 CA 經濟內容／cutoff 已被證明。

## 3. Runner schema mapping

讀取基準為 PR #7 `a614ae8e369134bf1e1245e19d031a697bb8149f`；不修改該分支。
其 v1 loader 只保留五欄、enum 尚未接受真實限制性 label，不能稱已接通。
資料端 `exploration_data_contract.map_source_row` 是保留原欄的純 mapping／合成契約，
不掛入 runner、不授予執行資格。runner 任務依 issue 固定 schema 自行整合。

| 原 parquet／manifest | 對接欄位與規則 |
| --- | --- |
| `date`, `stock_id` | 原 key；不可用 inner join 丟列、不得補0；重複／空 key 拒絕 |
| `limited_exploration_label` | 原樣保留在 `source_eligibility_label`；限制性值原字進 `eligibility_status` |
| `baseline_issue_a_any/b_any/c_any` | 三個獨立 bool 原樣保留；C>B>A只決定摘要優先序，不覆蓋 flags |
| NOT_ELIGIBLE + C | `eligibility_status=UNAVAILABLE`, `reason_code=C_NOT_COMPUTABLE` |
| NOT_ELIGIBLE + B且無C | `eligibility_status=BLOCKED`, `reason_code=B_ECONOMIC_CONTENT_UNRESOLVED` |
| A-only | `ELIGIBLE_WITH_PIT_EVIDENCE_INCOMPLETE`，`reason_code=A_PIT_EVIDENCE_INCOMPLETE` |
| `raw_version_evidence_reason` | 原樣保留；亦作 `reason_detail`，不能只留摘要而刪細項 |
| `baseline_evidence_state` | 原樣保留，A-only仍為 INDETERMINATE；不轉 VERIFIED |
| 各 feature 全部原欄 | `numeric_computable`, `limited_exploration_eligible`, `issue_a/b/c`, `evidence_state`, `dominant_problem_class`, `c_reason`, `b_known`, `b_event_count`, `b_event_ids`, `b_reasons` 全保留 |
| 其餘 baseline與來源欄 | 全保留；mapping不丟未知額外欄，不刪 B/C rows |
| key無對應列 | UNKNOWN／MISSING_ELIGIBILITY_ROW；不推定 A-only、不插入原母體分母 |
| source/contract/evidence/delivery revisions | 使用manifest固定值，不以review基準或runner head替換 |
| 原母體 | `original_row_count=458315`；年度／feature仍沿原分母；不能改為候選數或持倉日數 |

`SOURCE_EVIDENCE` 與 `SYNTHETIC_FIXTURE` scope 不互換；synthetic可使用同形欄位測試，
不得把真實資料包裝成synthetic或把 A label 改成普通 ELIGIBLE。
輸出CSV若另做轉換須重新算table SHA256、列數及schema version，並另存來源Parquet identity。
已固定的日期範圍、母體及版本不可因轉換改寫。

## 4. 持倉逐日狀態契約與合成例

all_liquid資格表只有候選母體股票日，**不是持倉資料的完整calendar spine**。
訊號日以當時證據決定候選；進場依既有next-open規則及當時可得證據；不得先查未來B/C刪候選。
持倉後每一共同session，無論membership，皆需獨立holding-path證據。

必要欄位：trade/entry identity、ticker、signal_session、entry_session/phase、session/index、
trusted calendar revision、decision/as-of cutoff、`in_all_liquid`、row_present、source/contract/evidence revisions、
當日RAW有效性與可執行／停牌原因、CA/economic state及理由、估值／會計是否可靠、
適用exit輸入是否可算、baseline與feature A/B/C完整原因、資料狀態、
last_reliable_session/phase、first_problem_session/phase、censor reason、portfolio continuation status。
v1沒有提供完整持倉證據及上述所有欄；本輪不聲稱已補齊真實資料。

| 當日情境 | 狀態／處置 |
| --- | --- |
| 離開all_liquid，但有完整當日持倉證據 | OPEN，照正式持倉／出場規則延續；membership不自動造成交易出場 |
| 只有all_liquid表、持倉日缺列 | DATA_CENSORED／MISSING_HOLDING_EVIDENCE；不可補前值、補價格或當成正常未平倉 |
| 持有中首次經濟內容未解B | DATA_CENSORED + economic UNRESOLVED，保留所有原因 |
| 持有中首次必要計算／估值無法可靠C | DATA_CENSORED；確知停牌但有可靠估值／既有執行規則者不可僅因停牌武斷強平 |
| canonical合法出場且到出場phase證據可靠 | CLOSED；next-open平倉只需到該open，不讀其後high/low判定過去狀態 |
| E1結束仍有可靠持倉 | OPEN_AT_END；不讀E2補完、不強平 |
| 截尾後資料恢復 | 本record維持DATA_CENSORED；不得回填取消截尾或事後丟交易 |

相同日有多phase時依實際觀察先後判定。若問題在exit-open之後，不能污染已可靠平倉的交易；
若在exit-open前或時點未知，先截尾，不以策略出場掩蓋問題。
本輪pure daily oracle採整日保守截止：問題日不再計效果，last reliable保留前個可靠session；
它不負責判定盤中先後，呼叫端的`canonical_exit_observed`只可代表已證明可靠的phase。

合成oracle `advance_holding_data` 不接未來表，只吃逐日狀態；測試比較原進場與前綴不變：
1/2進場 → 1/3離開母體但證據可靠仍OPEN → 1/6首次B/C/缺證據變DATA_CENSORED →
1/7恢復資料仍截尾。另測可靠平倉、期末未平倉與漏／重排共同session。
這是資料契約示例，沒有改會計或runner執行路徑。

交易統計須滿足 entered = CLOSED + OPEN_AT_END + DATA_CENSORED（期末各交易恰一類）；
分別列筆數、以全部entered為分母的比例及原因。持倉日證據分母另列expected／observed／missing，
不能取代458,315候選母體。可計算交易子樣本平均不代表整體期望值。
首次不可靠且會影響現金/NAV的資金組合停止後續資金驅動執行，報BLOCKED及截止點，
不帶猜值往後跑。A持續保留，不因當日可估值變PIT VERIFIED。

## 5. 最小必要重算範圍與精確缺件（一次列出）

**沒有啟動重算。** 已確認程式差異，真實受影響計數待私有證據可讀後才可定案。

1. 上表固定 output commit 的 Parquet 原檔，blob及bytes已列；目前Git clone無私有認證，
   blob reader拒絕binary、contents reader回空內容。因此未讀逐列、未算其SHA256，不能宣稱已核驗。
2. 同一source revision的最小診斷摘錄：原母體內ATR C rows的 `date/stock_id`，
   及其原panel `valid_bar_ordinal`、`valid_observed_bar`。Parquet v1本身不保留這兩個ordinal欄，
   需由原runtime提供或只讀對應股票2015暖機～2021的RAW/tradability欄重建。
   先取 ordinal=14 且當日正式bar有效者，只更新ATR14 C/numeric/limited/evidence/reason年度與feature聚合；
   B依賴曝光與原母體不重跑。孤立暖機變更的四項交集增量為0。
3. 同一source的trusted共同session清單／版本及各ticker active span，
   RAW僅 `date,stock_id,open,max,min,close`，tradability僅
   `date,stock_id,observed_trade,valid_ohlc,reason`，範圍2015暖機～2021。
   先做calendar/有效性差異檢查，再僅對差異ticker及其受影響窗口修正：
   缺共同列影響MA120最多120個含當日窗口、N60最多62個；
   無效bar須先修valid序列，重建ATR最後14TR（含前close）與LOW20前20有效close，
   直到兩版依賴集合再次一致，並重新定位落在該區的既有B曝光。
   不因這項診斷重新查事件、全市場重新算效果或修改CA normalizer。

缺件是讀取／最小診斷材料，並非要求購買新資料。
若只有聚合可取得，受影響數維持UNKNOWN，不把上限或合成例數字冒充實際數。

## 6. 可重現驗證

公開環境：

```bash
python -m pytest tests/test_aq_exp_data_001_r2.py \
  tests/test_baseline_60d_exit_state.py tests/test_causal_raw_v2.py -q
```

可讀private producer者，先取上表exact revision，再指定路徑重跑同一指令：

```bash
AQ_COVERAGE_PRODUCER=/path/to/private/scripts/astraquant_aq_exp_data_001.py \
  python -m pytest tests/test_aq_exp_data_001_r2.py \
  tests/test_baseline_60d_exit_state.py tests/test_causal_raw_v2.py -q
```

測試先驗Git blob identity，只import producer函式餵合成資料，從不呼叫其main。
本輪Python3.12環境：**58 passed**；包括4個直接private producer合成測試。
無private程式時這4項明示skip，不偽裝已執行。
未改formal gate、CA/accounting、normalizer、runner分支或任何真實逐列檔。
交付僅供審查，不合併、不解除gate；真實效果工作仍需Owner另行明確授權。
