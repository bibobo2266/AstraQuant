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
