#!/usr/bin/env python3
"""Run frozen dividend component reconciliation and write PRIVATE row-level files.

The caller controls the output location.  For AstraQuant governance, row-level
outputs belong in an authorized private location; only aggregate/public
summaries may be copied into the public repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from astraquant.data.dividend_reconciliation import (
    PrimaryClass,
    ReconciliationInputs,
    TRANSFORM_VERSION,
    aggregate_reconciliation,
    finmind_components,
    finmind_source_rows,
    official_rows,
    reconcile_dividend_components,
)

FROZEN_SOURCE = "fb8b042b46dc38838d103544ca17da10286c7bfe"
START = pd.Timestamp("2015-01-01")
E1_START = pd.Timestamp("2016-01-04")
END = pd.Timestamp("2021-12-31")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _event_component_mapping(
    events: pd.DataFrame,
    components: pd.DataFrame,
    official: pd.DataFrame,
) -> pd.DataFrame:
    event_id = {
        (str(r.stock_id), pd.Timestamp(r.event_date).normalize()): r.economic_event_id
        for r in events.itertuples(index=False)
    }
    rows: list[dict[str, object]] = []
    for r in components.itertuples(index=False):
        key = (str(r.stock_id), pd.Timestamp(r.effective_date).normalize())
        rows.append({
            "economic_event_id": event_id[key],
            "side": "NORMALIZED_COMPONENT",
            "source_row_id": r.source_row_id,
            "component_or_row_id": r.component_id,
            "stock_id": r.stock_id,
            "event_date": pd.Timestamp(r.effective_date).normalize(),
            "component_kind": r.component_kind,
            "cash_per_share": r.cash_per_share,
            "share_multiplier": r.share_multiplier,
            "source_distribution_value": r.source_distribution_value,
            "source_unit_semantics": r.source_unit_semantics,
            "source_name": r.source_name,
        })
    for r in official.itertuples(index=False):
        if pd.isna(r.event_date):
            continue
        day = pd.Timestamp(r.event_date).normalize()
        key = (str(r.stock_id), day)
        if key not in event_id:
            continue
        rows.append({
            "economic_event_id": event_id[key],
            "side": "OFFICIAL_SOURCE_ROW",
            "source_row_id": r.official_row_id,
            "component_or_row_id": r.official_row_id,
            "stock_id": r.stock_id,
            "event_date": day,
            "component_kind": "EVENT_ROW",
            "cash_per_share": r.cash_per_share,
            "share_multiplier": r.share_multiplier,
            "source_distribution_value": r.rights_ratio,
            "source_unit_semantics": (
                f"cash={r.cash_unit_semantics};stock={r.stock_unit_semantics}"
            ),
            "source_name": r.source_name,
        })
    return pd.DataFrame(rows)


def _aggregate_with_period(events: pd.DataFrame) -> pd.DataFrame:
    blocks: list[pd.DataFrame] = []
    periods = (
        ("WARMUP", START, E1_START - pd.Timedelta(days=1)),
        ("E1", E1_START, END),
        ("WARMUP_PLUS_E1", START, END),
    )
    for name, begin, finish in periods:
        x = events[events["event_date"].between(begin, finish)].copy()
        if x.empty:
            continue
        a = aggregate_reconciliation(x)
        a.insert(0, "period", name)
        blocks.append(a)
    return pd.concat(blocks, ignore_index=True) if blocks else pd.DataFrame()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dividend", required=True)
    p.add_argument("--official", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--source-revision", default=FROZEN_SOURCE)
    p.add_argument("--acquired-at", required=True)
    p.add_argument("--program-revision", required=True)
    args = p.parse_args()

    if args.source_revision != FROZEN_SOURCE:
        raise SystemExit("BLOCKED: this audit version is frozen to the approved source revision")

    dividend_path = Path(args.dividend)
    official_path = Path(args.official)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    dividend_sha = sha256(dividend_path)
    official_sha = sha256(official_path)
    dividend = pd.read_parquet(dividend_path)
    official_df = pd.read_csv(official_path, dtype=str).fillna("")

    inputs = ReconciliationInputs(
        source_revision=args.source_revision,
        dividend_blob_sha=dividend_sha,
        official_blob_sha=official_sha,
        acquired_at=args.acquired_at,
    )

    events, finmind_raw, components = reconcile_dividend_components(
        dividend,
        official_df,
        inputs=inputs,
        start=START.date().isoformat(),
        end=END.date().isoformat(),
    )
    official_norm = official_rows(
        official_df,
        source_revision=args.source_revision,
        official_blob_sha=official_sha,
    )
    official_norm = official_norm[
        official_norm["event_type"].eq("ex_right_dividend")
        & official_norm["event_date"].between(START, END)
    ].copy()

    mapping = _event_component_mapping(events, components, official_norm)
    aggregate = _aggregate_with_period(events)

    finmind_raw.to_csv(out / "finmind_source_rows.csv", index=False, encoding="utf-8-sig")
    components.to_csv(out / "normalized_components.csv", index=False, encoding="utf-8-sig")
    official_norm.to_csv(out / "official_source_rows.csv", index=False, encoding="utf-8-sig")
    mapping.to_csv(out / "source_event_component_mapping.csv", index=False, encoding="utf-8-sig")
    events.to_csv(out / "event_reconciliation.csv", index=False, encoding="utf-8-sig")
    aggregate.to_csv(out / "aggregate_reconciliation.csv", index=False, encoding="utf-8-sig")

    primary_counts = {
        cls.value: int(events["primary_class"].eq(cls.value).sum())
        for cls in PrimaryClass
    }
    if sum(primary_counts.values()) != len(events):
        raise AssertionError("primary classification does not conserve event count")

    manifest = {
        "transform_version": TRANSFORM_VERSION,
        "program_revision": args.program_revision,
        "source_revision": args.source_revision,
        "acquired_at": args.acquired_at,
        "period": {
            "warmup_start": START.date().isoformat(),
            "e1_start": E1_START.date().isoformat(),
            "e1_end": END.date().isoformat(),
        },
        "input_fingerprints": {
            "dividend_sha256": dividend_sha,
            "official_sha256": official_sha,
        },
        "input_rows": {
            "dividend_all_horizon": int(len(dividend)),
            "official_all_horizon": int(len(official_df)),
            "official_ex_right_dividend_warmup_e1": int(len(official_norm)),
        },
        "output_rows": {
            "finmind_source_rows_all_horizon": int(len(finmind_raw)),
            "normalized_components_warmup_e1": int(len(components)),
            "economic_events_warmup_e1": int(len(events)),
            "source_event_component_mapping": int(len(mapping)),
        },
        "primary_class_counts_warmup_e1": primary_counts,
        "formal_e1_feature_artifact_built": False,
        "strategy_effects_computed": False,
        "canonical_ca_engine_modified": False,
        "row_level_delivery_private": True,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # stdout is aggregate-only by design.
    e1 = events[events["event_date"].between(E1_START, END)]
    print(json.dumps({
        "transform_version": TRANSFORM_VERSION,
        "events_warmup_e1": int(len(events)),
        "events_e1": int(len(e1)),
        "normalized_components_warmup_e1": int(len(components)),
        "official_rows_warmup_e1": int(len(official_norm)),
        "primary_conservation": int(sum(primary_counts.values())),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
