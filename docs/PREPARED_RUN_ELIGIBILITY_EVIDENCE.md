# PreparedResearchRun Eligibility Evidence Lifecycle

Status: **SYNTHETIC INTEGRITY / PROVENANCE BINDING ONLY — FORMAL_RESEARCH REMAINS BLOCKED**

This contract carries successful existing feature-hydration checks into one
`PreparedResearchRun`. It does not create a new data-approval standard and it
does not authorize formal research.

## Existing validation source

`FeaturePanelIntegrator.hydrate()` remains the source of the underlying checks:

- configured artifact name, source revision, formula version, and epoch match
  the manifest;
- the canonical panel is inside the manifest period;
- required feature availability satisfies the configured strategy requirement
  when `verified_only=True`;
- each actually used yearly parquet matches the manifest SHA256;
- requested feature columns exist;
- logical keys are unique;
- declared availability/cutoff rules pass when their metadata is present.

Only after those checks succeed does hydration emit
`FeaturePanelEligibilityEvidence`.

## Feature hydration evidence

The evidence records the inputs that were actually used:

- integration-config fingerprint;
- `verified_only` and strategy-required availability status;
- manifest path and content SHA256;
- artifact name, source revision, feature formula version, epoch, and closed
  manifest period;
- each used yearly artifact path/name/SHA256/row declaration;
- required feature columns, dependencies, warmup, and availability status;
- cutoff contracts exercised by the hydrated frame;
- hydrated-panel date range and content fingerprint;
- hydration-audit fingerprint;
- evidence scope and explicit source.

`SYNTHETIC_FIXTURE` is an explicit test scope. The default
`INTEGRITY_ONLY` scope cannot be used to execute the synthetic baseline path.

## Prepared-run binding

`ResearchConfigEngine.prepare_hydrated()` revalidates the join result against
the current manifest/artifact bytes and hydrated-frame fingerprint, prepares
the real research run, then creates `PreparedRunEligibilityEvidence`.

That run-level evidence additionally binds:

- `StrategyRunConfig`, universe config, signal config, exit config, and final
  prepared portfolio policy;
- the compiled `CompiledExitPlan` fingerprint, so replacing the plan cannot
  change whether evidence validation runs;
- `SignalContext.source_revision` and availability policy;
- universe-mask fingerprint;
- signal-frame fingerprint;
- candidate-frame fingerprint;
- the exact feature hydration evidence above;
- an explicit ordered execution-session contract when supplied during
  `prepare_hydrated()`.

The execution-session contract is separate from the hydration panel range.
Hydration may include warmup dates that are not executable sessions. The
declared execution calendar must be strictly increasing, unique, non-empty,
and contained inside the validated panel/manifest date coverage; its exact
ordered sequence is fingerprinted. A later shorter, reordered, extended, or
out-of-range calendar is rejected.

The identity is content-based. It does not use Python object identity.

## Validation before simulation

For the opt-in baseline synthetic path, `simulate_prepared()` recompiles the
stored `ExitConfig` and requires the stored compiled plan to match it. The
decision to enforce baseline evidence therefore does not trust a replaceable
`prepared.exit_plan`.

Before execution, the engine binds and checks the actual
`simulator.policy.config`, the exact execution-session sequence, the compiled
exit plan, and the candidate frame against the prepared evidence. Cheap
in-memory mismatches are rejected before rereading feature artifact bytes.
Only after those execution-layer identities agree does the engine revalidate
the full prepared/config/artifact evidence.

`CanonicalStrategySimulator.run()` enforces the same execution binding again
at the direct simulator boundary. A direct baseline call without
`PreparedRunEligibilityEvidence` is rejected before construction of the
execution trading calendar, RAW market-data reads, order creation, or holding
mutation. Non-baseline legacy calls remain outside this opt-in evidence path.

A synthetic run fails closed when, among other cases:

- eligibility evidence is absent;
- evidence is not `SYNTHETIC_FIXTURE`;
- hydration used `verified_only=False`;
- a required feature is no longer VERIFIED;
- manifest or artifact bytes changed;
- source revision, formula version, epoch, period, required-field contract, or
  integration config changed;
- the hydrated panel/audit changed;
- prepared run config/policy, universe mask, signal frame, or candidates changed;
- the compiled exit plan differs from the one produced during preparation;
- the actual simulator policy differs from the prepared policy;
- the execution calendar is reordered, shortened, extended, duplicated, or
  outside the validated date coverage;
- direct baseline simulator execution omits the prepared evidence binding;
- evidence from one run is attached to a different run.

Re-hydration/re-preparation is required after such a change.

## Authorization boundary

Two questions remain deliberately separate:

1. **Does this evidence still match the data and prepared run that produced it?**
   This revision implements and synthetically tests that integrity/provenance
   question.
2. **Is FORMAL_RESEARCH authorized to execute?**
   **No.** FORMAL_RESEARCH remains unconditionally blocked by the existing
   baseline simulation gate.

The current evidence objects are not formal approval tokens. Synthetic evidence
cannot unlock formal mode, and caller-provided `VERIFIED`/source text is not a
substitute for canonical formal eligibility.

These SHA256/fingerprint checks are software integrity/provenance checks inside
the research process. They are not presented as a security system against a
malicious actor who can rewrite code, data, and evidence together.

## Regression location

Primary package coverage:

- `tests/test_feature_panel_integration.py`
- `tests/test_baseline_60d_simulator_integration.py`

The baseline synthetic E2E uses the real
`FeaturePanelIntegrator -> ResearchConfigEngine.prepare_hydrated() ->
PreparedResearchRun -> CanonicalStrategySimulator` path.
