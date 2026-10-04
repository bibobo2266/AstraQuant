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
  portfolio policy;
- `SignalContext.source_revision` and availability policy;
- universe-mask fingerprint;
- signal-frame fingerprint;
- candidate-frame fingerprint;
- the exact feature hydration evidence above.

The identity is content-based. It does not use Python object identity.

## Validation before simulation

For the opt-in baseline synthetic path, `simulate_prepared()` applies the
runtime mode gate first, then revalidates the prepared evidence before the
canonical simulator reads execution market data.

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
