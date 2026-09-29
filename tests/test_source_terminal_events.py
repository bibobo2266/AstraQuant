from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "source_strategy_integration_smoke.py"
    spec = importlib.util.spec_from_file_location("source_strategy_integration_smoke_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_6286_terminal_cash_conversion_fact_is_curated():
    module = _load_script_module()
    events = {
        str(item["ticker"]): item
        for item in module.CURATED_TERMINAL_EVENTS
    }
    event = events["6286"]

    assert event["known_at"].isoformat() == "2016-04-06T14:40:00"
    assert event["terminal_stale_from"].isoformat() == "2016-04-21"
    assert event["effective_at"].isoformat() == "2016-04-29T00:00:00"
    assert event["payment_at"].isoformat() == "2016-05-05T00:00:00"
    assert event["cash_per_share"] == 195.0
