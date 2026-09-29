# Decision Log

## DEC-001 — Repository isolation

**Status:** Accepted

### Problem

AstraQuant must be built independently without changing any other repository.

### Decision

All write operations are restricted to:

```text
bibobo2266/AstraQuant
```

No other repository may be modified.

### Consequences

- external repositories may be studied as references only when explicitly needed
- production projects remain untouched
- integration, if any, will be a later human-approved step

### Revisit condition

Only if the user explicitly changes this boundary.


## DEC-002 — External source data remains immutable

**Status:** Accepted

### Problem

The source parquet data is currently being cleaned in another repository and must not be changed by AstraQuant.

### Decision

AstraQuant will use a read-only `SourceDataAdapter` when source data is eventually connected. The adapter exposes inspection and read operations only and rejects paths outside its configured root.

AstraQuant-owned derived datasets are separate from source data.

### Consequences

- no source-data copying is required by the architecture
- no write/update/delete/rename API exists on the source adapter
- source-dependent research remains blocked until the user declares the dataset final
- framework development can continue without accessing the source repository

### Revisit condition

Only if the user explicitly changes the source-data boundary.

## DEC-003 — Do not research on moving data

**Status:** Accepted

### Problem

Running factor research, ML, or backtests while the source dataset is still changing would create unstable evidence and unnecessary reruns.

### Decision

No factor calculation, backtest, ML training, or strategy recommendation will begin until the user declares the cleaned source dataset ready and the data audit gates pass.

### Consequences

Framework and validation infrastructure may continue to be developed independently of source data.


## DEC-004 — Corporate actions are explicit economic position mutations

**Status:** Accepted

### Problem

The original fill-only position invariant is correct for discretionary/system decisions but incomplete for exogenous economic events such as stock splits, stock dividends, and capital reductions. Treating those events as synthetic trades would corrupt order/fill semantics and realized P&L.

### Decision

Position quantity may change through exactly two governed paths:

1. executed trade `Fill` events; and
2. explicit corporate-action share mutations carrying an event ID, effective time, share multiplier, and provenance.

Signals, research results, recommendations, DecisionPackets, and human approvals still cannot mutate positions.

Corporate-action quantity mutations preserve total cost basis by inversely adjusting average cost.

### Consequences

- no synthetic trade is invented for a split/reduction;
- share-count reconciliation becomes possible on RAW economic coordinates;
- duplicate corporate-action event IDs are rejected;
- source events without interpretable share-mutation fields remain unsupported rather than inferred from adjusted prices.

### Revisit condition

Only if a different accounting representation is explicitly adopted and preserves equivalent economic/audit semantics.


## DEC-005 — Narrow P2-063 source-repair authorization

**Status:** Accepted

### Decision

owner 於 2026-09-29 明確授權 `bibobo2266/minervini_picks` 的 P2-063 最小來源修復，
因此本次視為 DEC-001 / DEC-002 的明確、有限例外。

授權範圍只包含：

- 五個 execution / tradability ticker regex 從四位純數字放寬為可帶一個大寫字母後綴；
- 2883B 自 2021-12-30 起、涵蓋 P2-062 所需窗口的 RAW 與 tradability 定向回補。

不得藉此更動研究候選母體、P2-060 排除名單、調整價替代品或合成成交。
本次修復完成後，source repo 再度回到 AstraQuant 正常研究流程的唯讀依賴。


## DEC-006 — Defer overnight futures and U.S. context

**Status:** DEFERRED_BY_OWNER

owner 於 2026-09-29 決定暫緩。理由不是資料不存在，而是成本效益：
該觀察每交易日僅產生一個方向判斷，統計密度低；而正確實作需處理台美
日光節約時間、假日錯開、ADR 交易日對應、SOX/Nasdaq 收盤時戳、夜盤
契約轉倉、期貨對現貨尺度等六項 look-ahead 風險點，任一處理錯誤都會
產生看似優異但虛假的結果。

解除條件：當 AstraQuant 具備帶明確時戳語意的夜盤與海外 canonical 來源，
且該來源能提供 known_at 欄位時，重新啟動。

OBS-001 的元件契約與必要欄位定義保留不動。


## DEC-007 — Defer intraday data acquisition until PIT contract exists

**Status:** DEFERRED_BY_OWNER

owner 於 2026-09-29 查證 FinMind `TaiwanStockKBar` 後決定暫緩。

已確認限制：

1. 個股自 2019-01-01 起，無法與 2016-01-04 起的凍結研究窗使用相同共同母體。
2. 無 `available_at / known_at`；資料於 15:50 盤後整表更新，PIT 時戳需 AstraQuant 自行宣告。
3. 同源曾有無版本號回溯重製；若未自存快照與 hash，PIT 不可重現。
4. 僅有分 K，15 分 / 60 分聚合邊界需先明確宣告。
5. 2019-02-20~22、2019-05-16 有已知個股缺漏，且 volume 單位可在不同市場混用「張」與「股」。

決策：技術上可補，但啟動前先完成分 K 資料契約（時戳語意、聚合邊界、
快照/hash、缺漏處理），而不是先抓資料。

因此 OBS-005 的 60 分 / 15 分部分與 OBS-002 的 60 分版本維持 BLOCKED；
不得以日線資料合成盤中序列替代。
