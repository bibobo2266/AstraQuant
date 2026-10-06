"""Synthetic contract checks only; optional pinned private producer, no data reads."""
from datetime import date, datetime, timedelta
import hashlib
import importlib.util
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from astraquant.portfolio.models import Fill
from astraquant.research.baseline_60d_exit_state import Baseline60DExitState, BaselineBarInput
from astraquant.research.causal_raw_v2 import build_causal_raw_v2_features
from astraquant.research.exploration_data_contract import (
    FEATURES, LIMITED, HoldingDataAudit, advance_holding_data, map_source_row,
)
from astraquant.research.feature_cache import FeatureCache
from astraquant.research.signal_engine import SignalContext
from astraquant.research.strategy_config import ComponentSpec
from astraquant.research.technical_components import n_session_high


def bars(n=63):
    days = pd.bdate_range("2020-01-02", periods=n)
    return pd.DataFrame(dict(date=days, stock_id="SYNTH", open=100., max=101.,
                             min=99., close=100., observed_trade=True, valid_ohlc=True))


def state_results(frame):
    state = Baseline60DExitState()
    state.register_entry(Fill(fill_id="synthetic", order_id="synthetic", ticker="SYNTH",
                              side="buy", quantity=1, price=100., fees=0.,
                              filled_at=datetime(2020, 1, 2)), session_index=0)
    results = []
    for index, row in frame.iterrows():
        results.append(state.observe_bar(BaselineBarInput(
            ticker="SYNTH", session_date=row.date.date(), session_index=index,
            open=row.open, high=row["max"], low=row["min"], close=row.close,
            observed_trade=bool(row.observed_trade), valid_ohlc=bool(row.valid_ohlc))))
    return results


def test_formal_atr_14_15_same_nonconstant_bars():
    frame = bars(15)
    frame.loc[0, ["max", "min"]] = [103., 97.]
    results = state_results(frame)
    assert results[12].atr_value is None
    assert results[13].atr_value == pytest.approx((6 + 13 * 2) / 14)
    assert results[14].atr_value == pytest.approx(2.)
    assert results[13].atr_window.observation_count == 14


def test_formal_atr_skips_suspension_but_audits_common_session_gap():
    frame = bars(16)
    frame.loc[7, "observed_trade"] = False
    results = state_results(frame)
    assert not results[7].observation_accepted
    assert results[13].atr_value is None
    assert results[14].atr_value == 2.
    assert results[14].atr_window.session_span == 15
    assert results[14].atr_window.skipped_sessions == 1


def n60(frame):
    panel = frame.rename(columns={"close": "raw_close"}).assign(
        Trading_money=30_000_000., decision_cutoff_at=frame.date + pd.Timedelta(days=1))
    events = pd.DataFrame(columns=["stock_id", "effective_date", "event_kind", "known_at",
                                   "cash_per_share", "share_multiplier"])
    return build_causal_raw_v2_features(panel, events)


def test_n60_first_cross_boundaries_and_formal_trigger():
    frame = bars()
    frame.loc[61, "close"] = 101.
    frame.loc[62, "close"] = 102.
    out = n60(frame)
    assert pd.isna(out.loc[60, "n60_first_cross"])
    assert bool(out.loc[61, "n60_first_cross"])
    assert not bool(out.loc[62, "n60_first_cross"])  # already above yesterday
    trigger = n_session_high(panel=frame, spec=ComponentSpec(type="N_SESSION_HIGH", params={"lookback": 60}),
                             cache=FeatureCache(), context=SignalContext(source_revision="synthetic"))
    assert trigger.tolist() == out.n60_first_cross.fillna(False).tolist()
    frame.loc[61, "close"] = 100.
    assert not bool(n60(frame).loc[61, "n60_first_cross"])  # equality is not crossing


def test_n60_missing_common_row_is_not_compressed_or_false():
    frame = bars()
    frame.loc[61, "close"] = 101.
    frame.loc[30, "close"] = np.nan
    frame.loc[30, ["observed_trade", "valid_ohlc"]] = False
    out = n60(frame)
    assert out.loc[61, "n60_state"] == "INPUT_MISSING"
    assert pd.isna(out.loc[61, "n60_first_cross"])


