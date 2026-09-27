# Data Source Policy

## Boundary

AstraQuant may modify only the `bibobo2266/AstraQuant` repository.

`bibobo2266/minervini_picks` is an external source repository and must not be modified by AstraQuant.

## Intended runtime layout

```text
workspace/
├─ AstraQuant/          # read/write by AstraQuant
└─ minervini_picks/     # read-only source checkout or mount
   └─ data/
```

The source adapter should be configured to a filesystem path such as:

```text
../minervini_picks/data
```

The exact path is runtime configuration, not a hard-coded repository assumption.

## SourceDataAdapter contract

Allowed operations:

- existence checks
- directory/file listing
- file metadata inspection
- Parquet schema inspection
- Parquet reads

Forbidden by design:

- write
- update
- rename
- delete

All path resolution must remain underneath the configured source root.

## Derived data

AstraQuant-owned derived datasets are retained separately from source data.

Recommended runtime location:

```text
AstraQuant/data_derived/
```

Derived datasets may include canonical PIT tables, features, fold assignments, predictions, and validation artifacts. Their manifests and lineage metadata belong in Git even when large binary Parquet outputs do not.

## Current state

The source-data runtime is not connected yet. Data inspection and research remain blocked until the user declares the cleaned source dataset ready and provides an execution environment that can expose it read-only.
