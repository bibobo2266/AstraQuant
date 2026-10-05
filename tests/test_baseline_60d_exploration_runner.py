from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from astraquant.research.baseline_60d_exploration import (
    BaselineExplorationError,
    FROZEN_METHOD,
    build_synthetic_fixture,
    load_eligibility_table,
    load_frozen_method_config,
    qualify_candidates,
    run_synthetic_exploration,
)
from astraquant.research.feature_panel_integration import sha256_file


METHOD_CONFIG = "configs/research/baseline_60d_breakout_v1/exploration.yaml"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _normalized_json(value):
    if isinstance(value, dict):
        return {key: _normalized_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalized_json(item) for item in value]
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return round(value, 12)
    return value


def test_frozen_method_config_matches_single_approved_baseline():
    loaded = load_frozen_method_config(_repo_root() / METHOD_CONFIG)
    assert loaded == FROZEN_METHOD
    assert loaded["entry"]["lookback"] == 60
    assert loaded["exit"]["atr_period"] == 14
    assert loaded["exit"]["low_window"] == 20
    assert loaded["costs"] == {
        "buy_fee_bps": 14.25,
        "sell_fee_bps_including_tax": 44.25,
        "adverse_slippage_bps_each_side": 10.0,
        "settlement_lag_sessions": 2,
    }
    assert loaded["method_contract"]["cross_stock_capital_competition"] is False
    assert loaded["formal_research_status"] == "BLOCKED"
    assert "capital_constrained_max_positions" in loaded["unfrozen_for_real_e1"]


