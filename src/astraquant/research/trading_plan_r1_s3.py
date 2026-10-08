"""Scoped S3 wiring. Engineering fixtures cannot produce performance metrics."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from copy import deepcopy
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

import pandas as pd

from astraquant.data.market_coordinates import PriceUse, SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage
from astraquant.execution.fills import ExecutionFillFactory, NotExecutableError
from astraquant.execution.market_data import ExecutionAvailability, ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
from astraquant.portfolio.models import OrderIntent
from astraquant.research.epoch_governance import resolve_historical_effect_period
from astraquant.research.technical_components import _rsi_value
from astraquant.research.trading_plan_r1 import (
    BOOL_COLUMNS, COMMISSION, FEES, FLOAT_COLUMNS, OBJECT_COLUMNS, RULE_VERSION,
    SCHEMAS, SLIPPAGE, TAX, Position, SharedLedger, TradingPlanR1, _day, _finite,
    _metric_rows, _plain,
)
from astraquant.validation.accounting_gate import AccountingReadiness

S1_SHA = "2fc9680a3cbb74b15d690edbeb02ed03457b26c74dd682a877b1c6e93f8dc38e"
LIMIT_SHA = "a38f5d63726df1daf4982067b7ce592dc6893f6768af8908e5dae1302b5c0a0a"
SOURCE_REVISION = "3e7c4b6d9cde3b18942710fa977db02f89bffa0d"
LIMIT_REVISION = "67e069e962e365b4f4c09fa466decd66bb70fc82"
VERSION = "s3-canonical-wiring-v1"
EXIT_MODES = {"sma20", "sma20_or_rsi13_lt50"}
S3_SCHEMAS = {name: cols + ("input_binding", "exit_mode", "execution_version")
              for name, cols in SCHEMAS.items()}
_SEAL = object()


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _inside(root, path):
    target = (root / path).resolve()
    target.relative_to(root)
    return target


def write_source_manifest(root, *, source_root, panel, supplement, output):
    """Inventory the existing accepted inputs; never create an approval receipt."""
    root = Path(root).resolve()
    source = _inside(root, source_root)
    paths = [(source / "raw" / f"prices_raw_{year}.parquet", "raw")
             for year in range(2015, 2022)]
    paths += [(source / "reference" / "tradability.parquet", "tradability"),
              (source / "reference" / "corporate_actions_official.csv", "events")]
    paths += [(p, "limits") for p in sorted((source / "reference").glob("price_limit_*.parquet"))
              if any(str(year) in p.name for year in range(2015, 2019))]
    if len([p for p, role in paths if role == "limits"]) != 4:
        raise ValueError("four existing 2015–2018 limit files required")
    paths += [(_inside(root, panel), "panel"), (_inside(root, supplement), "supplement")]
    if _hash(_inside(root, panel)) != S1_SHA or _hash(_inside(root, supplement)) != LIMIT_SHA:
        raise ValueError("wrong accepted S1/limit bytes")
    period = resolve_historical_effect_period("E1")
    manifest = dict(schema_version=VERSION, purpose="s3_source",
        source_root=str(source.relative_to(root)), source_revision=SOURCE_REVISION,
        limit_revision=LIMIT_REVISION,
        period=dict(epoch="E1", start=str(period.start), end=str(period.end)),
        entry_modes=["close", "next_open"], exit_modes=sorted(EXIT_MODES),
        files=[dict(path=str(p.relative_to(root)), role=role, sha256=_hash(p)) for p, role in paths])
    _inside(root, output).write_text(json.dumps(manifest, indent=2)+"\n")
    return manifest


class S3Inputs:
    """Verified file inventory plus an input-bound existing accounting gate.

    Production is pinned to the accepted S1/limit bytes and pristine source Git
    revision. The separate fixture route is explicitly engineering-only.
    """
    def __init__(self):
        raise TypeError("use open_source or open_engineering_fixture")

    @classmethod
    def open_source(cls, root, manifest, receipt):
        return cls._open(root, manifest, receipt, fixture=False)

    @classmethod
    def open_engineering_fixture(cls, root, manifest, receipt):
        return cls._open(root, manifest, receipt, fixture=True)

    @classmethod
    def _open(cls, root, manifest, receipt, *, fixture):
        self = object.__new__(cls)
        self.root = Path(root).resolve()
        self.manifest_path = _inside(self.root, manifest)
        self.receipt_path = _inside(self.root, receipt)
        self.manifest = json.loads(self.manifest_path.read_text())
        self.fixture = fixture
        self.source_kind = "s3_engineering_fixture" if fixture else "s3_real"
        m = self.manifest
        expected_purpose = "s3_engineering_fixture" if fixture else "s3_source"
        if m.get("schema_version") != VERSION or m.get("purpose") != expected_purpose:
            raise ValueError("unauthorized S3 input purpose/version")
        period = resolve_historical_effect_period("E1")
        if m.get("period") != {"epoch": "E1", "start": str(period.start), "end": str(period.end)}:
            raise ValueError("S3 period must remain the declared E1")
        if m.get("entry_modes") != ["close", "next_open"] or len(m.get("exit_modes", [])) != 2 or set(m.get("exit_modes", [])) != EXIT_MODES:
            raise ValueError("only the fixed S3 four cells are supported")
        if m.get("source_revision") != SOURCE_REVISION or m.get("limit_revision") != LIMIT_REVISION:
            raise ValueError("unaccepted S3 input revision")
        entries = m.get("files", [])
        if len({e["path"] for e in entries}) != len(entries):
            raise ValueError("duplicate input inventory path")
        self.inventory = deepcopy(entries)
        self.input_digest = _digest(m)
        self._manifest_sha = _hash(self.manifest_path)
        self._receipt_sha = _hash(self.receipt_path)
        self.binding_id = _digest(dict(input=self.input_digest, receipt=self._receipt_sha))
        self.source_root = _inside(self.root, m["source_root"])
        self._seal = _SEAL
        self.verify()
        self._bars = self._read_bars()
        return self

    def role(self, name):
        entries = [e for e in self.inventory if e["role"] == name]
        if len(entries) != 1:
            raise ValueError(f"exactly one {name} input required")
        return _inside(self.root, entries[0]["path"])

    def verify(self):
        if getattr(self, "_seal", None) is not _SEAL:
            raise ValueError("unverified S3 binding")
        if (_digest(self.manifest) != self.input_digest or self.inventory != self.manifest["files"]
                or self.binding_id != _digest(dict(input=self.input_digest, receipt=self._receipt_sha))
                or self.manifest["purpose"] != ("s3_engineering_fixture" if self.fixture else "s3_source")
                or self.source_kind != ("s3_engineering_fixture" if self.fixture else "s3_real")):
            raise ValueError("changed S3 binding identity")
        if _hash(self.manifest_path) != self._manifest_sha or _hash(self.receipt_path) != self._receipt_sha:
            raise ValueError("changed input manifest/accounting receipt")
        for entry in self.inventory:
            if _hash(_inside(self.root, entry["path"])) != entry["sha256"]:
                raise ValueError(f"input hash mismatch: {entry['path']}")
        for role, relative in [("tradability", "reference/tradability.parquet"),
                               ("events", "reference/corporate_actions_official.csv")]:
            if self.role(role) != (self.source_root / relative).resolve():
                raise ValueError("inventory does not bind canonical source path")
        for entry in self.inventory:
            if entry["role"] not in {"raw", "tradability", "events", "limits", "panel", "supplement"}:
                raise ValueError("unknown S3 input role")
            if entry["role"] in {"raw", "limits"}:
                directory = "raw" if entry["role"] == "raw" else "reference"
                if _inside(self.root, entry["path"]) != (self.source_root / directory / Path(entry["path"]).name).resolve():
                    raise ValueError("unbound canonical RAW/limit path")
        if not self.fixture:
            if _hash(self.role("panel")) != S1_SHA or _hash(self.role("supplement")) != LIMIT_SHA:
                raise ValueError("wrong accepted S1/limit bytes")
            revision = subprocess.check_output(["git", "-C", str(self.source_root), "rev-parse", "HEAD"], text=True).strip()
            if revision != SOURCE_REVISION:
                raise ValueError("wrong immutable RAW source checkout")
            top = Path(subprocess.check_output(["git", "-C", str(self.source_root), "rev-parse", "--show-toplevel"], text=True).strip())
            paths = [str(_inside(self.root, e["path"]).relative_to(top)) for e in self.inventory
                     if e["role"] in {"raw", "tradability", "events", "limits"}]
            subprocess.run(["git", "-C", str(top), "ls-files", "--error-unmatch", "--", *paths], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(top), "diff", "--quiet", "HEAD", "--", *paths], check=True)
            raw_names = {Path(e["path"]).name for e in self.inventory if e["role"] == "raw"}
            if raw_names != {f"prices_raw_{y}.parquet" for y in range(2015, 2022)}:
                raise ValueError("incomplete E1 RAW/warmup inventory")
        receipt = json.loads(self.receipt_path.read_text())
        if receipt.get("schema_version") != "s3-accounting-receipt-v1" or receipt.get("input_digest") != self.input_digest:
            raise ValueError("accounting evidence belongs to different inputs")
        checks = receipt.get("checks", {})
        if set(checks) != {f.name for f in fields(AccountingReadiness)} or any(type(v) is not bool for v in checks.values()):
            raise ValueError("complete typed AccountingReadiness evidence required")
        if not receipt.get("evidence"):
            raise ValueError("accounting evidence provenance required")
        self.readiness = AccountingReadiness(**checks)
        self.readiness.require_performance_unlocked()

    def _read_bars(self):
        panel = pd.read_parquet(self.role("panel")).reset_index()
        if {"date", "stock", "eligibility", "rs", "available_date"} - set(panel):
            raise ValueError("S1 panel keys/flags absent")
        panel["date"] = pd.to_datetime(panel.date).dt.normalize()
        panel["stock"] = panel.stock.astype(str)
        self._panel_keys = frozenset(zip(panel.date.map(_day), panel.stock))
        if panel.duplicated(["date", "stock"]).any():
            raise ValueError("duplicate S1 keys")
        raw = pd.concat([pd.read_parquet(_inside(self.root, e["path"])) for e in self.inventory if e["role"] == "raw"])
        raw["date"] = pd.to_datetime(raw.date).dt.normalize()
        raw["stock_id"] = raw.stock_id.astype(str)
        if raw.duplicated(["date", "stock_id"]).any():
            raise ValueError("duplicate RAW keys")
        start, end = self.manifest["period"]["start"], self.manifest["period"]["end"]
        if not panel.date.between(start, end).all() or raw.date.gt(end).any() or raw.date.lt("2015-01-01").any():
            raise ValueError("input dates outside fixed E1/warmup")
        raw = raw[raw.date.ge("2015-06-01") & raw.stock_id.isin(panel.stock.unique())].copy()
        missing = pd.MultiIndex.from_frame(panel[["date", "stock"]]).difference(
            pd.MultiIndex.from_frame(raw[["date", "stock_id"]]))
        if len(missing):
            raise ValueError("S1 keys lack RAW coverage")
        limits = pd.concat([pd.read_parquet(_inside(self.root, e["path"])) for e in self.inventory
                            if e["role"] in {"limits", "supplement"}], ignore_index=True)
        limits["date"] = pd.to_datetime(limits.date).dt.normalize()
        limits["stock_id"] = limits.stock_id.astype(str)
        if limits.duplicated(["date", "stock_id"]).any():
            raise ValueError("duplicate limit keys")
        needed = pd.MultiIndex.from_frame(panel[["date", "stock"]])
        if len(needed.difference(pd.MultiIndex.from_frame(limits[["date", "stock_id"]]))):
            raise ValueError("S1 keys lack exact limits")
        raw = raw.rename(columns={"stock_id": "stock", "max": "high", "min": "low", "Trading_Volume": "volume"})
        bars = raw.merge(panel[["date", "stock", "eligibility", "rs", "available_date"]], on=["date", "stock"], how="left", validate="one_to_one")
        bars = bars.merge(limits[["date", "stock_id", "limit_up", "limit_down"]].rename(columns={
            "stock_id": "stock", "limit_up": "limit_up_price", "limit_down": "limit_down_price"}), on=["date", "stock"], how="left", validate="one_to_one")
        bars["eligible"] = bars.eligibility.fillna(False).astype(bool)
        if (pd.to_datetime(bars.loc[bars.eligible, "available_date"]) > bars.loc[bars.eligible, "date"]).any():
            raise ValueError("future S1 availability")
        bars["available_date"] = bars.available_date.where(bars.available_date.notna(), bars.date)
        bars["source_kind"], bars["source"] = self.source_kind, self.binding_id
        events = pd.read_csv(self.role("events"), dtype={"stock_id": str})
        event_keys = set(zip(pd.to_datetime(events.event_date).map(_day), events.stock_id))
        bars["corporate_action"] = ["source_event_requires_accounting" if (_day(d), s) in event_keys else None
                                    for d, s in zip(bars.date, bars.stock)]
        return bars.sort_values(["stock", "date"]).reset_index(drop=True)


class _S3Ledger(SharedLedger):
    schemas = S3_SCHEMAS


class _OwnerCosts:
    def fee(self, *, side, quantity, price):
        return FEES.fee(side=side, quantity=quantity, price=price) + quantity * price * SLIPPAGE


class S3TradingPlanR1(TradingPlanR1):
    """Only a verified S3 bundle can enter; legacy entry points stay synthetic."""
    def __init__(self, *, inputs: S3Inputs, run_id, entry_mode, exit_mode, initial_cash=1_000_000):
        if not isinstance(inputs, S3Inputs):
            raise ValueError("verified S3 inputs required")
        inputs.verify()
        if entry_mode not in {"close", "next_open"} or exit_mode not in EXIT_MODES:
            raise ValueError("unapproved S3 cell")
        self.inputs = inputs
        self._bound_bars = inputs._bars.copy(deep=True)
        self._bars_sha = hashlib.sha256(pd.util.hash_pandas_object(self._bound_bars, index=True).values.tobytes()).hexdigest()
        sessions = sorted(self._bound_bars.date.map(_day).unique())
        super().__init__(run_id=run_id, mode="backtest", sessions=sessions, initial_cash=initial_cash,
                         portfolio_id="s3-r1", entry_mode=entry_mode)
        self.exit_mode = exit_mode
        self.ledger = _S3Ledger(run_id, "backtest", "s3-r1", entry_mode)
        self.ledger.identity.update(source_kind=inputs.source_kind, input_binding=inputs.binding_id,
                                    exit_mode=exit_mode, execution_version=VERSION)
        self.canonical = CanonicalExecutionService(
            market_data=ExecutionMarketData(SourceDataAdapter(inputs.source_root)),
            fill_factory=ExecutionFillFactory(_OwnerCosts(), FixedBpsSlippage(0)),
            portfolio=PortfolioEngine(opening_cash=initial_cash))
        self.signal = SignalDeclaration(source=inputs.binding_id, price_semantics=SignalPriceSemantics.RAW_REQUIRED)
        self.journal = []
        self.close_exit_reasons = {}

    def _prices(self, bars):
        self.inputs.verify()
        if bars is not self._bound_bars:
            raise ValueError("external bars cannot enter scoped S3")
        if hashlib.sha256(pd.util.hash_pandas_object(bars, index=True).values.tobytes()).hexdigest() != self._bars_sha:
            raise ValueError("changed verified S3 prices/eligibility")
        p = bars.copy()
        p["date"] = p.date.map(_day)
        return p

    def prepare_session(self, bars, day):
        raise ValueError("external bars/legacy session entry cannot enter scoped S3; use prepare")

    def prepare(self, day):
        self.inputs.verify()
        day = _day(day)
        if not self.inputs.manifest["period"]["start"] <= day <= self.inputs.manifest["period"]["end"]:
            raise ValueError("S3 execution outside E1")
        if day in self.completed or day in self.plans:
            return self.ledger.tables()
        self._prices(self._bound_bars)
        for sid, settlement in list(self.canonical.portfolio.settlements.pending.items()):
            if settlement.due_at <= datetime.fromisoformat(day):
                self.canonical.portfolio.settlements.settle(sid, datetime.fromisoformat(day))
                self.journal.append(dict(kind="settle", id=sid, at=day))
        return super().prepare_session(self._bound_bars, day)

    def _session_bars(self, prices, day):
        today = super()._session_bars(prices, day)
        holding = set(self.positions) | {self.ledger.find("decisions", rid)["stock"] for rid in self.pending_entries}
        return today[[((day, stock) in self.inputs._panel_keys or stock in holding) for stock in today.stock]]

    def _features(self, p, stock, day):
        result = super()._features(p, stock, day)
        history = p[p.stock.eq(stock) & p.date.le(day)].set_index("date").reindex(self.sessions[:self.sessions.index(day)+1])
        history["stock_id"] = stock
        result["rsi13"] = float(_rsi_value(panel=history, lookback=13).iloc[-1])
        return result

    def _close_exit_reason(self, bar, feature):
        reason = super()._close_exit_reason(bar, feature)
        if reason:
            return reason
        return "rsi13_lt50_next_open" if self.exit_mode == "sma20_or_rsi13_lt50" and _finite(feature.get("rsi13")) and feature["rsi13"] < 50 else ""

    def _intent(self, **kwargs):
        row = super()._intent(**kwargs)
        if kwargs["reason"] in {"sma20_next_open", "rsi13_lt50_next_open"}:
            self.close_exit_reasons[row["row_id"]] = kwargs["reason"]
        return row

    def _pending_exit_reason(self, row):
        return self.close_exit_reasons[row["row_id"]]

    def _available_cash(self):
        return self.canonical.portfolio.cash.available_to_commit_cash

    def _execution_reasons(self, decision, bar, previous_close):
        reasons = super()._execution_reasons(decision, bar, previous_close)
        if bar is not None:
            raw = self.canonical.market_data.resolve(ticker=decision["stock"], session_date=bar["date"],
                side="buy", use=PriceUse.ENTRY, field="close" if self.entry_mode == "close" else "open")
            if raw.availability is not ExecutionAvailability.EXECUTABLE:
                reasons.append("canonical_raw:" + raw.reason)
        return reasons

    def _execute(self, event):
        day, side = event["day"], event["side"]
        at = datetime.fromisoformat(day + ("T09:00:00" if event["field"] == "open" else "T13:30:00"))
        kwargs = dict(ticker=event["stock"], session_date=day, side=side)
        if event["use"] == "stop":
            decision = self.canonical.market_data.resolve_stop_fill(**kwargs, stop_price=event["stop_price"])
        else:
            decision = self.canonical.market_data.resolve(**kwargs, use=PriceUse(event["use"]), field=event["field"])
        if decision.availability is not ExecutionAvailability.EXECUTABLE or not _finite(decision.price):
            raise NotExecutableError("S3 RAW gate: " + decision.reason)
        if not math.isclose(decision.price, event["price"], abs_tol=1e-8, rel_tol=0):
            raise ValueError("R1 fill is not the governed RAW price")
        intent = OrderIntent(event["id"]+":intent", event["stock"], side, event["quantity"], at, "S3 fixed R1")
        index = self.sessions.index(day)
        due = self.sessions[index+2] if index+2 < len(self.sessions) else _day(pd.Timestamp(day)+pd.offsets.BDay(2))
        args = dict(intent=intent, signal=self.signal, order_id=event["id"]+":order", fill_id=event["id"]+":fill",
                    submitted_at=at, session_date=day, settlement=SettlementInstruction(event["id"]+":settle", datetime.fromisoformat(due)))
        result = self.canonical.execute_stop(**args, stop_price=event["stop_price"]) if event["use"] == "stop" else self.canonical.execute(**args, use=PriceUse(event["use"]), field=event["field"])
        if not math.isclose(result.fill.fees, event["cost"], abs_tol=1e-8):
            raise ValueError("canonical cost differs from fixed R1 costs")
        return result

    def _charge(self, row, *, price, quantity, day, observed_at):
        self.inputs.verify()
        side = row["side"]
        reason = row["reason"] or ""
        stop = side == "sell" and reason in {"stop_observed", "stop_price_assumption"}
        event = dict(kind="fill", id=row["row_id"], day=day, side=side, stock=row["stock"], quantity=quantity,
                     price=price, cost=FEES.fee(side=side, quantity=quantity, price=price)+price*quantity*SLIPPAGE,
                     field="stop" if stop else "close" if side == "buy" and self.entry_mode == "close" else "open",
                     use="stop" if stop else PriceUse.ENTRY.value if side == "buy" else PriceUse.EXIT.value,
                     stop_price=self.positions[row["stock"]].stop_price if stop else None)
        self._execute(event)
        self.journal.append(event)
        return super()._charge(row, price=price, quantity=quantity, day=day, observed_at=observed_at)

    def reconcile_session(self, day, *, observed_at):
        self.inputs.verify()
        self._prices(self._bound_bars)
        result = super().reconcile_session(day, observed_at=observed_at)
        self._check_accounts()
        return result

    def _check_accounts(self):
        portfolio = self.canonical.portfolio
        if not math.isclose(self.cash, portfolio.cash.projected_cash, abs_tol=1e-6):
            raise ValueError("canonical/R1 cash mismatch")
        own = {sid: p.quantity for sid, p in self.positions.items()}
        canonical = {sid: p.quantity for sid, p in portfolio.positions.positions.items() if p.quantity}
        if own != canonical:
            raise ValueError("canonical/R1 share-count mismatch")
        pending = portfolio.settlements.pending.values()
        receivables = sum(p.amount for p in pending if p.direction.value == "RECEIVABLE")
        payables = sum(p.amount for p in portfolio.settlements.pending.values() if p.direction.value == "PAYABLE")
        if not math.isclose(receivables, portfolio.cash.pending_receivables, abs_tol=1e-6) or not math.isclose(payables, portfolio.cash.pending_payables, abs_tol=1e-6):
            raise ValueError("canonical settlement/cash mismatch")
        for stock, pos in self.positions.items():
            value = portfolio.positions.positions[stock]
            if not math.isclose(value.avg_cost * value.quantity, pos.entry_cash, abs_tol=1e-6):
                raise ValueError("canonical/R1 position cost mismatch")
        actual = {r["row_id"]: r for r in self.ledger.rows["fills"] if r["fill"]}
        journal = {e["id"]: e for e in self.journal if e["kind"] == "fill"}
        if set(actual) != set(journal):
            raise ValueError("canonical/R1 fill journal mismatch")
        for row_id, event in journal.items():
            row = actual[row_id]
            for field, key in [("fill_price", "price"), ("quantity", "quantity"), ("cost", "cost")]:
                if not math.isclose(float(row[field]), event[key], abs_tol=1e-8, rel_tol=0):
                    raise ValueError("canonical/R1 fill economics mismatch")
        if self.completed and not self.frozen:
            day = self.completed[-1]
            equity = self.cash
            for stock, pos in self.positions.items():
                mark = self.canonical.mark(ticker=stock, session_date=day)
                if mark.availability is not ExecutionAvailability.EXECUTABLE:
                    raise NotExecutableError("S3 RAW mark gate: " + mark.reason)
                equity += mark.price * pos.quantity
            if not math.isclose(equity, self.last_reliable_equity, abs_tol=1e-6):
                raise ValueError("canonical/R1 RAW NAV mismatch")

    def validate_tables(self, tables=None):
        self.inputs.verify()
        frames = self.ledger.tables() if tables is None else tables
        if set(frames) != set(S3_SCHEMAS):
            raise ValueError("exactly four S3 ledger tables required")
        for name, frame in frames.items():
            if tuple(frame.columns) != S3_SCHEMAS[name] or frame.duplicated(["run_id", "portfolio_id", "row_id"]).any():
                raise ValueError("S3 ledger schema/key mismatch")
            for key, value in self.ledger.identity.items():
                if not frame[key].eq(value).all():
                    raise ValueError("S3 ledger identity/input binding mismatch")
            if tables is not None and not frame.equals(self.ledger.table(name)):
                raise ValueError("S3 report differs from the canonical run ledger")

    def save(self, path):
        self.validate_tables()
        self._check_accounts()
        state = dict(version=VERSION, input_binding=self.inputs.binding_id, identity=self.ledger.identity,
                     initial_cash=self.initial_cash, sessions=self.sessions, cash=self.cash,
                     tables=self.ledger.rows, positions={s: asdict(p) for s,p in self.positions.items()},
                     plans=self.plans, pending_entries=self.pending_entries, completed=self.completed,
                     frozen=self.frozen, freeze_reason=self.freeze_reason, last_reliable_equity=self.last_reliable_equity,
                     journal=self.journal, close_exit_reasons=self.close_exit_reasons)
        state = _plain(state)
        state["state_digest"] = _digest(state)
        Path(path).write_text(json.dumps(state, allow_nan=False))

    @classmethod
    def load(cls, path, *, inputs):
        state = json.loads(Path(path).read_text())
        digest = state.pop("state_digest", None)
        if digest != _digest(state) or state.get("version") != VERSION or state.get("input_binding") != inputs.binding_id:
            raise ValueError("saved S3 version/integrity/input mismatch")
        identity = state["identity"]
        engine = cls(inputs=inputs, run_id=identity["run_id"], entry_mode=identity["entry_mode"],
                     exit_mode=identity["exit_mode"], initial_cash=state["initial_cash"])
        if identity != engine.ledger.identity or state["sessions"] != engine.sessions:
            raise ValueError("saved S3 source/cell/calendar mismatch")
        for event in state["journal"]:
            if event["kind"] == "fill":
                engine._execute(event)
            elif event["kind"] == "settle":
                at = datetime.fromisoformat(event["at"])
                if engine.canonical.portfolio.settlements.pending[event["id"]].due_at > at:
                    raise ValueError("saved settlement precedes canonical due date")
                engine.canonical.portfolio.settlements.settle(event["id"], at)
            else:
                raise ValueError("unknown canonical journal event")
        engine.close_exit_reasons = state["close_exit_reasons"]
        for reason in engine.close_exit_reasons.values():
            if reason not in {"sma20_next_open", "rsi13_lt50_next_open"}:
                raise ValueError("unknown saved close exit reason")
        engine.ledger.rows = state["tables"]
        engine.positions = {s: Position(**p) for s,p in state["positions"].items()}
        for key in ["cash", "plans", "pending_entries", "completed", "frozen", "freeze_reason", "last_reliable_equity", "journal"]:
            setattr(engine, key, state[key])
        engine.validate_tables()
        engine._check_accounts()
        return engine

    def export_tables(self, directory):
        self.validate_tables()
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        for name, frame in self.ledger.tables().items():
            for col in frame:
                if col in OBJECT_COLUMNS:
                    frame[col] = frame[col].map(lambda v: json.dumps(_plain(v)))
                elif col not in FLOAT_COLUMNS | BOOL_COLUMNS:
                    frame[col] = frame[col].map(lambda v: json.dumps(None if pd.isna(v) else str(v)))
            frame.to_csv(target / f"s3_{name}.csv", index=False)

    def read_tables(self, directory):
        tables = {}
        for name, columns in S3_SCHEMAS.items():
            frame = pd.read_csv(Path(directory)/f"s3_{name}.csv", dtype=str, keep_default_na=False)
            for col in frame:
                if col in OBJECT_COLUMNS:
                    frame[col] = frame[col].map(lambda v: json.loads(v) if v else None)
                elif col in FLOAT_COLUMNS:
                    frame[col] = pd.array(frame[col].replace("", pd.NA), dtype="Float64")
                elif col in BOOL_COLUMNS:
                    frame[col] = pd.array(frame[col].map({"True":True,"False":False}), dtype="boolean")
                else:
                    frame[col] = pd.array(frame[col].map(json.loads), dtype="string")
            tables[name] = frame
        self.validate_tables(tables)
        return tables

    def metrics(self, tables=None):
        self.validate_tables(tables)
        self._check_accounts()
        if self.inputs.fixture:
            raise ValueError("engineering fixtures cannot produce S3 performance")
        if self.frozen:
            raise ValueError("unresolved holding path blocks S3 performance")
        result = _metric_rows(tables if tables is not None else self.ledger.tables(), scope="s3_fixed_E1")
        for key in ["exit_mode", "source_kind", "input_binding", "execution_version"]:
            result[key] = self.ledger.identity[key]
        return result
