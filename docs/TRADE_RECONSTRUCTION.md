# Canonical FIFO Trade Reconstruction

Status: **IMPLEMENTED_PENDING_CI**

AstraQuant trade-level reconstruction must not infer position history from fills alone. Canonical holdings can also change through explicit corporate-action share mutations and successor-security conversions.

The reconstruction utility in `src/astraquant/portfolio/trade_reconstruction.py` consumes the chronological union of:

- fills,
- `PositionShareMutation` events, and
- `PositionSecurityConversion` events.

Share mutations rescale quantity and per-share cost while preserving total lot cost basis. Successor conversions move the original FIFO lots to the successor ticker while preserving original acquisition time and economic cost basis. Therefore a later 3715 sale can close a lot originally acquired as 6251.

This utility is intended for future trade-level diagnostics such as win rate, payoff ratio, expectancy, and holding-period statistics. Those diagnostics must not rebuild lots from fills alone.

Cash merger/extinguishment economics remain represented by the canonical CA accounting path rather than by synthetic sell fills; any future trade-level statistic that treats a cash extinguishment as a realized exit must explicitly join the corresponding cash-entitlement event instead of inventing a market fill.