def test_synthetic_exploration_full_entry_report_and_costs(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    output = tmp_path / "output"

    artifacts = run_synthetic_exploration(
        repo_root=_repo_root(),
        fixture_root=fixture,
        output_dir=output,
        method_config_path=METHOD_CONFIG,
    )

    report = artifacts.report
    assert report["mode"] == "SYNTHETIC_FIXTURE"
    assert report["formal_research_status"] == "BLOCKED"

    # Original row denominator is preserved. No UNKNOWN/BLOCKED row is
    # zero-filled or silently removed from the population audit.
    assert report["population"]["row_denominator"] == 16 * 64
    assert report["population"]["unique_tickers"] == 16
    assert report["population"]["status_counts"] == {
        "ELIGIBLE": 15 * 64,
        "BLOCKED": 64,
    }
    assert report["population"]["reason_counts"]["ECONOMIC_CONTENT_UNRESOLVED"] == 64

    # Four frozen-method candidates: three executable, one explicit economic
    # content block. The blocked candidate never becomes a fill.
    assert report["candidate_funnel"]["signal_candidates"] == 4
    assert report["candidate_funnel"]["eligible_candidates"] == 3
    assert report["candidate_funnel"]["status_counts"] == {
        "ELIGIBLE": 3,
        "BLOCKED": 1,
    }
    assert (
        report["candidate_funnel"]["reason_counts"][
            "ECONOMIC_CONTENT_UNRESOLVED"
        ]
        == 1
    )
    blocked = artifacts.candidate_funnel[
        artifacts.candidate_funnel["stock_id"].eq("2317")
    ].iloc[0]
    assert blocked["eligibility_status"] == "BLOCKED"

    # Candidate cohort is independent-by-ticker and remains separate from
    # capacity-constrained portfolio results.
    candidate_metrics = report["candidate_cohort"]["metrics"]
    capital_metrics = report["capital_constrained"]["metrics"]
    assert candidate_metrics["n_closed"] == 2
    assert candidate_metrics["n_open"] == 1
    assert candidate_metrics["win_rate"] == pytest.approx(0.5)
    assert capital_metrics["n_closed"] == 2
    assert capital_metrics["n_open"] == 0
    assert report["capital_constrained"]["entries_executed"] == 2
    assert report["capital_constrained"]["capacity_rejections"] == 1

    assert set(artifacts.candidate_trades["stock_id"]) == {"2330", "2454"}
    assert "3008" in set(
        artifacts.open_positions.loc[
            artifacts.open_positions["run_label"].eq("CANDIDATE_COHORT"),
            "stock_id",
        ]
    )
    assert "2317" not in set(artifacts.candidate_trades["stock_id"])
    assert "2317" not in set(artifacts.open_positions["stock_id"])

    # Fee+tax and slippage are applied exactly once by the canonical fill
    # factory. Compare report return against the one-pass fill economics.
    by_ticker = artifacts.candidate_trades.set_index("stock_id")
    entry_fill = 100.0 * 1.001
    entry_cost = entry_fill * (1.0 + 14.25 / 10_000.0)
    expected_2330 = (
        105.0 * 0.999 * (1.0 - 44.25 / 10_000.0) - entry_cost
    ) / entry_cost
    expected_2454 = (
        95.0 * 0.999 * (1.0 - 44.25 / 10_000.0) - entry_cost
    ) / entry_cost
    assert by_ticker.loc["2330", "net_return"] == pytest.approx(expected_2330)
    assert by_ticker.loc["2454", "net_return"] == pytest.approx(expected_2454)

    # MFE/MAE exists only as a diagnostic surface.
    assert report["mfe_mae"]["role"] == "DIAGNOSTIC_ONLY"
    assert report["mfe_mae"]["status_counts"] == {"OK": 4}
    assert artifacts.mfe_mae["mfe"].notna().all()
    assert artifacts.mfe_mae["mae"].notna().all()

    expected_files = {
        "report.json",
        "candidate_trades.csv",
        "capital_constrained_trades.csv",
        "open_positions.csv",
        "eligibility_audit.csv",
        "candidate_funnel.csv",
        "mfe_mae_diagnostics.csv",
        "data_censored_positions.csv",
    }
    assert expected_files == {path.name for path in output.iterdir()}
    stored = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert stored["candidate_funnel"] == report["candidate_funnel"]
    expected = json.loads(
        (_repo_root() / "out/baseline_60d_exploration_synthetic_report.json")
        .read_text(encoding="utf-8")
    )
    assert _normalized_json(stored) == _normalized_json(expected)


def test_missing_candidate_eligibility_is_explicit_unknown_not_zero(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    table_path = fixture / "eligibility.csv"
    manifest_path = fixture / "eligibility_manifest.json"
    table = pd.read_csv(table_path, dtype={"stock_id": str})
    signal_date = sorted(pd.to_datetime(table["date"]).dt.normalize().unique())[61]
    keep = ~(
        table["stock_id"].eq("3008")
        & pd.to_datetime(table["date"]).dt.normalize().eq(signal_date)
    )
    table = table.loc[keep].copy()
    table.to_csv(table_path, index=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["row_count"] = len(table)
    manifest["table_sha256"] = sha256_file(table_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    eligibility = load_eligibility_table(
        table_path=table_path,
        manifest_path=manifest_path,
    )
    candidates = pd.DataFrame(
        [
            {
                "signal_date": signal_date,
                "stock_id": "3008",
            }
        ]
    )
    out = qualify_candidates(candidates, eligibility)
    assert out.iloc[0]["eligibility_status"] == "UNKNOWN"
    assert out.iloc[0]["reason_code"] == "MISSING_ELIGIBILITY_ROW"
    assert len(eligibility.frame) == 16 * 64 - 1


def test_eligibility_checksum_tamper_fails_closed(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    table_path = fixture / "eligibility.csv"
    table = pd.read_csv(table_path, dtype={"stock_id": str})
    table.loc[0, "reason_code"] = "TAMPERED"
    table.to_csv(table_path, index=False)

    with pytest.raises(BaselineExplorationError, match="checksum mismatch"):
        load_eligibility_table(
            table_path=table_path,
            manifest_path=fixture / "eligibility_manifest.json",
        )


def test_execution_source_checksum_tamper_fails_before_simulation(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    raw_path = fixture / "source/raw/prices_raw_2020.parquet"
    raw = pd.read_parquet(raw_path)
    raw.loc[0, "open"] = 999.0
    raw.to_parquet(raw_path, index=False)

    with pytest.raises(BaselineExplorationError, match="source file checksum mismatch"):
        run_synthetic_exploration(
            repo_root=_repo_root(),
            fixture_root=fixture,
            output_dir=tmp_path / "output",
            method_config_path=METHOD_CONFIG,
        )


@pytest.mark.parametrize("manifest_name", ["source_manifest.json", "eligibility_manifest.json"])
def test_synthetic_runner_rejects_non_fixture_scope(tmp_path, manifest_name):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    path = fixture / manifest_name
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["scope"] = "SOURCE_EVIDENCE"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BaselineExplorationError, match="scope mismatch"):
        run_synthetic_exploration(
            repo_root=_repo_root(),
            fixture_root=fixture,
            output_dir=tmp_path / "output",
            method_config_path=METHOD_CONFIG,
        )


def _save_eligibility(fixture, table, **metadata):
    path = fixture / "eligibility.csv"
    table.to_csv(path, index=False)
    manifest_path = fixture / "eligibility_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update(row_count=len(table), table_sha256=sha256_file(path), **metadata)
    manifest_path.write_text(json.dumps(manifest))


def _save_raw(fixture, raw):
    path = fixture / "source/raw/prices_raw_2020.parquet"
    raw.to_parquet(path, index=False)
    manifest_path = fixture / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][0]["sha256"] = sha256_file(path)
    manifest_path.write_text(json.dumps(manifest))


def _run(fixture, tmp_path):
    return run_synthetic_exploration(repo_root=_repo_root(), fixture_root=fixture,
                                     output_dir=tmp_path / "output", method_config_path=METHOD_CONFIG)


def test_exit_open_extremes_do_not_pollute_holding_diagnostic(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    raw = pd.read_parquet(fixture / "source/raw/prices_raw_2020.parquet")
    exit_day = raw["date"].max()
    raw.loc[raw["date"].eq(exit_day), ["max", "min"]] = [1000000., .001]
    _save_raw(fixture, raw)
    result = _run(fixture, tmp_path)
    diagnostics = result.mfe_mae.set_index(["run_label", "stock_id"])
    assert diagnostics.loc[("CANDIDATE_COHORT", "2330"), "mfe"] == pytest.approx(105 / 100.1 - 1)
    assert diagnostics.loc[("CANDIDATE_COHORT", "2454"), "mfe"] == pytest.approx(101 / 100.1 - 1)
    assert diagnostics["mae"].tolist() == pytest.approx([89 / 100.1 - 1] * 4)


@pytest.mark.parametrize("problem", ["cash", "split", "multi_leg", "missing_raw", "missing_eligibility"])
def test_diagnostic_ca_or_missing_session_is_unavailable(tmp_path, problem):
    from astraquant.research.baseline_60d_exploration import _mfe_mae_diagnostics
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    normal = _run(fixture, tmp_path)
    table = pd.read_csv(fixture / "eligibility.csv", dtype={"stock_id": str})
    days = sorted(table["date"].unique())
    affected = table["stock_id"].eq("2330") & table["date"].eq(days[62])
    if problem == "missing_eligibility":
        table = table.loc[~affected]
    elif problem != "missing_raw":
        table.loc[affected, "ca_path_status"] = problem.upper()
    _save_eligibility(fixture, table)
    if problem == "missing_raw":
        raw_path = fixture / "source/raw/prices_raw_2020.parquet"
        raw = pd.read_parquet(raw_path)
        raw = raw.loc[~(raw["stock_id"].eq("2330") & pd.to_datetime(raw["date"]).eq(pd.Timestamp(days[62])))]
        _save_raw(fixture, raw)
    eligibility = load_eligibility_table(table_path=fixture / "eligibility.csv", manifest_path=fixture / "eligibility_manifest.json")
    diagnostics = _mfe_mae_diagnostics(source_root=fixture / "source", trades=normal.candidate_trades,
                                     sessions=tuple(pd.Timestamp(d).date() for d in days), eligibility=eligibility)
    row = diagnostics.set_index("stock_id").loc["2330"]
    assert row["status"] == "UNAVAILABLE"
    assert pd.isna(row["mfe"]) and pd.isna(row["mae"])


@pytest.mark.parametrize("problem", ["economic", "missing_row", "missing_raw", "suspended", "cash", "split"])
def test_first_holding_problem_preserves_entry_and_blocks_portfolio(tmp_path, problem):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    table = pd.read_csv(fixture / "eligibility.csv", dtype={"stock_id": str})
    days = sorted(table["date"].unique())
    affected = table["stock_id"].eq("2330") & table["date"].eq(days[63])
    if problem == "economic":
        table.loc[affected, ["eligibility_status", "reason_code", "baseline_issue_b_any"]] = ["BLOCKED", "ECONOMIC_CONTENT_UNRESOLVED", True]
    elif problem == "missing_row":
        table = table.loc[~affected]
    elif problem in {"cash", "split"}:
        table.loc[affected, "ca_path_status"] = problem.upper()
    _save_eligibility(fixture, table)
    if problem == "missing_raw":
        path = fixture / "source/raw/prices_raw_2020.parquet"
        raw = pd.read_parquet(path)
        raw = raw.loc[~(raw["stock_id"].eq("2330") & pd.to_datetime(raw["date"]).eq(pd.Timestamp(days[63])))]
        _save_raw(fixture, raw)
    if problem == "suspended":
        path = fixture / "source/reference/tradability.parquet"
        trad = pd.read_parquet(path)
        mask = trad["stock_id"].eq("2330") & pd.to_datetime(trad["date"]).eq(pd.Timestamp(days[63]))
        trad.loc[mask, ["observed_trade", "valid_ohlc"]] = False
        trad.to_parquet(path, index=False)
        manifest_path = fixture / "source_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][1]["sha256"] = sha256_file(path)
        manifest_path.write_text(json.dumps(manifest))
    result = _run(fixture, tmp_path)
    assert result.report["candidate_funnel"]["eligible_candidates"] == 3
    metrics = result.report["candidate_cohort"]["metrics"]
    assert (metrics["n_closed"], metrics["n_open"], metrics["n_data_censored"]) == (1, 1, 1)
    assert metrics["entered_trade_denominator"] == 3
    assert metrics["data_censored_share"] == pytest.approx(1/3)
    assert metrics["return_statistics_scope"] == "RESOLVED_CLOSED_TRADES_ONLY_NOT_OVERALL_EXPECTANCY"
    censored = result.censored_positions
    one = censored[censored["run_label"].eq("CANDIDATE_COHORT")].iloc[0]
    assert one["stock_id"] == "2330"
    assert one["entry_at"].startswith(days[62])
    assert one["censored_at"] == days[63]
    assert one["last_reliable_date"] == days[62]
    assert one["last_reliable_boundary"] == "SESSION_CLOSE"
    assert one["status"] == "DATA_CENSORED" and one["resolution_status"] == "UNRESOLVED"
    assert "2330" not in set(result.candidate_trades["stock_id"])
    assert set(result.open_positions["stock_id"]) == {"3008"}
    capital = result.report["capital_constrained"]
    assert capital["performance_status"] == "BLOCKED_DATA_CENSORED"
    assert capital["blocked_at"] == days[63]
    assert capital["entries_executed"] == 2
    assert capital["metrics"]["n_closed"] == 0  # No planned exit at unreliable open.
    assert capital["metrics"]["n_open"] == 0
    assert capital["metrics"]["n_data_censored"] == 2
    assert capital["metrics"]["data_censored_share"] == 1
    assert result.capital_trades.empty


def test_sol4_mapping_retains_pit_flags_reasons_and_original_denominator(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    table = pd.read_csv(fixture / "eligibility.csv", dtype={"stock_id": str})
    table["limited_exploration_label"] = table["eligibility_status"].map({"ELIGIBLE": "ELIGIBLE_WITH_PIT_EVIDENCE_INCOMPLETE", "BLOCKED": "NOT_ELIGIBLE"})
    table = table.drop(columns=["eligibility_status", "reason_code", "reason_detail"])
    table["baseline_issue_a_any"] = True
    table["baseline_evidence_state"] = "INDETERMINATE"
    table["raw_version_evidence_reason"] = "HISTORICAL_VERSION_UNKNOWN"
    table["ma120_b_event_ids"] = "synthetic-id-1;synthetic-id-2"
    table["ma120_b_reasons"] = "synthetic-reason-1;synthetic-reason-2"
    _save_eligibility(fixture, table, schema_version="2", original_row_denominator=2048,
                      source_revision="synthetic-baseline-exploration-v1",
                      contract_revision="synthetic-contract-r2", evidence_revision="synthetic-evidence-r2",
                      private_delivery_revision="synthetic-delivery-r2")
    result = _run(fixture, tmp_path)
    audit = result.eligibility_rows
    assert audit["baseline_issue_a_any"].all()
    assert set(audit["eligibility_status"]) == {"ELIGIBLE_WITH_PIT_EVIDENCE_INCOMPLETE", "BLOCKED"}
    pd.testing.assert_series_equal(audit.set_index(["date", "stock_id"])["limited_exploration_label"],
                                   table.assign(date=pd.to_datetime(table["date"])).set_index(["date", "stock_id"])["limited_exploration_label"].sort_index())
    assert audit["ma120_b_event_ids"].eq("synthetic-id-1;synthetic-id-2").all()
    assert audit["ma120_b_reasons"].eq("synthetic-reason-1;synthetic-reason-2").all()
    assert audit["baseline_evidence_state"].eq("INDETERMINATE").all()
    population = result.report["population"]
    assert population["row_denominator"] == 2048
    assert population["provided_row_count"] == 1024
    assert population["evidence_manifest"]["contract_revision"] == "synthetic-contract-r2"
    assert result.report["candidate_cohort"]["metrics"]["n_closed"] == 2
    assert "baseline_issue_a_any" in result.candidate_funnel


def test_pit_label_cannot_erase_b_exposure(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    table = pd.read_csv(fixture / "eligibility.csv", dtype={"stock_id": str})
    table["eligibility_status"] = "ELIGIBLE_WITH_PIT_EVIDENCE_INCOMPLETE"
    table["baseline_issue_a_any"] = True
    table["baseline_evidence_state"] = "INDETERMINATE"
    _save_eligibility(fixture, table)
    with pytest.raises(BaselineExplorationError, match="contradicts A/B/C"):
        _run(fixture, tmp_path)


def test_formal_cli_still_rejects_before_any_fixture_access(tmp_path):
    import os
    import subprocess
    import sys
    result = subprocess.run([sys.executable, str(_repo_root() / "scripts/baseline_60d_exploration_runner.py"),
                             "--mode", "FORMAL_RESEARCH", "--build-fixture",
                             "--fixture-root", str(tmp_path / "must-not-exist"), "--output-dir", str(tmp_path / "output")],
                            capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(_repo_root() / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")})
    assert result.returncode != 0
    assert "formal" in result.stderr.lower()
    assert not (tmp_path / "must-not-exist").exists()


def test_entry_day_censor_is_sticky_and_prevents_later_capital_entries(tmp_path, monkeypatch):
    from astraquant.research.config_engine import ResearchConfigEngine
    from astraquant.portfolio.performance_reporting import portfolio_fills
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    table = pd.read_csv(fixture / "eligibility.csv", dtype={"stock_id": str})
    days = sorted(table["date"].unique())
    affected = table["stock_id"].eq("2330") & table["date"].eq(days[62])
    table.loc[affected, ["eligibility_status", "reason_code", "baseline_issue_b_any"]] = ["BLOCKED", "ECONOMIC_CONTENT_UNRESOLVED", True]
    # Day 63 recovers; the previously censored portfolio must never restart.
    _save_eligibility(fixture, table)
    panel_path = fixture / "panel.parquet"
    panel = pd.read_parquet(panel_path)
    panel.loc[panel["stock_id"].eq("3008") & pd.to_datetime(panel["date"]).eq(pd.Timestamp(days[61])), "close"] = 100.
    panel.loc[panel["stock_id"].eq("3008") & pd.to_datetime(panel["date"]).eq(pd.Timestamp(days[62])), "close"] = 110.
    panel.to_parquet(panel_path, index=False)
    executions = []
    original = ResearchConfigEngine.execute_prepared

    def record(self, **kwargs):
        executed = original(self, **kwargs)
        executions.append((executed.simulation, portfolio_fills(kwargs["simulator"].portfolio)))
        return executed

    monkeypatch.setattr(ResearchConfigEngine, "execute_prepared", record)
    result = _run(fixture, tmp_path)
    one = result.censored_positions.query("run_label == 'CANDIDATE_COHORT'").iloc[0]
    assert one["entry_at"].startswith(days[62])
    assert one["censored_at"] == days[62]
    assert one["last_reliable_date"] == days[62]
    assert one["last_reliable_boundary"] == "ENTRY_OPEN"
    assert one["phase"] == "BEFORE_CLOSE"
    capital_simulation, capital_fills = executions[-1]
    assert capital_simulation.data_censored_at.isoformat() == days[62]
    assert capital_simulation.sessions[-1].session_date.isoformat() == days[61]
    assert len(capital_fills) == 2 and all(fill.side == "buy" for fill in capital_fills)
    assert all(fill.ticker != "3008" for fill in capital_fills)
    # Independent candidate 3008 still enters; only the unreliable portfolio stops.
    assert "3008" in set(result.open_positions["stock_id"])
    assert result.report["capital_constrained"]["full_period_performance_available"] is False


def test_leaving_universe_with_daily_holding_evidence_does_not_censor(tmp_path):
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    table = pd.read_csv(fixture / "eligibility.csv", dtype={"stock_id": str})
    table["in_original_all_liquid"] = True
    table.loc[table["date"].eq(table["date"].max()), "in_original_all_liquid"] = False
    _save_eligibility(fixture, table)
    result = _run(fixture, tmp_path)
    assert result.report["candidate_cohort"]["metrics"]["n_closed"] == 2
    assert result.censored_positions.empty


def test_candidate_cohort_exposes_its_own_censoring_status(tmp_path):
    """候選族群與資金組合的截尾語意不同，兩邊都要能直接讀到狀態。"""
    fixture = build_synthetic_fixture(tmp_path / "fixture")
    clean = _run(fixture, tmp_path / "clean")
    cohort = clean.report["candidate_cohort"]
    assert cohort["performance_status"] == "COMPLETE"
    assert cohort["censored_ticker_count"] == 0
    assert cohort["censored_first_date"] is None
    assert cohort["full_period_performance_available"] is True
    assert cohort["censoring_scope"] == "PER_TICKER_INDEPENDENT_DOES_NOT_STOP_OTHER_TICKERS"
    assert clean.report["capital_constrained"]["performance_status"] == "COMPLETE"

    table = pd.read_csv(fixture / "eligibility.csv", dtype={"stock_id": str})
    days = sorted(table["date"].unique())
    affected = table["stock_id"].eq("2330") & table["date"].eq(days[63])
    table.loc[affected, ["eligibility_status", "reason_code", "baseline_issue_b_any"]] = [
        "BLOCKED", "ECONOMIC_CONTENT_UNRESOLVED", True]
    _save_eligibility(fixture, table)
    censored_run = _run(fixture, tmp_path / "censored")
    cohort = censored_run.report["candidate_cohort"]

    # 一檔被截尾，但其他檔照跑完 —— 這正是與資金組合不同的地方。
    assert cohort["performance_status"] == "PARTIAL_DATA_CENSORED"
    assert cohort["censored_ticker_count"] == 1
    assert cohort["censored_first_date"] == days[63]
    assert cohort["full_period_performance_available"] is False
    assert cohort["metrics"]["n_closed"] == 1
    assert cohort["metrics"]["n_data_censored"] == 1

    # 資金組合則是整個組合停住，不是只停一檔。
    capital = censored_run.report["capital_constrained"]
    assert capital["performance_status"] == "BLOCKED_DATA_CENSORED"
    assert capital["blocked_at"] == days[63]
    assert capital["metrics"]["data_censored_share"] == 1

    note = "candidate-cohort censoring is per ticker; capital-constrained censoring stops the shared portfolio"
    assert note in censored_run.report["notes"]
