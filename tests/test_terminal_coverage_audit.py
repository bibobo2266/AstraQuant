from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "source_terminal_coverage_audit.py"
    spec = importlib.util.spec_from_file_location("terminal_coverage_audit_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_modeled_terminal_map_contains_known_lifecycle_types():
    module = _load_module()
    modeled = module.modeled_terminal_map()
    assert modeled["4141"]["event_type"] == "CASH_MERGER_EXTINGUISHMENT"
    assert modeled["5305"]["event_type"] == "CASH_MERGER_EXTINGUISHMENT"
    assert modeled["6286"]["event_type"] == "CASH_MERGER_EXTINGUISHMENT"
    assert modeled["6251"]["event_type"] == "SUCCESSOR_SHARE_CONVERSION"
    assert modeled["2823"]["event_type"] == "MULTI_LEG_SHARE_CONVERSION_PLUS_CASH"


def test_unmodeled_suspension_is_not_mislabeled_as_modeled():
    module = _load_module()
    suspensions = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-05-02")],
            "stock_id": ["1234"],
            "suspension_time": ["09:00:00"],
            "resumption_date": [pd.NaT],
            "resumption_time": [None],
        }
    )
    ledger = pd.DataFrame(
        columns=[
            "stock_id",
            "event_date",
            "event_type",
            "source_name",
        ]
    )
    missing, availability, detail = module.classify_missing_event(
        ticker="1234",
        last_raw_date=pd.Timestamp("2024-05-01"),
        suspensions=suspensions,
        ledger=ledger,
    )
    assert missing == "TERMINAL_SUSPENSION_LIFECYCLE"
    assert "suspended" in availability.lower()
    assert "2024-05-02" in detail


def test_unmodeled_capital_reduction_is_explicit_blocker():
    module = _load_module()
    suspensions = pd.DataFrame(
        columns=["date", "stock_id", "resumption_date"]
    )
    ledger = pd.DataFrame(
        {
            "stock_id": ["2345"],
            "event_date": [pd.Timestamp("2023-08-15")],
            "event_type": ["capital_reduction"],
            "source_name": ["TWSE"],
        }
    )
    missing, availability, detail = module.classify_missing_event(
        ticker="2345",
        last_raw_date=pd.Timestamp("2023-08-10"),
        suspensions=suspensions,
        ledger=ledger,
    )
    assert missing == "CAPITAL_REDUCTION_TERMINAL_OR_RESUMPTION_SEMANTICS"
    assert "ledger" in availability.lower()
    assert "capital_reduction" in detail


def test_terminal_table_keeps_unmodeled_rows_instead_of_excluding():
    module = _load_module()
    raw_last = pd.DataFrame(
        {
            "stock_id": ["1111", "2222", "3333"],
            "last_raw_date": [
                pd.Timestamp("2022-04-26"),
                pd.Timestamp("2024-05-01"),
                pd.Timestamp("2026-07-07"),
            ],
        }
    )
    modeled = {
        "1111": {
            "event_type": "CASH_MERGER_EXTINGUISHMENT",
            "terminal_stale_from": pd.Timestamp("2022-04-27"),
            "effective_at": pd.Timestamp("2022-05-03"),
            "source": "fixture",
            "source_url": "fixture",
        }
    }
    suspensions = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-05-02")],
            "stock_id": ["2222"],
            "resumption_date": [pd.NaT],
        }
    )
    ledger = pd.DataFrame(
        columns=["stock_id", "event_date", "event_type", "source_name"]
    )
    coverage = pd.DataFrame(
        {
            "stock_id": ["1111", "2222", "3333"],
            "end_date": [
                pd.Timestamp("2022-04-26"),
                pd.Timestamp("2024-05-01"),
                pd.Timestamp("2026-07-07"),
            ],
        }
    )
    audit = module.build_audit_table(
        common_support_tickers={"1111", "2222", "3333"},
        raw_last=raw_last,
        modeled=modeled,
        suspensions=suspensions,
        ledger=ledger,
        coverage=coverage,
    )
    assert set(audit["ticker"]) == {"1111", "2222"}
    status = dict(zip(audit["ticker"], audit["status"]))
    assert status == {"1111": "MODELED", "2222": "UNMODELED"}
