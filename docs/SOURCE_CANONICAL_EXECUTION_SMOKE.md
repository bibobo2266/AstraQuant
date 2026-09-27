# Source Canonical Execution Service Smoke

Status: **PASS**

This smoke test routes real source data through CanonicalExecutionService. It is not a strategy backtest.

## Window

- ticker: 2330
- entry session: 2026-09-23
- exit session: 2026-09-24
- sizing RAW open: 2475.0
- entry RAW open: 2475.0
- mark RAW close: 2500.0
- exit RAW close: 2475.0

## Gates

| Gate | Result |
|---|---|
| signal_declared | PASS |
| sizing_raw | PASS |
| entry_raw | PASS |
| mark_raw | PASS |
| exit_raw | PASS |
| position_flat_after_exit | PASS |
| settlements_flat | PASS |
| pre_exit_nav_positive | PASS |
| canonical_service_path_used | PASS |
| no_adjusted_fallback | PASS |

The numeric cash/NAV values are not interpreted as performance evidence. The purpose is path validation only.
