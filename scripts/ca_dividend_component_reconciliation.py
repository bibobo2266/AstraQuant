#!/usr/bin/env python3
"""Component-level dividend/corporate-action reconciliation.

Scope:
- fixed source snapshot supplied by the caller;
- 2015 warmup + E1 by default;
- dividend/ex-right components only.

This is an audit tool.  It does not modify canonical accounting/execution,
does not build a formal feature artifact, and does not compute strategy effects.

Private row-level outputs must be written outside the public AstraQuant repo by
the caller.  Public use should retain only aggregate summaries/manifests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

VERSION = "ca_dividend_component_reconciliation_v1"
DEFAULT_SOURCE_REVISION = "fb8b042b46dc38838d103544ca17da10286c7bfe"
DEFAULT_START = "2015-01-01"
DEFAULT_E1_START = "2016-01-04"
DEFAULT_END = "2021-12-31"

PRIMARY_CLASSES = (
    "CONSISTENT_COMPONENTS_AND_VALUES",
    "DATE_MATCH_COMPONENT_MISSING",
    "VALUE_MULTIPLIER_OR_UNIT_CONFLICT",
    "DATE_DIFFERENCE_EXPLAINED",
    "DUPLICATE_REVISION_OR_CANCEL",
    "OUTSIDE_NORMALIZER_SCOPE",
    "TRUE_SOURCE_EVENT_MISSING",
    "INSUFFICIENT_EVIDENCE",
)

TIME_PRECISIONS = ("EXACT_TIME", "DATE_ONLY", "PARSE_FAILED", "MISSING")


class ReconciliationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuditPaths:
    components: Path
    events: Path
    aggregates: Path
    manifest: Path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join("" if x is None else str(x) for x in parts)
    return prefix + "_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _num(x: object) -> float | None:
    v = pd.to_numeric(pd.Series([x]), errors="coerce").iloc[0]
    return None if pd.isna(v) else float(v)


def _date(x: object) -> pd.Timestamp | pd.NaT:
    v = pd.to_datetime(x, errors="coerce")
    return pd.NaT if pd.isna(v) else pd.Timestamp(v).normalize()


def _positive_sum(row: pd.Series, *cols: str) -> float | None:
    vals = [_num(row.get(c)) for c in cols]
    if all(v is None for v in vals):
        return None
    return float(sum(v or 0.0 for v in vals))


def classify_time_precision(row: pd.Series) -> tuple[str, pd.Timestamp | pd.NaT]:
    """Preserve timing precision instead of promoting a date to midnight."""
    raw_date = row.get("AnnouncementDate")
    raw_time = row.get("AnnouncementTime")
    d = pd.to_datetime(raw_date, errors="coerce")
    date_present = pd.notna(raw_date) and str(raw_date).strip() not in ("", "nan", "None")
    time_present = pd.notna(raw_time) and str(raw_time).strip() not in ("", "nan", "None")

    if not date_present and not time_present:
        return "MISSING", pd.NaT
    if pd.isna(d):
        return "PARSE_FAILED", pd.NaT
    if not time_present:
        return "DATE_ONLY", pd.Timestamp(d).normalize()

    combined = pd.to_datetime(
        f"{pd.Timestamp(d).date().isoformat()} {str(raw_time).strip()}",
        errors="coerce",
    )
    if pd.isna(combined):
        return "PARSE_FAILED", pd.NaT
    return "EXACT_TIME", pd.Timestamp(combined)


def _security_scope(stock_id: str) -> str:
    return "RESEARCH_TICKER_PATTERN" if pd.Series([stock_id]).str.fullmatch(r"[1-9]\d{3}").iloc[0] else "SOURCE_ONLY"


def build_normalized_components(
    dividend: pd.DataFrame,
    *,
    source_revision: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Expand each FinMind source row into cash/stock economic components.

    The FinMind stock conversion is source-specific:
    stock-dividend "yuan per share" / NT$10 par value -> additional-share ratio.
    It is never applied to another source.
    """
    rows: list[dict[str, Any]] = []
    required = {
        "stock_id",
        "CashExDividendTradingDate",
        "StockExDividendTradingDate",
        "CashEarningsDistribution",
        "CashStatutorySurplus",
        "StockEarningsDistribution",
        "StockStatutorySurplus",
        "AnnouncementDate",
    }
    missing = sorted(required - set(dividend.columns))
    if missing:
        raise ReconciliationError(f"dividend source missing columns: {missing}")

    d = dividend.reset_index(drop=True).copy()
    for i, row in d.iterrows():
        sid = str(row.get("stock_id", "")).strip()
        if not sid:
            continue
        source_row_id = _stable_id("finmindrow", source_revision, i)
        precision, known_at = classify_time_precision(row)

        cash = _positive_sum(row, "CashEarningsDistribution", "CashStatutorySurplus")
        cash_date = _date(row.get("CashExDividendTradingDate"))
        if pd.notna(cash_date) and cash is not None and cash > 0 and start <= cash_date <= end:
            rows.append({
                "component_id": _stable_id("component", source_row_id, "CASH", cash_date.date()),
                "source_row_id": source_row_id,
                "source_system": "FinMind TaiwanStockDividend",
                "source_revision": source_revision,
                "source_row_index": int(i),
                "stock_id": sid,
                "security_scope": _security_scope(sid),
                "effective_date": cash_date,
                "component_kind": "CASH",
                "raw_component_value": cash,
                "raw_unit_semantics": "TWD_PER_PRE_EVENT_SHARE",
                "economic_value": cash,
                "economic_value_semantics": "cash_per_pre_event_share",
                "share_multiplier": np.nan,
                "announcement_date_raw": row.get("AnnouncementDate"),
                "announcement_time_raw": row.get("AnnouncementTime"),
                "time_precision": precision,
                "known_at_value": known_at,
                "raw_cash_earnings": _num(row.get("CashEarningsDistribution")),
                "raw_cash_statutory": _num(row.get("CashStatutorySurplus")),
                "raw_stock_earnings": _num(row.get("StockEarningsDistribution")),
                "raw_stock_statutory": _num(row.get("StockStatutorySurplus")),
                "unit_evidence_status": "SOURCE_SPECIFIC_FINMIND_CASH",
            })

        stock_amount = _positive_sum(row, "StockEarningsDistribution", "StockStatutorySurplus")
        stock_date = _date(row.get("StockExDividendTradingDate"))
        if pd.notna(stock_date) and stock_amount is not None and stock_amount > 0 and start <= stock_date <= end:
            ratio = stock_amount / 10.0
            rows.append({
                "component_id": _stable_id("component", source_row_id, "STOCK", stock_date.date()),
                "source_row_id": source_row_id,
                "source_system": "FinMind TaiwanStockDividend",
                "source_revision": source_revision,
                "source_row_index": int(i),
                "stock_id": sid,
                "security_scope": _security_scope(sid),
                "effective_date": stock_date,
                "component_kind": "STOCK",
                "raw_component_value": stock_amount,
                "raw_unit_semantics": "TWD_STOCK_DIVIDEND_PER_PRE_EVENT_SHARE",
                "economic_value": ratio,
                "economic_value_semantics": "additional_shares_per_pre_event_share",
                "share_multiplier": 1.0 + ratio,
                "announcement_date_raw": row.get("AnnouncementDate"),
                "announcement_time_raw": row.get("AnnouncementTime"),
                "time_precision": precision,
                "known_at_value": known_at,
                "raw_cash_earnings": _num(row.get("CashEarningsDistribution")),
                "raw_cash_statutory": _num(row.get("CashStatutorySurplus")),
                "raw_stock_earnings": _num(row.get("StockEarningsDistribution")),
                "raw_stock_statutory": _num(row.get("StockStatutorySurplus")),
                "unit_evidence_status": "SOURCE_SPECIFIC_FINMIND_PAR10_CONVERSION",
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    if out["component_id"].duplicated().any():
        raise ReconciliationError("normalized component_id collision")
    return out.sort_values(["effective_date", "stock_id", "component_kind", "source_row_index"]).reset_index(drop=True)


def build_official_rows(
    official: pd.DataFrame,
    *,
    source_revision: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    required = {"stock_id", "event_date", "event_type", "source_name", "market"}
    missing = sorted(required - set(official.columns))
    if missing:
        raise ReconciliationError(f"official source missing columns: {missing}")

    x = official.copy().reset_index(drop=True)
    x["event_date"] = pd.to_datetime(x["event_date"], errors="coerce").dt.normalize()
    x["stock_id"] = x["stock_id"].astype(str).str.strip()
    x = x[
        x["event_type"].astype(str).eq("ex_right_dividend")
        & x["event_date"].between(start, end)
    ].copy()
    rows: list[dict[str, Any]] = []
    for i, r in x.iterrows():
        source_name = str(r.get("source_name", "")).strip()
        sid = str(r["stock_id"]).strip()
        dt = pd.Timestamp(r["event_date"])
        market = str(r.get("market", "")).strip()
        cash = _num(r.get("cash_per_share"))
        multiplier = _num(r.get("share_multiplier"))
        rights = _num(r.get("rights_ratio"))

        # The frozen TWSE TWT49U importer intentionally stores event/date only.
        # It is not promoted to economic evidence.
        if source_name == "TWSE TWT49U":
            cash_status = "UNAVAILABLE_IN_TWT49U"
            stock_status = "UNAVAILABLE_IN_TWT49U"
        elif source_name == "TPEx exDailyQ":
            cash_status = "SOURCE_FIELD_AVAILABLE" if cash is not None else "SOURCE_FIELD_MISSING"
            # Frozen importer derived multiplier from a positional field /1000.
            # Preserve it, but do not call the unit verified here.
            stock_status = "PARSER_DERIVED_UNIT_UNVERIFIED" if (rights is not None or multiplier is not None) else "SOURCE_FIELD_MISSING"
        else:
            cash_status = "SOURCE_SEMANTICS_UNMAPPED"
            stock_status = "SOURCE_SEMANTICS_UNMAPPED"

        rows.append({
            "official_row_id": _stable_id(
                "officialrow", source_revision, source_name, market, sid,
                dt.date(), r.get("notes", ""), i,
            ),
            "source_revision": source_revision,
            "official_row_index": int(i),
            "source_name": source_name,
            "source_url": r.get("source_url", ""),
            "market": market,
            "stock_id": sid,
            "security_scope": _security_scope(sid),
            "event_date": dt,
            "cash_per_share_raw": cash,
            "share_multiplier_raw": multiplier,
            "rights_ratio_raw": rights,
            "cash_evidence_status": cash_status,
            "stock_evidence_status": stock_status,
            "known_date_raw": r.get("known_date", ""),
            "confidence": r.get("confidence", ""),
            "notes": r.get("notes", ""),
        })
    out = pd.DataFrame(rows)
    if not out.empty and out["official_row_id"].duplicated().any():
        raise ReconciliationError("official_row_id collision")
    return out.sort_values(["event_date", "stock_id", "source_name", "official_row_index"]).reset_index(drop=True)


def _close(a: float | None, b: float | None, atol: float = 1e-9, rtol: float = 1e-7) -> bool:
    if a is None or b is None:
        return False
    return bool(np.isclose(float(a), float(b), atol=atol, rtol=rtol))


def reconcile_events(
    components: pd.DataFrame,
    official_rows: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Bidirectional event reconciliation with event-level conservation."""
    comp_groups = {
        (str(sid), pd.Timestamp(dt)): g.copy()
        for (sid, dt), g in components.groupby(["stock_id", "effective_date"], dropna=False)
    } if not components.empty else {}
    off_groups = {
        (str(sid), pd.Timestamp(dt)): g.copy()
        for (sid, dt), g in official_rows.groupby(["stock_id", "event_date"], dropna=False)
    } if not official_rows.empty else {}

    all_keys = sorted(set(comp_groups) | set(off_groups), key=lambda k: (k[1], k[0]))
    event_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []

    for sid, dt in all_keys:
        cg = comp_groups.get((sid, dt), pd.DataFrame())
        og = off_groups.get((sid, dt), pd.DataFrame())
        norm_cash = cg[cg["component_kind"].eq("CASH")] if len(cg) else pd.DataFrame()
        norm_stock = cg[cg["component_kind"].eq("STOCK")] if len(cg) else pd.DataFrame()
        has_norm = len(cg) > 0
        has_off = len(og) > 0
        duplicate_norm = bool(
            len(norm_cash) > 1 or len(norm_stock) > 1 or
            (len(cg) and cg["component_id"].duplicated().any())
        )
        duplicate_off = bool(len(og) > 1)

        off_twse = og[og["source_name"].eq("TWSE TWT49U")] if has_off else pd.DataFrame()
        off_tpex = og[og["source_name"].eq("TPEx exDailyQ")] if has_off else pd.DataFrame()

        cash_missing = False
        stock_missing = False
        value_conflict = False
        unit_unverified = False
        evidence_insufficient = False

        if has_norm and has_off:
            if len(off_tpex):
                cash_vals = [v for v in off_tpex["cash_per_share_raw"].tolist() if pd.notna(v)]
                n_cash_vals = [v for v in norm_cash["economic_value"].tolist() if pd.notna(v)] if len(norm_cash) else []
                if cash_vals and not n_cash_vals:
                    cash_missing = True
                elif cash_vals and n_cash_vals and not any(_close(float(a), float(b)) for a in cash_vals for b in n_cash_vals):
                    value_conflict = True
                elif n_cash_vals and not cash_vals:
                    cash_missing = True

                rights_vals = [v for v in off_tpex["rights_ratio_raw"].tolist() if pd.notna(v)]
                n_stock_vals = [v for v in norm_stock["economic_value"].tolist() if pd.notna(v)] if len(norm_stock) else []
                if rights_vals or n_stock_vals:
                    # Frozen TPEx parser unit has not yet been proven. Do not
                    # compare multiplier numerically until field semantics are
                    # source-verified.
                    unit_unverified = True
                    if rights_vals and not n_stock_vals:
                        stock_missing = True
                    elif n_stock_vals and not rights_vals:
                        stock_missing = True

            if len(off_twse):
                # TWT49U proves same-date event existence, not components.
                if len(norm_cash) or len(norm_stock):
                    evidence_insufficient = True

        normalized_only = has_norm and not has_off
        official_only = has_off and not has_norm

        if duplicate_norm or duplicate_off:
            primary = "DUPLICATE_REVISION_OR_CANCEL"
        elif has_norm and has_off and (value_conflict or unit_unverified):
            primary = "VALUE_MULTIPLIER_OR_UNIT_CONFLICT"
        elif has_norm and has_off and (cash_missing or stock_missing):
            primary = "DATE_MATCH_COMPONENT_MISSING"
        elif has_norm and has_off and evidence_insufficient:
            primary = "INSUFFICIENT_EVIDENCE"
        elif has_norm and has_off:
            primary = "CONSISTENT_COMPONENTS_AND_VALUES"
        elif normalized_only:
            # Official source coverage is not assumed complete.
            primary = "INSUFFICIENT_EVIDENCE"
        elif official_only:
            # Event exists officially, but absence from FinMind may reflect
            # unsupported security/event economics. Do not call it a true miss
            # without source/type evidence.
            primary = "INSUFFICIENT_EVIDENCE"
        else:
            raise ReconciliationError("unreachable empty event key")

        event_id = _stable_id("event", sid, dt.date())
        scopes = set()
        if len(cg):
            scopes.update(cg["security_scope"].astype(str))
        if len(og):
            scopes.update(og["security_scope"].astype(str))
        scope = "RESEARCH_TICKER_PATTERN" if "RESEARCH_TICKER_PATTERN" in scopes else "SOURCE_ONLY"

        precisions = sorted(set(cg["time_precision"].astype(str))) if len(cg) else []
        event_rows.append({
            "event_id": event_id,
            "stock_id": sid,
            "event_date": dt,
            "security_scope": scope,
            "primary_class": primary,
            "normalized_component_count": int(len(cg)),
            "normalized_cash_count": int(len(norm_cash)),
            "normalized_stock_count": int(len(norm_stock)),
            "official_row_count": int(len(og)),
            "official_sources": ";".join(sorted(set(og["source_name"].astype(str)))) if len(og) else "",
            "normalized_only": bool(normalized_only),
            "official_only": bool(official_only),
            "cash_component_missing_flag": bool(cash_missing),
            "stock_component_missing_flag": bool(stock_missing),
            "value_conflict_flag": bool(value_conflict),
            "unit_unverified_flag": bool(unit_unverified),
            "duplicate_or_multirow_flag": bool(duplicate_norm or duplicate_off),
            "evidence_insufficient_flag": bool(evidence_insufficient or normalized_only or official_only),
            "time_precision_values": ";".join(precisions),
        })

        for _, rr in cg.iterrows():
            mapping_rows.append({
                "event_id": event_id,
                "stock_id": sid,
                "event_date": dt,
                "side": "NORMALIZED",
                "row_or_component_id": rr["component_id"],
                "source_row_id": rr["source_row_id"],
                "source_name": rr["source_system"],
                "component_kind": rr["component_kind"],
                "economic_value": rr["economic_value"],
                "unit_semantics": rr["economic_value_semantics"],
                "time_precision": rr["time_precision"],
            })
        for _, rr in og.iterrows():
            mapping_rows.append({
                "event_id": event_id,
                "stock_id": sid,
                "event_date": dt,
                "side": "OFFICIAL",
                "row_or_component_id": rr["official_row_id"],
                "source_row_id": rr["official_row_id"],
                "source_name": rr["source_name"],
                "component_kind": "EVENT_ROW",
                "economic_value": rr["cash_per_share_raw"],
                "unit_semantics": (
                    "cash_per_share;stock_unit_unverified"
                    if rr["source_name"] == "TPEx exDailyQ"
                    else "event_presence_only"
                ),
                "time_precision": "NOT_AVAILABLE_IN_FROZEN_OFFICIAL_ROW",
            })

    events = pd.DataFrame(event_rows)
    mappings = pd.DataFrame(mapping_rows)
    if not events.empty:
        if not set(events["primary_class"]).issubset(PRIMARY_CLASSES):
            raise ReconciliationError("unexpected primary class")
        if events["event_id"].duplicated().any():
            raise ReconciliationError("event_id collision")
    return events, mappings


def aggregate(events: pd.DataFrame, components: pd.DataFrame, official_rows: pd.DataFrame, *, e1_start: pd.Timestamp) -> dict[str, Any]:
    def subset_stats(frame: pd.DataFrame, scope: str, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, Any]:
        if frame.empty:
            return {"events": 0, "classes": {k: 0 for k in PRIMARY_CLASSES}}
        x = frame[frame["event_date"].between(start, end)].copy()
        if scope == "research":
            x = x[x["security_scope"].eq("RESEARCH_TICKER_PATTERN")]
        vc = x["primary_class"].value_counts().to_dict()
        classes = {k: int(vc.get(k, 0)) for k in PRIMARY_CLASSES}
        if sum(classes.values()) != len(x):
            raise ReconciliationError("event conservation failed")
        return {
            "events": int(len(x)),
            "distinct_tickers": int(x["stock_id"].nunique()),
            "classes": classes,
            "normalized_only": int(x["normalized_only"].sum()),
            "official_only": int(x["official_only"].sum()),
            "cash_component_missing_flags": int(x["cash_component_missing_flag"].sum()),
            "stock_component_missing_flags": int(x["stock_component_missing_flag"].sum()),
            "value_conflict_flags": int(x["value_conflict_flag"].sum()),
            "unit_unverified_flags": int(x["unit_unverified_flag"].sum()),
            "duplicate_or_multirow_flags": int(x["duplicate_or_multirow_flag"].sum()),
            "insufficient_evidence_flags": int(x["evidence_insufficient_flag"].sum()),
        }

    start = min(
        events["event_date"].min() if len(events) else pd.Timestamp(DEFAULT_START),
        pd.Timestamp(DEFAULT_START),
    )
    end = events["event_date"].max() if len(events) else pd.Timestamp(DEFAULT_END)

    precision_counts = (
        components["time_precision"].value_counts().to_dict()
        if len(components) else {}
    )
    for p in TIME_PRECISIONS:
        precision_counts.setdefault(p, 0)

    result = {
        "version": VERSION,
        "counting_units": {
            "event_conservation_unit": "unique_stock_id_plus_economic_effective_date",
            "normalized_unit": "cash_or_stock_component",
            "official_unit": "raw_official_source_row",
        },
        "source_all": {
            "warmup_plus_e1": subset_stats(events, "all", pd.Timestamp(DEFAULT_START), pd.Timestamp(DEFAULT_END)),
            "e1": subset_stats(events, "all", e1_start, pd.Timestamp(DEFAULT_END)),
        },
        "research_ticker_pattern": {
            "warmup_plus_e1": subset_stats(events, "research", pd.Timestamp(DEFAULT_START), pd.Timestamp(DEFAULT_END)),
            "e1": subset_stats(events, "research", e1_start, pd.Timestamp(DEFAULT_END)),
        },
        "normalized_components": {
            "rows": int(len(components)),
            "cash": int((components["component_kind"].eq("CASH")).sum()) if len(components) else 0,
            "stock": int((components["component_kind"].eq("STOCK")).sum()) if len(components) else 0,
            "distinct_tickers": int(components["stock_id"].nunique()) if len(components) else 0,
            "time_precision": {k: int(v) for k, v in precision_counts.items()},
        },
        "official_rows": {
            "rows": int(len(official_rows)),
            "distinct_tickers": int(official_rows["stock_id"].nunique()) if len(official_rows) else 0,
            "by_source": (
                {str(k): int(v) for k, v in official_rows["source_name"].value_counts().to_dict().items()}
                if len(official_rows) else {}
            ),
            "research_ticker_pattern_rows": int(
                official_rows["security_scope"].eq("RESEARCH_TICKER_PATTERN").sum()
            ) if len(official_rows) else 0,
        },
    }
    return result


def write_outputs(
    paths: AuditPaths,
    *,
    components: pd.DataFrame,
    mappings: pd.DataFrame,
    events: pd.DataFrame,
    aggregates: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    for p in (paths.components, paths.events, paths.aggregates, paths.manifest):
        p.parent.mkdir(parents=True, exist_ok=True)

    # One private table contains source-row -> economic-event -> component links.
    comp_map = mappings.merge(
        events[["event_id", "primary_class"]],
        on="event_id",
        how="left",
        validate="many_to_one",
    )
    comp_map.to_csv(paths.components, index=False, encoding="utf-8-sig")
    events.to_csv(paths.events, index=False, encoding="utf-8-sig")
    paths.aggregates.write_text(json.dumps(aggregates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dividend", required=True)
    ap.add_argument("--official", required=True)
    ap.add_argument("--private-output-dir", required=True)
    ap.add_argument("--source-revision", default=DEFAULT_SOURCE_REVISION)
    ap.add_argument("--source-acquired-at", required=True)
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--e1-start", default=DEFAULT_E1_START)
    ap.add_argument("--end", default=DEFAULT_END)
    args = ap.parse_args()

    start = pd.Timestamp(args.start)
    e1_start = pd.Timestamp(args.e1_start)
    end = pd.Timestamp(args.end)
    if (start, e1_start, end) != (
        pd.Timestamp(DEFAULT_START),
        pd.Timestamp(DEFAULT_E1_START),
        pd.Timestamp(DEFAULT_END),
    ):
        raise ReconciliationError("this version is frozen to 2015 warmup + full E1")

    dividend_path = Path(args.dividend)
    official_path = Path(args.official)
    out_dir = Path(args.private_output_dir)
    dividend = pd.read_parquet(dividend_path)
    official = pd.read_csv(official_path, dtype=str).fillna("")

    components = build_normalized_components(
        dividend,
        source_revision=args.source_revision,
        start=start,
        end=end,
    )
    official_rows = build_official_rows(
        official,
        source_revision=args.source_revision,
        start=start,
        end=end,
    )
    events, mappings = reconcile_events(components, official_rows)
    aggregates = aggregate(events, components, official_rows, e1_start=e1_start)

    manifest = {
        "version": VERSION,
        "source_revision": args.source_revision,
        "source_acquired_at": args.source_acquired_at,
        "period": {"start": args.start, "e1_start": args.e1_start, "end": args.end},
        "inputs": {
            "dividend": {"sha256": _sha256_file(dividend_path), "rows": int(len(dividend))},
            "official": {"sha256": _sha256_file(official_path), "rows": int(len(official))},
        },
        "private_outputs": {
            "component_mapping": "source_event_component_mapping.csv",
            "event_reconciliation": "event_reconciliation.csv",
            "aggregates": "aggregates.json",
        },
        "formal_e1_feature_artifact_built": False,
        "strategy_effects_computed": False,
        "canonical_ca_engine_modified": False,
        "notes": [
            "TWT49U is event/date evidence only in the frozen source.",
            "TPEx exDailyQ cash field is retained; frozen stock multiplier remains unit-unverified.",
            "Normalized-only or official-only rows are not automatically called true missing events.",
            "Date-only announcement evidence is never promoted to exact midnight precision.",
        ],
    }

    paths = AuditPaths(
        components=out_dir / "source_event_component_mapping.csv",
        events=out_dir / "event_reconciliation.csv",
        aggregates=out_dir / "aggregates.json",
        manifest=out_dir / "manifest.json",
    )
    write_outputs(
        paths,
        components=components,
        mappings=mappings,
        events=events,
        aggregates=aggregates,
        manifest=manifest,
    )

    # stdout is aggregate only; never print row-level private data.
    print(json.dumps(aggregates, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
