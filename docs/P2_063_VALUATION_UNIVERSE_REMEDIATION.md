# P2-063 Valuation-Universe Remediation

Status: **BLOCKED — SOURCE OWNER ACTION REQUIRED**

P2-063 separates the two universes:

- **Candidate universe:** unchanged. Breakout research and the top-25%-turnover eligible universe remain restricted to four-digit ordinary-share IDs matching `[1-9]\\d{3}`.
- **Valuation universe:** may include securities passively received through explicit corporate actions, including listed preferred shares such as `2883B`. These securities may be marked and exited but never become breakout candidates merely because they are markable.

## Confirmed source-side blocker

`bibobo2266/minervini_picks` is read-only to AstraQuant. At source commit `4b373060b2e65fce2fad7bbdbfddb62174d8bec6`, the following lines silently remove letter-suffixed listed securities from the execution/valuation path:

- `scripts/fetch_finmind_execution_year.py:53`
- `scripts/fetch_finmind_execution_year_safe.py:66`
- `scripts/fetch_finmind_execution_year_resume.py:53`

Each applies `stock_id.str.fullmatch(r"[1-9]\\d{3}")` after the FinMind response.

The canonical assembly path also restricts the RAW valuation universe at:

- `scripts/assemble_finmind_execution.py:57`

and `build_tradability.py` removes them again at:

- `scripts/build_tradability.py:27`

The owner-side remediation must widen only these valuation/execution paths to admit listed letter-suffixed equity IDs such as `2883B`. The research/signal filters in AstraQuant remain numeric-four-digit only.

## Required owner-side backfill

Backfill canonical RAW and tradability for `2883B` from 2021-12-30 onward through the window required by P2-062. Do not create adjusted-price substitutes and do not synthesize fills.

After the source update, AstraQuant will hard-gate:

1. P2-060 exclusion ledger SHA remains `379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134`.
2. Frozen top-25%-turnover eligible-universe distinct ticker count remains **1,986**.
3. Candidate signal IDs remain four-digit ordinary-share IDs only.
4. `2883B` has canonical RAW/tradability coverage for the valuation window.
5. A held successor outside the candidate universe can still be marked.

No widening of the candidate universe is authorized.
