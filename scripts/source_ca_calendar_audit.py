#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from astraquant.portfolio.calendar import CalendarMappingError, TradingCalendar

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_CA_CALENDAR_AUDIT.md"))


def load_sessions() -> list[pd.Timestamp]:
    sessions: list[pd.Timestamp] = []
    for path in sorted((SOURCE_ROOT / "raw").glob("prices_raw_*.parquet")):
        d = pd.read_parquet(path, columns=["date"])
        s = pd.to_datetime(d["date"], errors="coerce").dt.normalize().dropna().drop_duplicates()
        sessions.extend(pd.Timestamp(x) for x in s.tolist())
    if not sessions:
        raise SystemExit("BLOCKED: no RAW session dates found")
    return sorted(set(sessions))


def main() -> None:
    raw_sessions = load_sessions()
    calendar = TradingCalendar([x.date() for x in raw_sessions])
    first = pd.Timestamp(calendar.sessions[0])
    last = pd.Timestamp(calendar.sessions[-1])

    ledger = pd.read_parquet(
        SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet",
        columns=["stock_id", "event_date", "event_type", "source_name"],
    )
    ledger["stock_id"] = ledger["stock_id"].astype(str)
    ledger["event_date"] = pd.to_datetime(ledger["event_date"], errors="coerce").dt.normalize()
    ledger["event_type"] = ledger["event_type"].fillna("UNKNOWN").astype(str)

    null_dates = int(ledger["event_date"].isna().sum())
    before = ledger[ledger["event_date"].lt(first)]
    after = ledger[ledger["event_date"].gt(last)]
    in_horizon = ledger[ledger["event_date"].between(first, last, inclusive="both")].copy()

    session_set = {pd.Timestamp(x) for x in calendar.sessions}
    in_horizon["on_session"] = in_horizon["event_date"].isin(session_set)

    mapped_rows = []
    failures = []
    for row in in_horizon.itertuples(index=False):
        event_day = pd.Timestamp(row.event_date)
        try:
            mapped = pd.Timestamp(calendar.map_effective_date(event_day.date()))
        except CalendarMappingError as exc:
            failures.append((row.stock_id, event_day, row.event_type, str(exc)))
            continue
        mapped_rows.append(
            {
                "stock_id": str(row.stock_id),
                "event_date": event_day,
                "mapped_session": mapped,
                "event_type": str(row.event_type),
                "source_name": str(row.source_name),
                "gap_days": int((mapped - event_day).days),
                "on_session": bool(event_day == mapped),
            }
        )

    mapped = pd.DataFrame(mapped_rows)
    non_session = mapped[~mapped["on_session"]].copy() if not mapped.empty else mapped
    backwards = int((mapped["mapped_session"] < mapped["event_date"]).sum()) if not mapped.empty else 0
    zero_or_negative_gap_non_session = int((non_session["gap_days"] <= 0).sum()) if not non_session.empty else 0

    gap_counts = (
        non_session["gap_days"].value_counts().sort_index().to_dict()
        if not non_session.empty
        else {}
    )
    type_counts = (
        non_session["event_type"].value_counts().sort_values(ascending=False).to_dict()
        if not non_session.empty
        else {}
    )

    hard_fail = bool(failures or backwards or zero_or_negative_gap_non_session or null_dates)
    status = "FAIL" if hard_fail else "PASS_WITH_HORIZON_LIMITS"

    lines = [
        "# Source Corporate-Action Calendar Audit",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: verify how canonical corporate-action effective dates map onto the RAW trading-session calendar without ever moving an economic event backward.",
        "",
        "## RAW calendar",
        "",
        f"- first RAW session: {calendar.sessions[0]}",
        f"- last RAW session: {calendar.sessions[-1]}",
        f"- unique RAW sessions: {len(calendar.sessions):,}",
        "",
        "## Corporate-action dates",
        "",
        f"- ledger rows: {len(ledger):,}",
        f"- null event_date: {null_dates:,}",
        f"- rows before RAW calendar horizon: {len(before):,}",
        f"- rows after RAW calendar horizon: {len(after):,}",
        f"- rows inside RAW calendar horizon: {len(in_horizon):,}",
        f"- on-session event dates: {int(in_horizon['on_session'].sum()):,}",
        f"- non-session event dates: {int((~in_horizon['on_session']).sum()):,}",
        f"- mapping failures inside horizon: {len(failures):,}",
        f"- backward mappings: {backwards:,}",
        "",
        "## Non-session forward-mapping gaps",
        "",
        "| Calendar-day gap to first trading session | Events |",
        "|---:|---:|",
    ]
    for gap, count in gap_counts.items():
        lines.append(f"| {int(gap)} | {int(count):,} |")

    lines += [
        "",
        "## Non-session event types",
        "",
        "| Event type | Events |",
        "|---|---:|",
    ]
    for event_type, count in type_counts.items():
        lines.append(f"| {event_type} | {int(count):,} |")

    lines += [
        "",
        "## Canonical policy",
        "",
        "- If economic effective date is a trading session: apply before that session's trading.",
        "- If economic effective date is not a trading session: apply before the first trading session after the effective date.",
        "- Never map an event to a prior trading session.",
        "- If no later session exists inside the configured simulation calendar: hard-fail / extend the calendar; do not guess.",
        "- known_date, record date, and payment date remain separate concepts and are not substituted for the economic effective date.",
        "",
        "## Horizon treatment",
        "",
        "Rows before or after the available RAW calendar are reported separately and are not remapped into the observed horizon.",
        "",
        "## Result",
        "",
        "The calendar gate passes only if every in-horizon event has a deterministic same-session/forward mapping and no event maps backward.",
    ]

    if failures:
        lines += ["", "### Mapping failures", ""]
        for stock_id, event_day, event_type, message in failures[:25]:
            lines.append(f"- {stock_id} {event_day.date()} {event_type}: {message}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if hard_fail:
        raise SystemExit("FAIL: corporate-action calendar audit failed")


if __name__ == "__main__":
    main()
