# Persistence Conventions

Governance records such as human reviews, audit links, and research result summaries should be persisted append-only.

The initial implementation uses JSON Lines because it is simple, inspectable, and does not require a database.

## Rules

- append new records
- do not update historical records in place
- corrections are new records with new IDs
- large research artifacts remain in retained artifact/data-derived storage
- the external source-data repository is never used as a persistence target

A database can replace JSONL later without changing the domain contracts.
