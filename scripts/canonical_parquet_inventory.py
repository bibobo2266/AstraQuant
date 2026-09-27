#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/CANONICAL_PARQUET_INVENTORY.md"))

FAMILIES = ("raw", "adj", "reference", "fundamentals", "inst", "kbar")
DATE_CANDIDATES = (
    "date", "trade_date", "available_date", "known_date", "effective_date",
    "ex_date", "payment_date", "record_date", "datetime", "timestamp",
)
PIT_TOKENS = ("available", "known", "effective", "recorded", "publish", "revision", "download")
PROV_TOKENS = ("source", "provider", "dataset", "version", "revision", "download", "updated")

def esc(v: object) -> str:
    return str(v).replace("|", "/").replace("\n", " ")

def minmax_from_metadata(pf: pq.ParquetFile, name: str):
    names = pf.schema_arrow.names
    if name not in names:
        return None, None
    idx = names.index(name)
    lows, highs = [], []
    for i in range(pf.metadata.num_row_groups):
        stats = pf.metadata.row_group(i).column(idx).statistics
        if stats is not None and stats.has_min_max:
            lows.append(stats.min)
            highs.append(stats.max)
    if not lows:
        return None, None
    try:
        return min(lows), max(highs)
    except TypeError:
        return lows[0], highs[-1]

def schema_hash(pf: pq.ParquetFile) -> str:
    payload = "|".join(f"{f.name}:{f.type}" for f in pf.schema_arrow).encode()
    return hashlib.sha256(payload).hexdigest()[:12]

def matches(names, tokens):
    return [n for n in names if any(t in n.lower() for t in tokens)]

def inspect(path: Path) -> dict[str, object]:
    rel = path.relative_to(SOURCE_ROOT).as_posix()
    family = rel.split("/", 1)[0]
    pf = pq.ParquetFile(path)
    names = pf.schema_arrow.names
    date_field = next((n for n in DATE_CANDIDATES if n in names), None)
    lo, hi = minmax_from_metadata(pf, date_field) if date_field else (None, None)
    return {
        "family": family,
        "path": rel,
        "size_mib": round(path.stat().st_size / 1024 / 1024, 2),
        "rows": int(pf.metadata.num_rows),
        "row_groups": int(pf.metadata.num_row_groups),
        "columns": len(names),
        "schema_hash": schema_hash(pf),
        "date_field": date_field or "NONE",
        "date_min": lo if lo is not None else ("N/A" if not date_field else "NO_METADATA_STATS"),
        "date_max": hi if hi is not None else ("N/A" if not date_field else "NO_METADATA_STATS"),
        "pit_fields": ", ".join(matches(names, PIT_TOKENS)) or "NONE OBSERVED",
        "provenance_fields": ", ".join(matches(names, PROV_TOKENS)) or "NONE OBSERVED",
    }

def main() -> None:
    if not SOURCE_ROOT.is_dir():
        raise SystemExit("BLOCKED: source root missing: " + str(SOURCE_ROOT))

    files = []
    for family in FAMILIES:
        root = SOURCE_ROOT / family
        if root.is_dir():
            files.extend(sorted(root.glob("*.parquet")))

    if not files:
        raise SystemExit("BLOCKED: no canonical parquet files found")

    rows = [inspect(p) for p in files]
    by_family = defaultdict(lambda: {"files": 0, "rows": 0, "size_mib": 0.0, "schemas": set()})
    for r in rows:
        s = by_family[r["family"]]
        s["files"] += 1
        s["rows"] += r["rows"]
        s["size_mib"] += r["size_mib"]
        s["schemas"].add(r["schema_hash"])

    lines = [
        "# Canonical Parquet Inventory",
        "",
        "Status: **DONE — metadata inventory only**",
        "",
        "This inventory is generated from a transient, read-only checkout of the frozen source repository.",
        "It reads parquet footers/metadata only. It does not perform null, duplicate, or unique-ticker scans.",
        "",
        "## Family summary",
        "",
        "| Family | Parquet files | Total rows (sum of file metadata) | Size MiB | Distinct schema hashes |",
        "|---|---:|---:|---:|---:|",
    ]
    for family in FAMILIES:
        s = by_family.get(family)
        if not s:
            continue
        lines.append(
            f"| {family} | {s['files']} | {s['rows']:,} | {s['size_mib']:.2f} | {len(s['schemas'])} |"
        )

    lines += [
        "",
        "## File inventory",
        "",
        "| Family | File | Size MiB | Rows | Row groups | Columns | Schema hash | Date field | Min | Max | PIT fields | Provenance fields |",
        "|---|---|---:|---:|---:|---:|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| {family} | {path} | {size_mib} | {rows:,} | {row_groups} | {columns} | {schema_hash} | "
            "{date_field} | {date_min} | {date_max} | {pit_fields} | {provenance_fields} |".format(
                family=esc(r["family"]), path=esc(r["path"]), size_mib=r["size_mib"],
                rows=r["rows"], row_groups=r["row_groups"], columns=r["columns"],
                schema_hash=r["schema_hash"], date_field=esc(r["date_field"]),
                date_min=esc(r["date_min"]), date_max=esc(r["date_max"]),
                pit_fields=esc(r["pit_fields"]), provenance_fields=esc(r["provenance_fields"]),
            )
        )

    lines += [
        "",
        "## Interpretation limits",
        "",
        "- Row totals are metadata sums, not deduplicated logical row counts.",
        "- Date ranges depend on parquet statistics; NO_METADATA_STATS means a later targeted scan is required.",
        "- Schema hashes detect structural differences but do not prove semantic compatibility.",
        "- Nulls, duplicate keys, ticker coverage, PIT ordering, and cross-file reconciliation are separate tasks.",
        "",
        "## Next small task",
        "",
        "Run targeted key/null/duplicate checks by family, beginning with RAW and adjusted daily price files.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
