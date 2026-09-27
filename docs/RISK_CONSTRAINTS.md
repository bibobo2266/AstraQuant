# Risk Constraint Architecture

Risk checks are explicit, composable, and separate from alpha logic.

Each constraint receives a RiskContext and returns a RiskCheckResult containing:

- constraint name
- pass/fail
- reason

The core framework does not hard-code portfolio thresholds that have not been approved yet.

A generic maximum-position-count constraint is included as an interface example. Strategy-specific values such as maximum positions, position sizing, stop distance, pyramiding limits, concentration limits, and cash buffers will be frozen later through explicit configuration and validation.
