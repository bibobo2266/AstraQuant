"""Bounded source-quality evidence; no signal scan, returns, or strategy execution.

Run from repo root with SOURCE_ROOT=<frozen source>/data and SOURCE_REVISION.
Only key coverage is read market-wide. Price reconstruction uses four fixed IDs.
Outputs have a new prefix and never overwrite the accepted audit artifacts.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from astraquant.research.ca_adjustment_audit import (
    PRICE_REBUILD_ATOL, normalize_dividend_events,
    rebuild_final_adjusted_close, universe_masks,
)

REV = "fb8b042b46dc38838d103544ca17da10286c7bfe"
ROOT = Path(os.environ["SOURCE_ROOT"])
OUT = Path("out/layer1_data_decision")
IDS = ["1101", "1216", "2317", "2330"]
START, END = pd.Timestamp("2016-01-04"), pd.Timestamp("2021-12-31")


def norm(x):
    x = x.copy()
    x["date"] = pd.to_datetime(x.date).dt.normalize()
    x["stock_id"] = x.stock_id.astype(str)
    assert not x.duplicated(["date", "stock_id"]).any()
    return x


def save(name, x):
    x.to_csv(OUT / f"{name}.csv", index=False, float_format="%.15g")


def main():
    assert os.environ["SOURCE_REVISION"] == REV
    OUT.mkdir(parents=True, exist_ok=True)
    # Verify exact source blobs, including bounded ancestor snapshots, before reading.
    input_manifest = ROOT.parent / "input_blobs.json"
    if not input_manifest.exists():
        input_manifest = OUT / "inputs.json"
    inputs = json.loads(input_manifest.read_text())
    for item in inputs:
        b = (ROOT.parent / item["path"]).read_bytes()
        assert hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest() == item["sha"], item
        item["sha256"] = hashlib.sha256(b).hexdigest()
    (OUT / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")

    original = pd.read_parquet(ROOT / "adj/dividend_events.parquet")
    e = original.copy()
    e["date"] = pd.to_datetime(e.date, errors="coerce").dt.normalize()
    before = pd.to_numeric(e.before_price, errors="coerce")
    after = pd.to_numeric(e.after_price, errors="coerce")
    e["ratio"] = after / before
    e["reason"] = np.select(
        [e.date.isna(), ~(before.gt(0) & after.gt(0)), ~e.ratio.between(.5, 1.2)],
        ["INVALID_DATE", "NONPOSITIVE_OR_MISSING_PRICE", "RATIO_OUT_OF_RANGE"], default="KEEP")
    ev = normalize_dividend_events(original)
    save("excluded_events", e[e.reason.ne("KEEP")])
    annual = []
    for y in range(2015, 2027):
        g, n = e[e.date.dt.year.eq(y)], ev[ev.date.dt.year.eq(y)]
        annual.append(dict(year=y, raw_rows=len(g), first=g.date.min(), last=g.date.max(),
                           invalid_price=int(g.reason.eq("NONPOSITIVE_OR_MISSING_PRICE").sum()),
                           ratio_excluded=int(g.reason.eq("RATIO_OUT_OF_RANGE").sum()),
                           valid_pre_group=int(g.reason.eq("KEEP").sum()), normalized_rows=len(n),
                           collapsed_rows=int(g.reason.eq("KEEP").sum())-len(n)))
    save("events_by_year", pd.DataFrame(annual))

    # Reproduce online event assignment using only the exact adjusted observation keys.
    # No MA/N60 calculations, candidate effects, or full source_validation scan.
    adj_keys, raw_keys, coverage = [], [], []
    for y in range(2015, 2022):
        a = norm(pd.read_parquet(ROOT / f"adj/prices_adj_{y}.parquet", columns=["date", "stock_id"]))
        r = norm(pd.read_parquet(ROOT / f"raw/prices_raw_{y}.parquet", columns=["date", "stock_id"]))
        adj_keys.append(a); raw_keys.append(r)
        j = a.merge(r, on=["date", "stock_id"], how="outer", indicator=True, validate="one_to_one")
        coverage.append(dict(year=y, adjusted_rows=len(a), raw_rows=len(r), adjusted_ids=a.stock_id.nunique(),
                             raw_ids=r.stock_id.nunique(), both=int(j._merge.eq("both").sum()),
                             adjusted_only=int(j._merge.eq("left_only").sum()), raw_only=int(j._merge.eq("right_only").sum())))
    save("price_key_coverage", pd.DataFrame(coverage))
    ak, rk = pd.concat(adj_keys), pd.concat(raw_keys)
    groups = {s: np.sort(g.date.to_numpy()) for s, g in ak.groupby("stock_id")}
    rawsets = {s: set(g.date) for s, g in rk.groupby("stock_id")}
    assignments = []
    for row in ev.itertuples(index=False):
        dates = groups.get(row.stock_id)
        first = pd.NaT
        if dates is None:
            status = "NO_STOCK_IN_ADJUSTED_KEYS"
        else:
            pos = dates.searchsorted(row.date.to_datetime64(), side="left")
            if pos == len(dates):
                status = "AFTER_E1_NOT_EXPECTED" if row.date > END else "NO_SUBSEQUENT_OBSERVATION"
            else:
                first = pd.Timestamp(dates[pos])
                status = "WARMUP_PROCESSED" if first < START else "E1_PROCESSED"
        assignments.append(dict(stock_id=row.stock_id, event_date=row.date, ratio=row.ratio,
                                observation_date=first, status=status,
                                exact_day_observation=bool(pd.notna(first) and first == row.date),
                                raw_key_at_processing=bool(pd.notna(first) and first in rawsets.get(row.stock_id,set()))))
    assign = pd.DataFrame(assignments)
    # Persist only E1 deferred assignments; yearly totals cover every status.
    save("event_assignment_deferred", assign[assign.status.eq("E1_PROCESSED") & ~assign.exact_day_observation])
    statuses = ["E1_PROCESSED", "WARMUP_PROCESSED", "NO_STOCK_IN_ADJUSTED_KEYS", "NO_SUBSEQUENT_OBSERVATION", "AFTER_E1_NOT_EXPECTED"]
    counts = assign.assign(event_year=assign.event_date.dt.year).groupby(["event_year", "status"]).size().reindex(pd.MultiIndex.from_product([range(2015,2027),statuses],names=["event_year","status"]),fill_value=0).rename("rows").reset_index()
    save("event_assignment_counts", counts)
    actual = assign[assign.status.eq("E1_PROCESSED")].observation_date.dt.year.value_counts()
    accepted = pd.read_csv("out/ca_adjustment_invariance_audit_yearly.csv").set_index("year").online_events_applied
    assert actual.reindex(accepted.index, fill_value=0).sort_index().equals(accepted.sort_index())

    # Fixed quality sample: first observation of each E1 year, four preselected IDs;
    # plus before/on known 2016 cash ex-dates for 1216 and 2330. No outcome selection.
    price_rows = []
    cross_sections = []
    for y in range(2016, 2022):
        a = norm(pd.read_parquet(ROOT / f"adj/prices_adj_{y}.parquet", columns=["date", "stock_id", "close", "Trading_money"]))
        r = norm(pd.read_parquet(ROOT / f"raw/prices_raw_{y}.parquet", columns=["date", "stock_id", "close", "Trading_money", "source"]))
        day = a.date.min()
        dates = [day] + ([pd.Timestamp(d) for d in ["2016-06-24", "2016-06-27", "2016-08-03", "2016-08-04"]] if y == 2016 else [])
        a = a[a.date.isin(dates)]; r = r[r.date.isin(dates)]
        j = a.rename(columns={"close":"adjusted_close"}).merge(r.rename(columns={"close":"raw_close", "Trading_money":"raw_Trading_money"}), on=["date", "stock_id"], how="outer", validate="one_to_one")
        j["Trading_money"] = j.Trading_money.combine_first(j.raw_Trading_money)
        cross_sections.append(j)
        selected = j.stock_id.isin(IDS) & j.date.eq(day)
        if y == 2016:
            selected |= (j.stock_id.eq("1216") & j.date.isin(pd.to_datetime(["2016-08-03","2016-08-04"]))) | (j.stock_id.eq("2330") & j.date.isin(pd.to_datetime(["2016-06-24","2016-06-27"])))
        price_rows.append(j[selected])
    samples = pd.concat(price_rows, ignore_index=True)
    rebuilt = rebuild_final_adjusted_close(samples, ev)
    samples = samples.merge(rebuilt, on=["date","stock_id"], validate="one_to_one")
    samples["diff_round_once"] = samples.adjusted_close-samples.rebuild_round_once
    samples["diff_sequential"] = samples.adjusted_close-samples.rebuild_sequential_round4
    samples["match_round_once"] = samples.diff_round_once.abs().le(PRICE_REBUILD_ATOL+1e-12)
    samples["match_sequential"] = samples.diff_sequential.abs().le(PRICE_REBUILD_ATOL+1e-12)
    # Exact existing source_validation function, without importing/executing its main.
    module = ast.parse(Path("scripts/source_ca_adjustment_invariance_audit.py").read_text())
    fn = next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=="source_validation")
    ns = dict(pd=pd, np=np, E1_START=START, E1_END=END, PRICE_REBUILD_ATOL=PRICE_REBUILD_ATOL)
    exec(compile(ast.Module(body=[fn],type_ignores=[]), "accepted_source_validation", "exec"), ns)
    save("sample_source_validation", ns["source_validation"](pd.concat(price_rows, ignore_index=True),rebuilt))
    cs = pd.concat(cross_sections, ignore_index=True)
    tr = norm(pd.read_parquet(ROOT / "reference/tradability.parquet", columns=["date","stock_id","observed_trade","valid_ohlc"]))
    cs = cs.merge(tr[tr.date.isin(cs.date.unique())],on=["date","stock_id"],how="left",validate="one_to_one")
    excluded = set(pd.read_csv("docs/SOURCE_CA_PIT_EXCLUSIONS.csv",dtype={"ticker":str}).ticker)
    masks = universe_masks(cs, excluded=excluded)
    samples = samples.merge(masks[["date","stock_id","fixed_other_qualifiers","adjusted_counts","raw_counts","adjusted_turnover_pct"]],on=["date","stock_id"],validate="one_to_one")
    assert samples[samples.stock_id.isin(["1216","2330"])].adjusted_counts.all()
    samples["p2_060_excluded"] = samples.stock_id.isin(excluded)
    save("price_samples",samples)
    save("sample_events",e[e.stock_id.isin(IDS)])
    steps = []
    for row in samples.itertuples(index=False):
        value, factor, bound = row.raw_close, 1.0, 0.0
        for step, event in enumerate(ev[ev.stock_id.eq(row.stock_id) & ev.date.gt(row.date)].itertuples(index=False),1):
            prior=value;value=float(np.round(value*event.ratio,4));factor*=event.ratio
            bound=bound*abs(event.ratio)+0.00005
            steps.append(dict(date=row.date,stock_id=row.stock_id,step=step,event_date=event.date,ratio=event.ratio,
                              value_before=prior,value_after_round4=value,cumulative_factor=factor,rounding_error_bound=bound))
        assert abs(value-row.rebuild_sequential_round4)<1e-10
    save("reconstruction_steps",pd.DataFrame(steps))

    ledger = pd.read_parquet(ROOT / "reference/corporate_actions_ledger.parquet")
    ledger["event_date"] = pd.to_datetime(ledger.event_date)
    official16 = ledger[ledger.event_type.eq("ex_right_dividend") & ledger.event_date.dt.year.eq(2016)].copy()
    # Alternative ledger evidence proves source-table absence != no 2016 CA.
    price16a, price16r = adj_keys[1], raw_keys[1]
    official16["adjusted_stock_present"] = official16.stock_id.isin(price16a.stock_id)
    official16["raw_stock_present"] = official16.stock_id.isin(price16r.stock_id)
    ak16=set(zip(price16a.stock_id,price16a.date)); rk16=set(zip(price16r.stock_id,price16r.date))
    official16["adjusted_exact_day"]=[(s,d) in ak16 for s,d in zip(official16.stock_id,official16.event_date)]
    official16["raw_exact_day"]=[(s,d) in rk16 for s,d in zip(official16.stock_id,official16.event_date)]
    save("official_2016_coverage",official16.groupby("source_name").agg(rows=("stock_id","size"),stocks=("stock_id","nunique"),adjusted_stock_present=("adjusted_stock_present","sum"),raw_stock_present=("raw_stock_present","sum"),adjusted_exact_day=("adjusted_exact_day","sum"),raw_exact_day=("raw_exact_day","sum")).reset_index())
    save("sample_official_events",ledger[ledger.stock_id.isin(IDS)])
    dividend = pd.read_parquet(ROOT / "fundamentals/dividend.parquet")
    save("sample_dividend_details",dividend[dividend.stock_id.isin(IDS)])
    missing_cash=[]
    for sid, exday, prior_day in [("1216","2016-08-04","2016-08-03"),("2330","2016-06-27","2016-06-24")]:
        detail=dividend[dividend.stock_id.eq(sid) & dividend.CashExDividendTradingDate.eq(exday)]
        assert len(detail)==1
        cash=float(detail.CashEarningsDistribution.iloc[0]+detail.CashStatutorySurplus.iloc[0])
        before_close=float(samples.loc[samples.stock_id.eq(sid)&samples.date.eq(pd.Timestamp(prior_day)),"raw_close"].iloc[0])
        ratio=(before_close-cash)/before_close
        assert not e[e.stock_id.eq(sid)&e.date.eq(pd.Timestamp(exday))].shape[0]
        for row in samples[samples.stock_id.eq(sid)&samples.date.lt(pd.Timestamp(exday))].itertuples(index=False):
            diag=row.raw_close*row.future_factor*ratio
            missing_cash.append(dict(date=row.date,stock_id=sid,ex_date=exday,prior_date=prior_day,prior_raw_close=before_close,cash_per_share=cash,diagnostic_missing_ratio=ratio,
                                     diagnostic_rebuild=diag,stored_adjusted=row.adjusted_close,residual=row.adjusted_close-diag,
                                     interpretation="diagnostic only; no production event inserted"))
    save("missing_cash_diagnostic",pd.DataFrame(missing_cash))
    # Before/after a source update: historical prices only, no E3 prices/effects.
    snaps = []
    for ref in ["906f257d73d6515212d922aea4b6afd31b736129","e10810504c07f92dcbcca957d0156b21233db358"]:
        x=norm(pd.read_parquet(ROOT.parent / "snapshots" / ref / "prices_adj_2017.parquet",filters=[("stock_id","in",IDS)]))
        x=x[x.date.eq(pd.Timestamp("2017-01-03"))][["date","stock_id","close"]]
        x["revision"]=ref;snaps.append(x)
    save("historical_snapshot_trace",pd.concat(snaps))
    summary=dict(source_revision=REV,raw_event_rows=len(e),normalized_event_rows=len(ev),
                 invalid_date_rows=int(e.reason.eq("INVALID_DATE").sum()),
                 e1_processed=int(assign.status.eq("E1_PROCESSED").sum()),
                 event2016_rows=int(e.date.dt.year.eq(2016).sum()),
                 official2016_rows=len(official16),official2016_stocks=official16.stock_id.nunique(),
                 sample_rows=len(samples),sample_ids=IDS,full_audit_rerun=False,strategy_runs=[],
                 source_validation_tolerance=PRICE_REBUILD_ATOL,
                 legacy_match_column_name="match_within_0_00005 actually uses 0.0001; unchanged")
    (OUT / "summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))


if __name__ == "__main__":
    main()