@pytest.fixture
def producer():
    path = os.environ.get("AQ_COVERAGE_PRODUCER")
    if not path:
        pytest.skip("optional pinned private producer; do not fetch or run full coverage in CI")
    content = Path(path).read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
    assert blob == "fa6b2729e36351eb0cadc3097547fc1a66d0e33f"
    spec = importlib.util.spec_from_file_location("pinned_coverage_producer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pinned_producer_atr_difference_and_baseline_mask(producer):
    frame = bars(15)
    frame.loc[0, ["max", "min"]] = [103., 97.]
    actual = producer.add_c_states(frame.copy())
    formal = state_results(frame)
    assert actual.loc[13, "atr14_c_reason"] == "WARMUP_INSUFFICIENT_15_VALID_BARS_FOR_14_TR"
    assert formal[13].atr_value is not None
    assert actual.loc[14, "atr14_c_reason"] == ""
    assert formal[14].atr_value == 2.
    # Correcting only ATR 15->14 cannot change the all-four intersection here.
    assert actual.loc[13, "low20_c_reason"] != ""


def test_pinned_producer_geometry_and_invalid_current_are_not_formal(producer):
    frame = bars(22)
    frame.loc[21, "max"] = 90.  # positive but below open/close/low
    actual = producer.add_c_states(frame.copy())
    formal = state_results(frame)
    assert actual.loc[21, "valid_observed_bar"]
    assert actual.loc[21, "atr14_c_reason"] == ""
    assert not formal[21].observation_accepted
    assert formal[21].observation_reason == "INVALID_OHLC_GEOMETRY"
    frame.loc[21, "max"] = np.nan
    actual = producer.add_c_states(frame.copy())
    assert not actual.loc[21, "valid_observed_bar"]
    assert actual.loc[21, "atr14_c_reason"] == ""  # ordinal alone is insufficient


def test_pinned_producer_n60_requires_complete_calendar(producer):
    frame = bars()
    actual = producer.add_c_states(frame.copy())
    assert actual.loc[60, "n60_c_reason"] != ""
    assert actual.loc[61, "n60_c_reason"] == ""
    frame.loc[30, "close"] = np.nan
    frame.loc[30, ["observed_trade", "valid_ohlc"]] = False
    assert producer.add_c_states(frame.copy()).loc[61, "n60_c_reason"] != ""
    # Both rolling implementations rely on caller calendar completeness.
    hole = frame.drop(index=30).reset_index(drop=True)
    assert producer.add_c_states(hole).loc[61, "n60_c_reason"] == ""
    assert len(hole) == 62 and hole.date.iloc[-1] == frame.date.iloc[-1]


def test_pinned_producer_event_output_widths_keep_calendar_and_valid_bar_axes(producer):
    frame = bars(200)
    frame["all_liquid"] = True
    frame["panel_index"] = range(len(frame))
    frame.loc[65, "observed_trade"] = False
    frame = producer.add_c_states(frame)
    event = pd.DataFrame([dict(stock_id="SYNTH", event_date=frame.loc[62, "date"],
                               economic_event_id="SYNTHETIC_EVENT", primary_class="INSUFFICIENT_EVIDENCE")])
    exposure = producer.build_b_exposures(frame, event)
    expected = {"MA120": (119, 180), "N60": (61, 122), "ATR14": (14, 76), "LOW20": (20, 82)}
    for feature, (count, last) in expected.items():
        indices = exposure.loc[exposure.feature.eq(feature), "panel_index"].tolist()
        assert len(indices) == count and indices[0] == 62 and indices[-1] == last
        assert (65 in indices) == (feature in {"MA120", "N60"})


def source_row(b=False, c=False):
    row = dict(date="2020-01-02", stock_id="SYNTH", limited_exploration_label="NOT_ELIGIBLE" if b or c else LIMITED,
               baseline_issue_a_any=True, baseline_issue_b_any=b, baseline_issue_c_any=c,
               baseline_evidence_state="KNOWN_AFFECTED" if c else "INDETERMINATE",
               raw_version_evidence_reason="A_RAW_OHLC_TRADING_MONEY_HISTORICAL_VERSION_IDENTITY_UNKNOWN",
               baseline_all_four_numeric_computable=not c,
               baseline_limited_exploration_eligible=not b and not c)
    for feature in FEATURES:
        row.update({f"{feature}_{suffix}": value for suffix, value in dict(
            issue_a=True, issue_b=b, issue_c=c, c_reason="MISSING" if c else "",
            b_known=False, b_event_count=int(b), b_event_ids="SYNTHETIC_EVENT" if b else "",
            b_reasons="ECONOMIC_UNRESOLVED" if b else "", evidence_state=row["baseline_evidence_state"],
            dominant_problem_class="C" if c else "B" if b else "A",
            numeric_computable=not c, limited_exploration_eligible=not b and not c).items()})
    return row


@pytest.mark.parametrize("b,c,status", [(False, False, LIMITED), (True, False, "BLOCKED"),
                                        (False, True, "UNAVAILABLE"), (True, True, "UNAVAILABLE")])
def test_schema_is_lossless_and_never_promotes_a(b, c, status):
    row = source_row(b, c)
    mapped = map_source_row(row)
    assert mapped["eligibility_status"] == status
    assert all(mapped[key] == value for key, value in row.items())
    assert mapped["baseline_issue_a_any"] is True
    assert len([mapped]) == len([row])  # map every original row, not only eligible rows


@pytest.mark.parametrize("key,value", [("limited_exploration_label", "VERIFIED"),
                                       ("baseline_issue_a_any", False),
                                       ("baseline_issue_b_any", "false"),
                                       ("baseline_evidence_state", "SUPPORTED_UNAFFECTED")])
def test_schema_rejects_evidence_erasure(key, value):
    row = source_row()
    row[key] = value
    with pytest.raises(ValueError):
        map_source_row(row)


def step(previous, day, **kwargs):
    return advance_holding_data(previous, session=day, expected_next_session=day,
                                in_all_liquid=False, reason="synthetic reason", **kwargs)


@pytest.mark.parametrize("problem", ["MISSING", "ECONOMIC_UNRESOLVED", "NOT_COMPUTABLE"])
def test_holding_problem_is_chronological_sticky_and_does_not_erase_entry(problem):
    entry = date(2020, 1, 2)
    initial = HoldingDataAudit(entry, entry, entry)
    departed = step(initial, entry + timedelta(days=1), holding_evidence="RELIABLE")
    assert departed.status == "OPEN"  # leaving all_liquid is not an exit
    censored = step(departed, entry + timedelta(days=4), holding_evidence=problem,
                    canonical_exit_observed=True, period_end=True)
    assert initial.status == "OPEN" and departed.status == "OPEN"
    assert censored.entry_session == entry and censored.status == "DATA_CENSORED"
    assert censored.last_reliable_session == departed.last_reliable_session
    assert censored.first_problem_session == entry + timedelta(days=4)
    assert censored.portfolio_continuation_blocked
    assert step(censored, entry + timedelta(days=5), holding_evidence="RELIABLE") == censored


def test_normal_exit_period_end_and_calendar_error_are_distinct():
    day = date(2020, 1, 2)
    initial = HoldingDataAudit(day, day, day)
    assert step(initial, date(2020, 1, 3), holding_evidence="RELIABLE", canonical_exit_observed=True).status == "CLOSED"
    assert step(initial, date(2020, 1, 3), holding_evidence="RELIABLE", period_end=True).status == "OPEN_AT_END"
    with pytest.raises(ValueError, match="common session"):
        advance_holding_data(initial, session=date(2020, 1, 6), expected_next_session=date(2020, 1, 3),
                             in_all_liquid=True, holding_evidence="RELIABLE", reason="")
