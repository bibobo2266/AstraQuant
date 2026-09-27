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
