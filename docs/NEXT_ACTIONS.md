# Next Actions

## NOW

Phase-1 data/runtime audit is complete. Source remediation stays frozen.

Proceed with Phase-2 execution/accounting repair in small, recoverable tasks:

1. define an AstraQuant-owned dual-coordinate market-data interface
2. require declared signal price semantics
3. require RAW for entry, stop observation/fill, exit, sizing, and mark-to-market
4. enforce tradability before every intended fill
5. remove reverse-engineered pseudo-RAW from adjusted/dividend factors
6. route corporate actions through explicit economic events
7. reconcile share count, cash, receivables, and NAV
8. run an accounting-only dry replay
9. unlock portfolio-performance inspection only if every accounting gate passes

## CURRENT GATE

- RAW history: READY on the frozen eligible denominator
- Adjusted history: READY_WITH_LIMITATION for research only; canonical masking required
- Corporate actions: READY_WITH_LIMITATION; unknown known_date remains unknown
- PIT industry: READY_WITH_LIMITATION; uncovered history remains excluded
- Tradability: READY_WITH_LIMITATION; block states must be enforced
- PIT-bearing fundamentals: PASS_WITH_LIMITATIONS under declared availability rules
- source repository is consumed read-only during normal AstraQuant research; owner-authorized P2-063 source remediation is a narrow exception
- P1-007 is the canonical runtime-access mode: GitHub Actions transient read-only checkout via MINERVINI_READ_TOKEN; no local sibling-directory mount action remains
- Phase-1 summary: `docs/DATA_AUDIT.md`

## PERFORMANCE LOCK

Do not use CAGR, Sharpe, MAR, MDD, strategy rankings, or model comparisons as acceptance criteria until:

- entry/stop/exit/sizing/mark all use RAW
- no adjusted execution fallback exists
- tradability is enforced
- share count reconciles
- cash and receivables reconcile
- corporate actions reconcile
- NAV reconciles
- signal source semantics are declared

## RESEARCH AFTER DATA/ACCOUNTING GATES

1. construct canonical PIT dataset
2. materialize feature registry
3. preregister EXP-R001
4. run EXP-R001 only after all required gates pass
5. proceed to EXP-R002 / Complexity Lab only through the promotion protocol
