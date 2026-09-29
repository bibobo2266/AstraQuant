from __future__ import annotations

from pathlib import Path

from astraquant.research.terminal_events import (
    confirmed_terminal_events,
    load_terminal_event_records,
)


HEADER = (
    "ticker,last_trading_date,event_type,suspension_from,effective_date,"
    "cash_per_share,payment_date,successor_ticker,share_ratio,confidence,"
    "source_url,source_quote\n"
)


def test_only_confirmed_rows_override_fallback(tmp_path: Path):
    path = tmp_path / "terminal.csv"
    path.write_text(
        HEADER
        + "1111,2024-01-02,CASH_MERGER_EXTINGUISHMENT,2024-01-03,"
          "2024-01-10,50,2024-01-15,,,CONFIRMED,u,q\n"
        + "2222,2024-02-02,CASH_MERGER_EXTINGUISHMENT,2024-02-03,"
          "2024-02-10,60,2024-02-15,,,PARTIAL,u,q\n"
        + "3333,2024-03-02,CASH_MERGER_EXTINGUISHMENT,2024-03-03,"
          "2024-03-10,70,2024-03-15,,,NOT_FOUND,u,q\n",
        encoding="utf-8",
    )
    records = load_terminal_event_records(path)
    overrides = confirmed_terminal_events(records)
    assert set(overrides) == {"1111"}


def test_confirmed_successor_requires_ratio(tmp_path: Path):
    path = tmp_path / "terminal.csv"
    path.write_text(
        HEADER
        + "1111,2024-01-02,SUCCESSOR_SHARE_CONVERSION,2024-01-03,"
          "2024-01-10,,,2222,,CONFIRMED,u,q\n",
        encoding="utf-8",
    )
    try:
        load_terminal_event_records(path)
    except ValueError as exc:
        assert "share_ratio" in str(exc)
    else:
        raise AssertionError("expected ValueError")
