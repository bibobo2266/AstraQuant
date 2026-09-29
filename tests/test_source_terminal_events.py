from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "source_strategy_integration_smoke.py"
    spec = importlib.util.spec_from_file_location(
        "source_strategy_integration_smoke_test",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_6286_terminal_cash_conversion_fact_is_data_driven():
    module = _load_script_module()
    event = module.load_confirmed_terminal_overrides()["6286"]

    assert event.last_trading_date.isoformat() == "2016-04-20"
    assert event.suspension_from.isoformat() == "2016-04-21"
    assert event.effective_date.isoformat() == "2016-04-29"
    assert event.payment_date.isoformat() == "2016-05-05"
    assert event.cash_per_share == 195.0
    assert event.confidence == "CONFIRMED"
