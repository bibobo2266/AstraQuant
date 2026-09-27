# Validation Ladder

AstraQuant reports the strongest level actually demonstrated. Higher-level evidence does not imply that missing lower levels passed.

| Level | Evidence |
|---:|---|
| 11 | Locked future out-of-sample |
| 10 | Rolling walk-forward out-of-sample |
| 9 | Temporal replication |
| 8 | Execution sensitivity survived |
| 7 | Parameter plateau survived |
| 6 | Temporal replay passed |
| 5 | Placebo / falsification survived |
| 4 | Multiple-test adjusted |
| 3 | Cluster/block-aware inference |
| 2 | Descriptive association |
| 1 | Mechanism plausible |

## Locked OOS rule

Any dataset used to decide whether to keep, drop, tune, combine, or re-parameterize a model is no longer untouched out-of-sample data.

> Iterated OOS is validation, not locked OOS.

Optuna, manual tuning, feature selection, threshold selection, and model comparison must not touch the locked future OOS set.
