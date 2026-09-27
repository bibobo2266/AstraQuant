# AstraQuant Complexity Lab

> Prove that complexity earns its place.

The lab is a governance layer for deciding whether additional indicators, features, or model complexity create stable incremental value rather than prettier in-sample results.

## Entry rule

No model enters the lab until the canonical point-in-time dataset and feature registry are validated.

## Required comparisons

Every complex candidate must be compared under the same universe, labels, walk-forward folds, transaction-cost assumptions, execution rules, and portfolio construction.

Reference baselines:

1. simple linear/logistic model
2. small-feature LightGBM model
3. full candidate model

## Tests

### Redundancy map

Measure Pearson/Spearman correlation, mutual information, and feature-family clustering. Highly redundant indicators must justify their incremental contribution.

### Complexity curve

Evaluate frozen feature counts such as 5, 10, 20, 40, 80, and 150. Selection rules must be defined before the run and every attempted configuration counts as a trial.

### Family ablation

Remove one feature family at a time: trend/relative strength, persistence, volatility/contraction, volume/participation, liquidity, fundamentals, fundamental acceleration, institutional flow, market regime, and cross-sectional context.

### Feature knockout

Compare the full model against variants that remove technical features, institutional features, fundamentals, regime features, top-ranked features, or replace top-ranked features with noise.

### Personality stability

Across folds and regimes track top-feature overlap, rank stability, direction stability, family-importance stability, and SHAP-rank stability where applicable.

### Shadow model

Run a deliberately simple model beside the complex model and record agreement, disagreement, and subsequent outcomes. Disagreement is evidence to study, not an automatic trading signal.

### Noise robustness

Inject irrelevant features and perturb inputs within defensible ranges. A candidate that changes materially under small irrelevant perturbations requires review.

## Promotion principle

Complexity is admitted only when incremental out-of-sample value survives robustness checks and does not rely on a narrow parameter choice, unstable feature personality, excessive turnover, or repeated reuse of the same validation period.

The locked future OOS set is never used for feature selection, model selection, threshold tuning, or Optuna search.
