# Dataset and Run Lineage

AstraQuant must be able to answer:

> Which exact source data, code, configuration, features, and trial produced this result?

## Dataset manifest

Each canonical or research dataset should receive a stable `dataset_id` and record:

- source repository/path
- source version or fingerprint
- creation timestamp
- code version
- configuration version
- row count
- effective date range
- PIT validation state
- caveats

Large Parquet outputs do not need to be committed to Git for lineage to work. Their manifests do.

## Run manifest

Every meaningful attempt counts as a trial. A run manifest records:

- run ID
- experiment ID
- dataset ID
- code version
- parameters
- exact feature versions
- trial number
- selection role
- output artifacts

## Selection role

A run must state how its data was used, for example:

- `train`
- `validation`
- `walk_forward_test`
- `locked_oos`

A set used repeatedly for keep/drop/tune decisions must not be relabeled as untouched locked OOS later.
