"""Scoped S3 wiring. Engineering fixtures cannot produce performance metrics."""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
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
from astraquant.portfolio.reviewed_ca import ReviewedCA
from astraquant.portfolio.normalized_ca import NormalizedCA
from astraquant.portfolio.replay_runner import CanonicalPortfolioReplay
from astraquant.research.terminal_events import load_terminal_event_records
from astraquant.research.epoch_governance import resolve_historical_effect_period
from astraquant.research.technical_components import _rsi_value
from astraquant.research.trading_plan_r1 import (
    BOOL_COLUMNS, COMMISSION, FEES, FLOAT_COLUMNS, OBJECT_COLUMNS, RULE_VERSION,
    SCHEMAS, SLIPPAGE, TAX, Position, SharedLedger, TradingPlanR1, _day, _finite,
    _metric_rows, _plain, _has_corporate_event,
)
from astraquant.validation.accounting_gate import AccountingReadiness

S1_SHA = "2fc9680a3cbb74b15d690edbeb02ed03457b26c74dd682a877b1c6e93f8dc38e"
LIMIT_SHA = "a38f5d63726df1daf4982067b7ce592dc6893f6768af8908e5dae1302b5c0a0a"
SOURCE_REVISION = "3e7c4b6d9cde3b18942710fa977db02f89bffa0d"
LIMIT_REVISION = "67e069e962e365b4f4c09fa466decd66bb70fc82"
VERSION = "s3-canonical-wiring-v4"
EXIT_MODES = {"sma20", "sma20_or_rsi13_lt50"}
S3_SCHEMAS = {name: cols + ("input_binding", "exit_mode", "execution_version")
              for name, cols in SCHEMAS.items()}
_SEAL = object()
DIAGNOSTIC_A_MISSING_SHA = '2135303089df2b975627934956f6b28dc11cc6b2a089ce15503204f66ce19657'
DIAGNOSTIC_B_LIMIT_SHA = 'd0dcc01f3a86b3f53806a4c5e69386f280bdec4a520fc2c7033f0ddbafc5dc5d'
DIAGNOSTIC_B_RESTORED = frozenset('1240 2739 3207 3346 4438 4543 4561 4744 4806 4961 4989 5206 5222 5876 6416 6469 6486 6552 6643 6664 6669'.split())


def _diagnostic_a_exclusions(manifest, root):
    """Bibobo-approved fixed exclusion overlay; never a performance receipt."""
    overlay = manifest.get('diagnostic_overlay')
    if overlay is None:
        return frozenset()
    version = overlay.get('version')
    if (manifest.get('purpose') != 's3_accounting_probe'
            or version not in {'A_exclude_missing_limits_102', 'B_restore_verified_21_exclude_81'}
            or overlay.get('approval_issue_comment') != 6072210571
            or overlay.get('missing_keys_sha256') != DIAGNOSTIC_A_MISSING_SHA):
        raise ValueError('unapproved diagnostic exclusion overlay')
    path = _inside(root, overlay['missing_keys_path'])
    if _hash(path) != DIAGNOSTIC_A_MISSING_SHA:
        raise ValueError('changed approved missing-limit exclusion source')
    missing = pd.read_csv(path, dtype={'stock': str})
    stocks = frozenset(missing.stock)
    if len(missing) != 4806 or len(stocks) != 102:
        raise ValueError('changed approved 102-stock exclusion list')
    excluded = stocks
    if version == 'B_restore_verified_21_exclude_81':
        entries = [e for e in manifest.get('files', []) if e['role'] == 'supplement_2016_2018']
        if (overlay.get('restoration_review_comment') != 6072459378
                or overlay.get('restored_stocks') != sorted(DIAGNOSTIC_B_RESTORED)
                or len(entries) != 1 or entries[0]['sha256'] != DIAGNOSTIC_B_LIMIT_SHA
                or _hash(_inside(root, entries[0]['path'])) != DIAGNOSTIC_B_LIMIT_SHA):
            raise ValueError('changed reviewed B restoration/limit binding')
        excluded = stocks - DIAGNOSTIC_B_RESTORED
    elif any(e['role']=='supplement_2016_2018' for e in manifest.get('files', [])):
        raise ValueError('B supplement cannot alter fixed A inputs')
    if sorted(excluded) != overlay.get('excluded_stocks'):
        raise ValueError('changed approved exclusion list')
    return excluded


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _atomic_write(path, data):
    """Publish only a complete fsynced generation; keep the prior checkpoint on failure."""
    import tempfile
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=target.name + '.', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _day_labels(values):
    # Convert each distinct canonical date once; preserve the original _day semantics.
    return values.map({pd.Timestamp(value): _day(value) for value in values.unique()})


def _inside(root, path):
    target = (root / path).resolve()
    target.relative_to(root)
    return target


def write_source_manifest(root, *, source_root, panel, supplement, output, terminal_events, reviewed_ca_overlay=None):
    """Inventory the existing accepted inputs; never create an approval receipt."""
    root = Path(root).resolve()
    source = _inside(root, source_root)
    paths = [(source / "raw" / f"prices_raw_{year}.parquet", "raw")
             for year in range(2015, 2022)]
    paths += [(source / "reference" / "tradability.parquet", "tradability"),
              (source / "reference" / "corporate_actions_official.csv", "events"),
              (source / "fundamentals" / "dividend.parquet", "dividend"),
              (_inside(root,terminal_events), "terminal")]
    paths += [(p, "limits") for p in sorted((source / "reference").glob("price_limit_*.parquet"))
              if any(str(year) in p.name for year in range(2015, 2019))]
    if len([p for p, role in paths if role == "limits"]) != 4:
        raise ValueError("four existing 2015–2018 limit files required")
    paths += [(_inside(root, panel), "panel"), (_inside(root, supplement), "supplement")]
    if reviewed_ca_overlay is not None:
        overlay_path = _inside(root, reviewed_ca_overlay)
        ReviewedCA(overlay_path, source / "reference/corporate_actions_official.csv")
        paths.append((overlay_path, "reviewed_ca_overlay"))
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


def _frame_digest(frame):
    return _digest(dict(columns=list(frame.columns), dtypes=[str(t) for t in frame.dtypes],
        values=hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()))


@dataclass(frozen=True, slots=True)
class _InputSnapshot:
    input_binding: str
    bars_sha: str
    panel_keys: frozenset
    ca_sha: str


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
    def open_accounting_probe(cls, root, manifest, receipt):
        """Real frozen-export evidence only; never unlocks strategy performance."""
        return cls._open(root, manifest, receipt, fixture=False, probe=True)

    @classmethod
    def _open(cls, root, manifest, receipt, *, fixture, probe=False):
        self = object.__new__(cls)
        self.root = Path(root).resolve()
        self.manifest_path = _inside(self.root, manifest)
        self.receipt_path = _inside(self.root, receipt)
        self.manifest = json.loads(self.manifest_path.read_text())
        self.fixture, self.probe = fixture, probe
        self._declared_route = (fixture, probe)
        self.source_kind = "s3_engineering_fixture" if fixture else "s3_real_accounting_probe" if probe else "s3_real"
        m = self.manifest
        expected_purpose = "s3_engineering_fixture" if fixture else "s3_accounting_probe" if probe else "s3_source"
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
        self._verify_files()
        overlays = [e for e in self.inventory if e["role"] == "reviewed_ca_overlay"]
        if len(overlays) > 1:
            raise ValueError("duplicate reviewed corporate-action overlay")
        self.reviewed_ca = (ReviewedCA(self.role("reviewed_ca_overlay"), self.role("events"), engineering_fixture=fixture)
                            if overlays else None)
        self._declared_ca = self.reviewed_ca
        self.normalized_ca = NormalizedCA(self.role('dividend')) if any(e['role']=='dividend' for e in self.inventory) else None
        self._declared_normalized_ca = self.normalized_ca
        self.terminal_records = (tuple(load_terminal_event_records(self.role('terminal')))
                                 if any(e['role']=='terminal' for e in self.inventory) else ())
        self._terminal_digest = _digest(json.loads(json.dumps([asdict(t) for t in self.terminal_records],default=str)))
        self._bars = self._read_bars()
        self._snapshot = _InputSnapshot(self.binding_id, _frame_digest(self._bars), self._panel_keys, self._ca_digest())
        self.verify()
        return self

    def role(self, name):
        entries = [e for e in self.inventory if e["role"] == name]
        if len(entries) != 1:
            raise ValueError(f"exactly one {name} input required")
        return _inside(self.root, entries[0]["path"])

    def _ca_digest(self):
        return _digest(json.loads(json.dumps(dict(
            normalized=[] if self.normalized_ca is None else [asdict(a) for a in self.normalized_ca.actions],
            terminal=[asdict(t) for t in self.terminal_records],
            official=[(d,s,sorted(types)) for (d,s),types in sorted(self.official_event_types.items())]),default=str)))

    def verify(self):
        self._verify_files()
        if self.reviewed_ca is not self._declared_ca:
            raise ValueError("changed bound corporate-action implementation")
        if self.reviewed_ca is not None:
            self.reviewed_ca.verify()
        if self.normalized_ca is not self._declared_normalized_ca:
            raise ValueError('changed bound normalized corporate-action implementation')
        if self.normalized_ca is not None:
            self.normalized_ca.verify()
        if _digest(json.loads(json.dumps([asdict(t) for t in self.terminal_records],default=str))) != self._terminal_digest:
            raise ValueError('changed bound terminal evidence')
        if (self._snapshot.input_binding != self.binding_id
                or _frame_digest(self._bars) != self._snapshot.bars_sha
                or self._panel_keys != self._snapshot.panel_keys
                or self._ca_digest() != self._snapshot.ca_sha):
            raise ValueError("changed verified S3 input snapshot/keys")

    def _verify_files(self):
        if getattr(self, "_seal", None) is not _SEAL:
            raise ValueError("unverified S3 binding")
        if (_digest(self.manifest) != self.input_digest or self.inventory != self.manifest["files"]
                or self.binding_id != _digest(dict(input=self.input_digest, receipt=self._receipt_sha))
                or (self.fixture, self.probe) != self._declared_route
                or self.manifest["purpose"] != ("s3_engineering_fixture" if self.fixture else "s3_accounting_probe" if self.probe else "s3_source")
                or self.source_kind != ("s3_engineering_fixture" if self.fixture else "s3_real_accounting_probe" if self.probe else "s3_real")):
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
            if entry["role"] not in {"raw", "tradability", "events", "limits", "panel", "supplement", "supplement_2016_2018", "reviewed_ca_overlay", "dividend", "terminal", "export_manifest", "export_archive"}:
                raise ValueError("unknown S3 input role")
            if entry['role']=='supplement_2016_2018' and (not self.probe or not self.manifest.get('diagnostic_overlay')):
                raise ValueError('restored limits require reviewed B diagnostic binding')
            if entry["role"] in {"raw", "limits"}:
                directory = "raw" if entry["role"] == "raw" else "reference"
                if _inside(self.root, entry["path"]) != (self.source_root / directory / Path(entry["path"]).name).resolve():
                    raise ValueError("unbound canonical RAW/limit path")
        if not self.fixture:
            if _hash(self.role("panel")) != S1_SHA or _hash(self.role("supplement")) != LIMIT_SHA:
                raise ValueError("wrong accepted S1/limit bytes")
            if self.role('dividend') != (self.source_root/'fundamentals/dividend.parquet').resolve():
                raise ValueError('inventory does not bind canonical dividend path')
            if _hash(self.role('terminal')) != '02d30cf5dc079a18b7ba7888568f1607e7152136aeca02b7ee06ada5ead58a5d':
                raise ValueError('wrong frozen terminal evidence bytes')
            if self.probe:
                self._verify_export_provenance()
            else:
                revision = subprocess.check_output(["git", "-C", str(self.source_root), "rev-parse", "HEAD"], text=True).strip()
                if revision != SOURCE_REVISION:
                    raise ValueError("wrong immutable RAW source checkout")
                top = Path(subprocess.check_output(["git", "-C", str(self.source_root), "rev-parse", "--show-toplevel"], text=True).strip())
                paths = [str(_inside(self.root, e["path"]).relative_to(top)) for e in self.inventory
                         if e["role"] in {"raw", "tradability", "events", "limits", "dividend"}]
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
        if self.probe:
            if self.readiness.passed or receipt.get('scope') != 'bounded_real_accounting_evidence_only':
                raise ValueError('probe receipt cannot claim full accounting clearance')
            scope = self.manifest.get('probe_sessions', [])
            excluded = _diagnostic_a_exclusions(self.manifest, self.root)
            if (not 1 <= len(scope) <= (2000 if excluded else 31) or scope != sorted(set(scope))
                    or any(not self.manifest['period']['start'] <= d <= self.manifest['period']['end'] for d in scope)):
                raise ValueError('bounded accounting probe sessions required')
        else:
            self.readiness.require_performance_unlocked()

    def _verify_export_provenance(self):
        # Same immutable bytes already independently accepted as the original ZIP.
        # Production still requires the pristine Git checkout and unlocked gate.
        if (_hash(self.role('export_manifest')) != 'e18b21dab018c04ae5f6d05979c9d601b035bde45338ed40c42544be9337a26c'
                or _hash(self.role('export_archive')) != '79a45e098fb55f9c358c2c8a67e58365d07277b5ba706e2768d1842d11902867'):
            raise ValueError('unreviewed frozen accounting export')
        original = json.loads(self.role('export_manifest').read_text())
        role_map = {'raw':'raw','limits':'limits','tradability':'tradability','events':'official_events','dividend':'dividend'}
        for entry in self.inventory:
            if entry['role'] in role_map:
                relative = str(_inside(self.root, entry['path']).relative_to(self.source_root))
                source = [e for e in original['files'] if e['role']==role_map[entry['role']] and e['source_path']==relative]
                if len(source)!=1 or entry['sha256']!=source[0]['sha256']:
                    raise ValueError('probe inventory differs from accepted source export')
        actual = {(e['role'],str(_inside(self.root,e['path']).relative_to(self.source_root)))
                  for e in self.inventory if e['role'] in role_map}
        expected = {(role, e['source_path']) for role, source_role in role_map.items()
                    for e in original['files'] if e['role']==source_role}
        if actual != expected:
            raise ValueError('incomplete frozen accounting probe inventory')

    def _read_bars(self):
        panel = pd.read_parquet(self.role("panel")).reset_index()
        if {"date", "stock", "eligibility", "rs", "available_date"} - set(panel):
            raise ValueError("S1 panel keys/flags absent")
        panel["date"] = pd.to_datetime(panel.date).dt.normalize()
        panel["stock"] = panel.stock.astype(str)
        excluded = _diagnostic_a_exclusions(self.manifest, self.root)
        self._panel_keys = frozenset(zip(_day_labels(panel.date), panel.stock))
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
                            if e["role"] in {"limits", "supplement", "supplement_2016_2018"}], ignore_index=True)
        limits["date"] = pd.to_datetime(limits.date).dt.normalize()
        limits["stock_id"] = limits.stock_id.astype(str)
        if limits.duplicated(["date", "stock_id"]).any():
            raise ValueError("duplicate limit keys")
        limit_panel = panel[_day_labels(panel.date).isin(self.manifest['probe_sessions'])] if self.probe else panel
        if excluded:
            limit_panel = limit_panel[~limit_panel.stock.isin(excluded)]
        needed = pd.MultiIndex.from_frame(limit_panel[["date", "stock"]])
        if len(needed.difference(pd.MultiIndex.from_frame(limits[["date", "stock_id"]]))):
            raise ValueError("S1 keys lack exact limits")
        raw = raw.rename(columns={"stock_id": "stock", "max": "high", "min": "low", "Trading_Volume": "volume"})
        bars = raw.merge(panel[["date", "stock", "eligibility", "rs", "available_date"]], on=["date", "stock"], how="left", validate="one_to_one")
        bars = bars.merge(limits[["date", "stock_id", "limit_up", "limit_down"]].rename(columns={
            "stock_id": "stock", "limit_up": "limit_up_price", "limit_down": "limit_down_price"}), on=["date", "stock"], how="left", validate="one_to_one")
        bars["eligible"] = bars.eligibility.fillna(False).astype(bool)
        if excluded:
            # Preserve original S1/RAW bytes and market RS; execute only the approved subpopulation.
            bars = bars[~bars.stock.isin(excluded)].copy()
            expected_sessions = sorted(set(_day_labels(bars.loc[bars.date.between(start,end),'date'])))
            if expected_sessions != self.manifest['probe_sessions']:
                raise ValueError('diagnostic A requires the complete fixed E1 calendar')
        if (pd.to_datetime(bars.loc[bars.eligible, "available_date"]) > bars.loc[bars.eligible, "date"]).any():
            raise ValueError("future S1 availability")
        bars["available_date"] = bars.available_date.where(bars.available_date.notna(), bars.date)
        bars["source_kind"], bars["source"] = self.source_kind, self.binding_id
        events = pd.read_csv(self.role("events"), dtype={"stock_id": str})
        self.official_event_types = {(_day(d),s):frozenset(g.event_type)
            for (d,s),g in events.groupby(['event_date','stock_id'])}
        event_keys = set(zip(pd.to_datetime(events.event_date).map(_day), events.stock_id))
        if self.normalized_ca is not None:
            event_keys |= {(str(a.effective_date),a.ticker) for a in self.normalized_ca.actions}
        bars["corporate_action"] = ["source_event_requires_accounting" if (d, s) in event_keys else None
                                    for d, s in zip(_day_labels(bars.date), bars.stock)]
        for terminal in self.terminal_records:
            cutoff = terminal.suspension_from or terminal.effective_date
            if cutoff is not None:
                bars.loc[bars.stock.eq(terminal.ticker) & bars.date.ge(pd.Timestamp(cutoff)),
                         'corporate_action'] = 'terminal_terms_unverified'
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
        # Share verified buffers, while retaining both full input and execution hashes.
        # A mutation through either view is still rejected before execution.
        self._bound_bars = inputs._bars.copy(deep=False)
        self._bars_sha = inputs._snapshot.bars_sha
        sessions = sorted(_day(value) for value in self._bound_bars.date.unique())
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
        self.canonical_replay = CanonicalPortfolioReplay(execution=self.canonical,portfolio=self.canonical.portfolio)
        self.journal = []
        self.close_exit_reasons = {}
        self.applied_ca_keys = set()
        self._declared_identity = deepcopy(self.ledger.identity)
        self._declared_cell = (entry_mode, exit_mode)
        self._declared_sessions = tuple(self.sessions)

    def _verify_run(self):
        self.inputs.verify()
        if ((self.entry_mode, self.exit_mode) != self._declared_cell
                or self.ledger.identity != self._declared_identity
                or self.inputs.binding_id != self._declared_identity["input_binding"]
                or tuple(self.sessions) != self._declared_sessions):
            raise ValueError("changed S3 execution cell/identity/calendar")
        if _frame_digest(self._bound_bars) != self._bars_sha or self._bars_sha != self.inputs._snapshot.bars_sha:
            raise ValueError("changed verified S3 prices/eligibility")

    def _prices(self, bars):
        self._verify_run()
        if bars is not self._bound_bars:
            raise ValueError("external bars cannot enter scoped S3")
        p = bars.copy(deep=False)
        p["date"] = _day_labels(p.date)
        # Keep every market row; locate one stock without rescanning the market.
        p = p.set_index(['stock','date'],drop=False)
        p.index.names = ['_stock_feature_key','_date_feature_key']
        return p

    def prepare_session(self, bars, day):
        raise ValueError("external bars/legacy session entry cannot enter scoped S3; use prepare")

    def prepare(self, day):
        self._verify_run()
        day = _day(day)
        if self.inputs.probe and day not in self.inputs.manifest['probe_sessions']:
            raise ValueError('session outside bounded real accounting probe')
        if not self.inputs.manifest["period"]["start"] <= day <= self.inputs.manifest["period"]["end"]:
            raise ValueError("S3 execution outside E1")
        if day in self.completed or day in self.plans:
            return self.ledger.tables()
        self._verify_run()
        for sid, settlement in list(self.canonical.portfolio.settlements.pending.items()):
            if settlement.due_at <= datetime.fromisoformat(day):
                self.canonical.portfolio.settlements.settle(sid, datetime.fromisoformat(day))
                self.journal.append(dict(kind="settle", id=sid, at=day))
        if self.inputs.reviewed_ca is not None:
            self.journal.extend(self.inputs.reviewed_ca.pay_due(portfolio=self.canonical.portfolio,day=day))
        if self.inputs.normalized_ca is not None:
            self.journal.extend(self.inputs.normalized_ca.pay_due(replay=self.canonical_replay,day=day))
        for terminal in self.inputs.terminal_records:
            cutoff = terminal.suspension_from or terminal.effective_date
            if cutoff is None or str(cutoff) > day:
                continue
            observation = self._terminal_observation(terminal,day)
            self.journal.append(observation)
            pos = self.positions.get(terminal.ticker)
            if pos is not None and not pos.truncated:
                self._truncate(pos,day,'unresolved_terminal_event',observation)
        for stock,pos in list(self.positions.items()):
            if self.frozen or pos.truncated or (day,stock) in self.applied_ca_keys:
                continue
            normalized = self.inputs.normalized_ca
            has_normalized = normalized is not None and any(
                a.ticker==stock and str(a.effective_date)==day for a in normalized.actions)
            if (day,stock) not in self.inputs.official_event_types and not has_normalized:
                continue
            try:
                records = self._apply_bound_ca(stock,day,pos.stop_price)
            except ValueError as error:
                observation = dict(kind='unresolved_ca',ticker=stock,day=day,trade_id=pos.trade_id,
                    old_quantity=pos.quantity,old_stop=pos.stop_price,reason=str(error),binding=self.inputs.binding_id)
                self.journal.append(observation)
                self._truncate(pos,day,'unresolved_ca',observation)
                continue
            for record in records:
                record['trade_id'] = pos.trade_id
                pos.quantity = record['new_quantity']
                pos.stop_price = record['new_stop']
                self.cash += record['cash_receivable']
                self.journal.append(record)
            self.applied_ca_keys.add((day,stock))
        return super().prepare_session(self._bound_bars, day)

    def _apply_bound_ca(self,ticker,day,stop_price):
        normalized = self.inputs.normalized_ca
        has_normalized = normalized is not None and any(
            a.ticker==ticker and str(a.effective_date)==day for a in normalized.actions)
        official = self.inputs.official_event_types.get((day,ticker),frozenset())
        if has_normalized:
            if official - {'ex_right_dividend'}:
                raise ValueError('overlapping official and normalized rights require resolved evidence')
            return normalized.apply(replay=self.canonical_replay,ticker=ticker,day=day,stop_price=stop_price)
        if self.inputs.reviewed_ca is not None:
            return [self.inputs.reviewed_ca.apply(portfolio=self.canonical.portfolio,
                        ticker=ticker,day=day,stop_price=stop_price)]
        raise ValueError('corporate action lacks complete bound source evidence')

    def _holding_trade_id(self,ticker):
        position = self.canonical.portfolio.positions.positions.get(ticker)
        if position is None or not position.quantity:
            return None
        buy = next(fill for fill in reversed(position.fills) if fill.side=='buy')
        row_id = buy.fill_id.removesuffix(':fill')
        return next(r['trade_id'] for r in self.ledger.rows['fills'] if r['row_id']==row_id)

    def _terminal_observation(self,terminal,day):
        position = self.canonical.portfolio.positions.positions.get(terminal.ticker)
        return dict(kind='terminal_observation',ticker=terminal.ticker,day=day,
            candidate_boundary=str(terminal.suspension_from or terminal.effective_date),
            source_status='UNKNOWN_FINAL_TERMS',binding=self.inputs.binding_id,
            terms_sha=_hash(self.inputs.role('terminal')),
            held_quantity=0 if position is None else position.quantity,
            trade_id=self._holding_trade_id(terminal.ticker))

    def _session_bars(self, prices, day):
        today = super()._session_bars(prices, day)
        today = today.copy()
        for stock in today.stock:
            if (day, stock) in self.applied_ca_keys:
                today.loc[today.stock.eq(stock), "corporate_action"] = None
        holding = set(self.positions) | {self.ledger.find("decisions", rid)["stock"] for rid in self.pending_entries}
        return today[[((day, stock) in self.inputs._panel_keys or stock in holding) for stock in today.stock]]

    def _features(self, p, stock, day):
        stock_prices = (p.xs(stock,level='_stock_feature_key')
                        if '_stock_feature_key' in p.index.names else p[p.stock.eq(stock)])
        result = super()._features(stock_prices, stock, day)
        history = stock_prices[stock_prices.date.le(day)].set_index("date").reindex(self.sessions[:self.sessions.index(day)+1])
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
        self._verify_run()
        day, side = event["day"], event["side"]
        if self.inputs.probe and day not in self.inputs.manifest['probe_sessions']:
            raise ValueError('fill outside bounded real accounting probe')
        if not self.inputs.manifest['period']['start']<=day<=self.inputs.manifest['period']['end']:
            raise ValueError('S3 fill outside declared E1')
        barred=self._execution_bar(event['stock'], day)
        if (len(barred) and _has_corporate_event(barred.iloc[0].corporate_action)
                and (day,event['stock']) not in self.applied_ca_keys):
            raise NotExecutableError('S3 source event requires resolved accounting')
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
        if index+2>=len(self.sessions) and not self.inputs.fixture:
            raise NotExecutableError('S3 source calendar lacks T+2 settlement sessions')
        due = self.sessions[index+2] if index+2 < len(self.sessions) else _day(pd.Timestamp(day)+pd.offsets.BDay(2))
        args = dict(intent=intent, signal=self.signal, order_id=event["id"]+":order", fill_id=event["id"]+":fill",
                    submitted_at=at, session_date=day, settlement=SettlementInstruction(event["id"]+":settle", datetime.fromisoformat(due)))
        result = self.canonical.execute_stop(**args, stop_price=event["stop_price"]) if event["use"] == "stop" else self.canonical.execute(**args, use=PriceUse(event["use"]), field=event["field"])
        if not math.isclose(result.fill.fees, event["cost"], abs_tol=1e-8):
            raise ValueError("canonical cost differs from fixed R1 costs")
        return result

    def _execution_bar(self, stock, day):
        return self._bound_bars[self._bound_bars.stock.eq(stock) & self._bound_bars.date.map(_day).eq(day)]

    def _charge(self, row, *, price, quantity, day, observed_at):
        self._verify_run()
        side = row["side"]
        reason = row["reason"] or ""
        stop = side == "sell" and reason in {"stop_observed", "stop_price_assumption"}
        event = dict(kind="fill", id=row["row_id"], day=day, side=side, stock=row["stock"], quantity=quantity,
                     price=price, cost=FEES.fee(side=side, quantity=quantity, price=price)+price*quantity*SLIPPAGE,
                     field="stop" if stop else "close" if side == "buy" and self.entry_mode == "close" else "open",
                     use="stop" if stop else PriceUse.ENTRY.value if side == "buy" else PriceUse.EXIT.value,
                     stop_price=self.positions[row["stock"]].stop_price if stop else None)
        try:
            self._execute(event)
        except NotExecutableError as error:
            self.journal.append(dict(event,kind='execution_blocked',reason=str(error)))
            row.update(status='BLOCKED',reason=str(error))
            pos=self.positions.get(row['stock'])
            if pos is not None:
                self._truncate(pos,day,'unresolved_execution',dict(reason=str(error)))
            else:
                self.frozen,self.freeze_reason=True,'unresolved_execution:'+str(error)
            raise
        self.journal.append(event)
        return super()._charge(row, price=price, quantity=quantity, day=day, observed_at=observed_at)

    def reconcile_session(self, day, *, observed_at):
        self._verify_run()
        self._verify_run()
        result = super().reconcile_session(day, observed_at=observed_at)
        self._check_accounts()
        return result

    def _trade_economics(self, trade_id):
        fills = [r for r in self.ledger.rows["fills"] if r["fill"] and r["trade_id"] == trade_id]
        buys = [r for r in fills if r["side"] == "buy"]
        sells = [r for r in fills if r["side"] == "sell"]
        if len(buys) != 1 or len(sells) != 1:
            raise ValueError("closed trade requires one canonical entry and exit")
        journal = {e["id"]: e for e in self.journal if e["kind"] == "fill"}
        buy, sell = (journal[r["row_id"]] for r in (buys[0], sells[0]))
        entry = buy["quantity"] * buy["price"] + buy["cost"]
        proceeds = sell["quantity"] * sell["price"] - sell["cost"]
        ca = self.canonical.portfolio.corporate_actions
        entitlements = {**ca.completed_cash_entitlements, **ca.cash_entitlement_receivables,
                        **ca.completed_dividends, **ca.dividend_receivables}
        events = [r["event_id"] for r in self.journal if r["kind"] in {"reviewed_ca","normalized_ca"} and r["trade_id"] == trade_id]
        rights = sum(entitlements[event_id].amount for event_id in events if event_id in entitlements)
        pnl = proceeds + rights - entry
        return dict(pnl=pnl, net_return=pnl / entry, cash_entitlement=rights, events=events)

    def _sell(self, pos, bar, day, observed_at, *, open_only=False):
        super()._sell(pos, bar, day, observed_at, open_only=open_only)
        if pos.stock in self.positions:
            return
        economics = self._trade_economics(pos.trade_id)
        row = next(r for r in self.ledger.rows["fills"] if r["trade_id"] == pos.trade_id and r["side"] == "sell" and r["fill"])
        row.update(pnl=economics["pnl"], net_return=economics["net_return"])
        if economics["events"]:
            row["corporate_action"] = dict(cash_entitlement=economics["cash_entitlement"], events=economics["events"])

    def _check_accounts(self):
        portfolio = self.canonical.portfolio
        from itertools import groupby
        from decimal import Decimal
        ca_records = [r for r in self.journal if r['kind'] in {'reviewed_ca','normalized_ca'}]
        if len({r['event_id'] for r in ca_records}) != len(ca_records):
            raise ValueError('duplicate corporate-action journal')
        ca = portfolio.corporate_actions
        entitlements = {**ca.completed_cash_entitlements,**ca.cash_entitlement_receivables,
                        **ca.completed_dividends,**ca.dividend_receivables}
        if set(entitlements) != {r['event_id'] for r in ca_records if r['cash_receivable']>0}:
            raise ValueError('corporate-action entitlement journal mismatch')
        mutations = {r['event_id'] for r in ca_records if r['new_quantity']!=r['old_quantity']}
        if set(ca.share_mutations)!=mutations or portfolio.positions.applied_share_mutation_ids!=mutations:
            raise ValueError('corporate-action share mutation journal mismatch')
        for trade_id in {r['trade_id'] for r in ca_records}:
            records = [r for r in ca_records if r['trade_id']==trade_id]
            decisions = [r for r in self.ledger.rows['decisions'] if r['trade_id']==trade_id]
            fills = [r for r in self.ledger.rows['fills'] if r['fill'] and r['trade_id']==trade_id]
            buys = [r for r in fills if r['side']=='buy']
            sells = [r for r in fills if r['side']=='sell']
            if len(decisions)!=1 or len(buys)!=1:
                raise ValueError('corporate-action holding provenance mismatch')
            quantity, stop = float(buys[0]['quantity']), decisions[0]['stop_price']
            for (day,kind),bundle in groupby(records,key=lambda r:(r['day'],r['kind'])):
                bundle=list(bundle);ticker=decisions[0]['stock']
                if buys[0]['fill_date']>=day or any(r['fill_date']<day for r in sells):
                    raise ValueError('corporate-action rights belong to different holding')
                if kind=='normalized_ca':
                    if self.inputs.normalized_ca is None:
                        raise ValueError('normalized journal lacks bound source')
                    expected=self.inputs.normalized_ca.expected_records(ticker=ticker,day=day,
                        quantity=quantity,stop_price=stop)
                else:
                    if self.inputs.reviewed_ca is None:
                        raise ValueError('reviewed journal lacks bound overlay')
                    action=self.inputs.reviewed_ca.resolve(ticker,day);event=action.event
                    expected=[dict(kind='reviewed_ca',ticker=ticker,day=day,binding=action.binding,
                        old_quantity=quantity,new_quantity=float(Decimal(str(quantity))*Decimal(str(event.share_multiplier))),
                        cash_receivable=quantity*event.cash_per_share,old_stop=stop,
                        new_stop=(stop-event.cash_per_share)/event.share_multiplier,event_id=event.event_id)]
                expected=[dict(r,trade_id=trade_id) for r in expected]
                if bundle != expected:
                    raise ValueError('corporate-action stop/input/economics provenance mismatch')
                for record in bundle:
                    if record['cash_receivable']>0:
                        entitlement=entitlements[record['event_id']]
                        if (entitlement.ticker!=ticker or not math.isclose(entitlement.amount,record['cash_receivable'],abs_tol=1e-8)):
                            raise ValueError('corporate-action entitlement economics mismatch')
                    quantity,stop=record['new_quantity'],record['new_stop']
        prepared=set(self.completed)|set(self.plans)
        observations=[r for r in self.journal if r['kind']=='terminal_observation']
        expected_keys={(day,t.ticker) for day in prepared for t in self.inputs.terminal_records
                       if (t.suspension_from or t.effective_date) is not None
                       and str(t.suspension_from or t.effective_date)<=day}
        if (len(observations)!=len(expected_keys)
                or {(r['day'],r['ticker']) for r in observations}!=expected_keys):
            raise ValueError('terminal coverage observation mismatch')
        for record in observations:
            if record['binding']!=self.inputs.binding_id or record['terms_sha']!=_hash(self.inputs.role('terminal')):
                raise ValueError('terminal observation source mismatch')
            if record['held_quantity']>0:
                truncated=[r for r in self.ledger.rows['fills'] if r['truncated']
                           and r['trade_id']==record['trade_id'] and r['reason']=='unresolved_terminal_event']
                if not self.frozen or not truncated:
                    raise ValueError('unresolved terminal holding must remain incomplete')
        quantities,owners={},{}
        fill_rows={r['row_id']:r for r in self.ledger.rows['fills'] if r['fill']}
        for event in self.journal:
            if event['kind']=='fill':
                stock=event['stock']
                quantities[stock]=quantities.get(stock,0)+(event['quantity'] if event['side']=='buy' else -event['quantity'])
                if event['side']=='buy': owners[stock]=fill_rows[event['id']]['trade_id']
                if quantities[stock]==0: owners.pop(stock,None)
            elif event['kind'] in {'reviewed_ca','normalized_ca'}:
                quantities[event['ticker']]=event['new_quantity']
            elif event['kind']=='terminal_observation':
                terminal=next(t for t in self.inputs.terminal_records if t.ticker==event['ticker'])
                if (event['held_quantity']!=quantities.get(event['ticker'],0)
                        or event['trade_id']!=owners.get(event['ticker'])
                        or event['candidate_boundary']!=str(terminal.suspension_from or terminal.effective_date)
                        or event['source_status']!='UNKNOWN_FINAL_TERMS'):
                    raise ValueError('terminal historical exposure provenance mismatch')
        for record in [r for r in self.journal if r['kind']=='unresolved_ca']:
            if not self.frozen or record['binding']!=self.inputs.binding_id:
                raise ValueError('unresolved corporate-action holding must remain incomplete')
            decision=next(r for r in self.ledger.rows['decisions'] if r['trade_id']==record['trade_id'])
            earlier=[r for r in ca_records if r['trade_id']==record['trade_id'] and r['day']<record['day']]
            stop=earlier[-1]['new_stop'] if earlier else decision['stop_price']
            if record['old_stop']!=stop:
                raise ValueError('unresolved corporate-action stop provenance mismatch')
        if any(r['kind']=='execution_blocked' for r in self.journal) and not self.frozen:
            raise ValueError('blocked execution must remain incomplete')
        paid={**ca.completed_cash_entitlements,**ca.completed_dividends}
        payments=[r for r in self.journal if r['kind'] in {'reviewed_ca_payment','normalized_ca_payment'}]
        if len(payments)!=len(paid) or {r['event_id'] for r in payments}!=set(paid):
            raise ValueError('corporate-action payment journal mismatch')
        for record in payments:
            right=paid[record['event_id']]
            if right.amount!=record['amount'] or right.paid_at!=datetime.fromisoformat(record['day']):
                raise ValueError('corporate-action payment economics mismatch')
        if prepared:
            at=datetime.fromisoformat(max(prepared))
            if (any(r.due_at<=at for r in portfolio.settlements.pending.values())
                    or any(r.payment_at is not None and r.payment_at<=at
                           for r in list(ca.dividend_receivables.values())+list(ca.cash_entitlement_receivables.values()))):
                raise ValueError('due settlement/payment missing from canonical replay')
        if not math.isclose(self.cash, portfolio.cash.projected_cash, abs_tol=1e-6):
            raise ValueError("canonical/R1 cash mismatch")
        own = {sid: p.quantity for sid, p in self.positions.items()}
        canonical = {sid: p.quantity for sid, p in portfolio.positions.positions.items() if p.quantity}
        if own != canonical:
            raise ValueError("canonical/R1 share-count mismatch")
        pending = portfolio.settlements.pending.values()
        receivables = sum(p.amount for p in pending if p.direction.value == "RECEIVABLE")
        receivables += sum(r.amount for r in portfolio.corporate_actions.cash_entitlement_receivables.values())
        receivables += sum(r.amount for r in portfolio.corporate_actions.dividend_receivables.values())
        payables = sum(p.amount for p in portfolio.settlements.pending.values() if p.direction.value == "PAYABLE")
        if not math.isclose(receivables, portfolio.cash.pending_receivables, abs_tol=1e-6) or not math.isclose(payables, portfolio.cash.pending_payables, abs_tol=1e-6):
            raise ValueError("canonical settlement/cash mismatch")
        for stock, pos in self.positions.items():
            value = portfolio.positions.positions[stock]
            if not math.isclose(value.avg_cost * value.quantity, pos.entry_cash, abs_tol=1e-6):
                raise ValueError("canonical/R1 position cost mismatch")
            records = [r for r in self.journal if r["kind"] in {"reviewed_ca","normalized_ca"} and r["trade_id"] == pos.trade_id]
            if records and not math.isclose(pos.stop_price, records[-1]["new_stop"], abs_tol=1e-8):
                raise ValueError("canonical/R1 equivalent stop mismatch")
        actual = {r["row_id"]: r for r in self.ledger.rows["fills"] if r["fill"]}
        journal = {e["id"]: e for e in self.journal if e["kind"] == "fill"}
        if set(actual) != set(journal):
            raise ValueError("canonical/R1 fill journal mismatch")
        for row_id, event in journal.items():
            row = actual[row_id]
            for field, key in [("fill_price", "price"), ("quantity", "quantity"), ("cost", "cost")]:
                if not math.isclose(float(row[field]), event[key], abs_tol=1e-8, rel_tol=0):
                    raise ValueError("canonical/R1 fill economics mismatch")
            gross = event["price"] * event["quantity"]
            expected_cash = -gross-event["cost"] if event["side"] == "buy" else gross-event["cost"]
            if not _finite(row["cash_flow"]) or not math.isclose(float(row["cash_flow"]), expected_cash, abs_tol=1e-8, rel_tol=0):
                raise ValueError("canonical/R1 cash_flow economics mismatch")
            if row["side"] == "sell":
                economics = self._trade_economics(row["trade_id"])
                for key in ("pnl", "net_return"):
                    if not _finite(row[key]) or not math.isclose(float(row[key]), economics[key], abs_tol=1e-8, rel_tol=0):
                        raise ValueError(f"canonical/R1 closed {key} economics mismatch")
                if economics["events"] and row["corporate_action"] != dict(cash_entitlement=economics["cash_entitlement"], events=economics["events"]):
                    raise ValueError("canonical/R1 closed entitlement attribution mismatch")
        expected_cash = self.initial_cash + sum(
            (-e["price"] * e["quantity"] - e["cost"] if e["side"] == "buy" else e["price"] * e["quantity"] - e["cost"])
            for e in journal.values()) + sum(r.amount for r in entitlements.values())
        if not math.isclose(expected_cash, portfolio.cash.projected_cash, abs_tol=1e-6, rel_tol=0):
            raise ValueError("canonical fill/entitlement cash and NAV mismatch")
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
        self._verify_run()
        self._check_accounts()
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
        state = self._state()
        state["state_digest"] = _digest(state)
        _atomic_write(path, json.dumps(state, allow_nan=False).encode())

    def _state(self, tables=None):
        state = dict(version=VERSION, input_binding=self.inputs.binding_id, identity=self.ledger.identity,
                     declared_cell=self._declared_cell,
                     initial_cash=self.initial_cash, sessions=self.sessions, cash=self.cash,
                     tables=self.ledger.rows if tables is None else tables, positions={s: asdict(p) for s,p in self.positions.items()},
                     plans=self.plans, pending_entries=self.pending_entries, completed=self.completed,
                     frozen=self.frozen, freeze_reason=self.freeze_reason, last_reliable_equity=self.last_reliable_equity,
                     journal=self.journal, close_exit_reasons=self.close_exit_reasons)
        return _plain(state)

    @classmethod
    def load(cls, path, *, inputs):
        state = json.loads(Path(path).read_text())
        digest = state.pop("state_digest", None)
        if digest != _digest(state) or state.get("version") != VERSION or state.get("input_binding") != inputs.binding_id:
            raise ValueError("saved S3 version/integrity/input mismatch")
        identity = state["identity"]
        engine = cls(inputs=inputs, run_id=identity["run_id"], entry_mode=identity["entry_mode"],
                     exit_mode=identity["exit_mode"], initial_cash=state["initial_cash"])
        if (identity != engine.ledger.identity or state["sessions"] != engine.sessions
                or tuple(state.get("declared_cell", [])) != engine._declared_cell):
            raise ValueError("saved S3 source/cell/calendar mismatch")
        engine.ledger.rows = state['tables']
        events=iter(state['journal'])
        for event in events:
            if event['kind']=='fill':
                engine._execute(event)
            elif event['kind']=='settle':
                at=datetime.fromisoformat(event['at'])
                if engine.canonical.portfolio.settlements.pending[event['id']].due_at>at:
                    raise ValueError('saved settlement precedes canonical due date')
                engine.canonical.portfolio.settlements.settle(event['id'],at)
            elif event['kind'] in {'reviewed_ca','normalized_ca'}:
                decisions=[r for r in state['tables']['decisions'] if r['trade_id']==event['trade_id']]
                if len(decisions)!=1 or decisions[0]['stock']!=event['ticker']:
                    raise ValueError('saved corporate-action holding provenance mismatch')
                records=engine._apply_bound_ca(event['ticker'],event['day'],event['old_stop'])
                supplied=[event]+[next(events,None) for _ in range(len(records)-1)]
                expected=[dict(r,trade_id=event['trade_id']) for r in records]
                if expected != supplied:
                    raise ValueError('saved corporate-action economics mismatch')
                engine.applied_ca_keys.add((event['day'],event['ticker']))
            elif event['kind']=='reviewed_ca_payment':
                if inputs.reviewed_ca is None:
                    raise ValueError('saved payment lacks bound overlay')
                paid=inputs.reviewed_ca.pay_due(portfolio=engine.canonical.portfolio,day=event['day'])
                if paid != [event]:
                    raise ValueError('saved corporate-action payment mismatch')
            elif event['kind']=='normalized_ca_payment':
                if inputs.normalized_ca is None:
                    raise ValueError('saved normalized payment lacks bound source')
                receivable=engine.canonical.portfolio.corporate_actions.dividend_receivables[event['event_id']]
                at=datetime.fromisoformat(event['day'])
                paid=engine.canonical_replay.pay_cash_dividend(event['event_id'],at)
                expected=dict(kind='normalized_ca_payment',event_id=event['event_id'],day=event['day'],amount=paid.amount)
                if expected!=event:
                    raise ValueError('saved normalized payment mismatch')
            elif event['kind']=='terminal_observation':
                terminal=next((t for t in inputs.terminal_records if t.ticker==event['ticker']),None)
                if terminal is None or engine._terminal_observation(terminal,event['day'])!=event:
                    raise ValueError('saved terminal exposure mismatch')
            elif event['kind']=='unresolved_ca':
                pos=engine.canonical.portfolio.positions.positions.get(event['ticker'])
                if (pos is None or pos.quantity!=event['old_quantity']
                        or engine._holding_trade_id(event['ticker'])!=event['trade_id']
                        or event['binding']!=inputs.binding_id):
                    raise ValueError('saved unresolved corporate-action holding mismatch')
                try:
                    engine._apply_bound_ca(event['ticker'],event['day'],event['old_stop'])
                except ValueError as error:
                    if str(error)!=event['reason']:
                        raise ValueError('saved unresolved corporate-action reason mismatch')
                else:
                    raise ValueError('saved unresolved event no longer rejects')
            elif event['kind']=='execution_blocked':
                try:
                    engine._execute(event)
                except NotExecutableError as error:
                    if str(error)!=event['reason']:
                        raise ValueError('saved blocked execution reason mismatch')
                else:
                    raise ValueError('saved blocked execution no longer rejects')
            else:
                raise ValueError('unknown canonical journal event')
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

    def cell_status(self):
        self.validate_tables()
        expected=[day for day in self.sessions if self.inputs.manifest['period']['start']<=day<=self.inputs.manifest['period']['end']]
        full = self.completed==expected and not self.plans
        observations=[r for r in self.journal if r['kind']=='terminal_observation']
        affected=[r for r in observations if r['held_quantity']>0]
        status = 'INCOMPLETE' if self.frozen else 'COMPLETE_UNAFFECTED' if full else 'PARTIAL' if self.completed else 'NOT_RUN'
        return dict(status=status,input_binding=self.inputs.binding_id,entry_mode=self.entry_mode,exit_mode=self.exit_mode,
            full_e1_sessions_covered=full,completed_sessions=len(self.completed),expected_sessions=len(expected),
            s1_population_preserved=not bool(self.inputs.manifest.get('diagnostic_overlay')),
            diagnostic_overlay=self.inputs.manifest.get('diagnostic_overlay'),
            unresolved_terminal_tickers=sorted({t.ticker for t in self.inputs.terminal_records
                if t.effective_date is not None and str(t.effective_date)<=self.inputs.manifest['period']['end']}),
            terminal_observations=observations,held_crossings=affected,
            freeze_reason=self.freeze_reason,final_terms_status='UNKNOWN')

    def metrics(self, tables=None):
        self.validate_tables(tables)
        self._check_accounts()
        if self.inputs.fixture:
            raise ValueError("engineering fixtures cannot produce S3 performance")
        if self.inputs.probe:
            raise ValueError('real accounting probes cannot produce S3 performance')
        self.inputs.readiness.require_performance_unlocked()
        if self.frozen:
            raise ValueError("unresolved holding path blocks S3 performance")
        coverage=self.cell_status()
        if coverage['status']!='COMPLETE_UNAFFECTED':
            raise ValueError("incomplete E1 coverage blocks S3 performance")
        result = _metric_rows(tables if tables is not None else self.ledger.tables(), scope="s3_fixed_E1")
        for key in ["exit_mode", "source_kind", "input_binding", "execution_version"]:
            result[key] = self.ledger.identity[key]
        result.attrs['unresolved_event_coverage']=coverage
        return result


# The reference executor remains available for exact regression comparisons.
# Batch execution consumes detached immutable bytes, never caller-owned frames.
from collections import deque, namedtuple
from types import MappingProxyType
from weakref import WeakValueDictionary
import numpy as np

_BATCH_SNAPSHOTS = WeakValueDictionary()


_FEATURE_DTYPE = np.dtype([
    ('trigger', '?'), ('bb_upper', '<f8'), ('sma20', '<f8'), ('prev_close', '<f8'),
    ('base_sessions', '<i8'), ('base_valid', '?'), ('pivot', '<f8'),
    ('structure_stop', '<f8'), ('rsi13', '<f8'),
])


def _feature_bytes(history):
    """Causal prefix-equivalent rolling calculations and linear-time base extrema."""
    close = history.close
    upper = close.rolling(21, min_periods=21).mean() + 2.1 * close.rolling(21, min_periods=21).std(ddof=0)
    above = close.gt(upper) & np.isfinite(upper)
    result = np.empty(len(history), dtype=_FEATURE_DTYPE)
    result['trigger'] = (above & close.shift().le(upper.shift()) & np.isfinite(upper.shift())).to_numpy()
    result['bb_upper'] = upper.to_numpy()
    result['sma20'] = close.rolling(20, min_periods=20).mean().to_numpy()
    result['prev_close'] = close.shift().to_numpy()
    result['rsi13'] = _rsi_value(panel=history, lookback=13).to_numpy()
    values = close.to_numpy(dtype=float)
    missing = np.concatenate(([0], np.cumsum(np.isnan(values))))
    last_above = -1
    maxima, minima = deque(), deque()
    for i, value in enumerate(values):
        start = last_above + 1 if last_above >= 0 else i - 60
        left = max(0, start)
        if i and not np.isnan(values[i-1]):
            previous = values[i-1]
            while maxima and values[maxima[-1]] <= previous:
                maxima.pop()
            while minima and values[minima[-1]] >= previous:
                minima.pop()
            maxima.append(i-1); minima.append(i-1)
        while maxima and maxima[0] < left:
            maxima.popleft()
        while minima and minima[0] < left:
            minima.popleft()
        result['base_sessions'][i] = i - left
        result['base_valid'][i] = start >= 0 and missing[i] == missing[left]
        result['pivot'][i] = values[maxima[0]] if maxima else np.nan
        result['structure_stop'][i] = values[minima[0]] if minima else np.nan
        if above.iloc[i]:
            last_above = i
    return result.tobytes()  # bytes-backed views cannot turn WRITEABLE back on.


def _arrow_bytes(frame):
    import pyarrow as pa
    table = pa.Table.from_pandas(frame, preserve_index=False)
    # Repeated binding/source strings otherwise consume hundreds of MB in daily snapshots.
    for i, field in enumerate(table.schema):
        if (pa.types.is_string(field.type) or pa.types.is_large_string(field.type)) and frame[field.name].nunique() < 64:
            table = table.set_column(i, field.name, table.column(i).dictionary_encode())
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return sink.getvalue().to_pybytes()


def _arrow_frame(value, index=None):
    import pyarrow as pa
    table = pa.ipc.open_stream(pa.BufferReader(value)).read_all()
    if index is not None:
        table = table.slice(index, 1)
    return table.to_pandas()


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


class _Sealed:
    def __getattribute__(self, name):
        value = object.__getattribute__(self, name)
        return MappingProxyType(value) if name == '__dict__' else value

    def __setattr__(self, name, value):
        if getattr(self, '_sealed', False):
            raise TypeError('immutable S3 runtime snapshot')
        object.__setattr__(self, name, value)


_RECORD_TYPES = {}


def _immutable_record(value):
    # Detach even frozen dataclasses: their ordinary __dict__ is otherwise writable.
    if hasattr(value, '__dataclass_fields__'):
        kind = type(value)
        record = _RECORD_TYPES.get(kind)
        if record is None:
            record = namedtuple('Sealed' + kind.__name__, [f.name for f in fields(value)])
            _RECORD_TYPES[kind] = record
        return record(*(_immutable_record(getattr(value, f.name)) for f in fields(value)))
    return value


class _BatchReadiness(namedtuple('SealedReadiness', [f.name for f in fields(AccountingReadiness)])):
    __slots__ = ()

    @property
    def passed(self):
        return all(self)

    @property
    def failed_checks(self):
        return tuple(k for k, v in zip(self._fields, self) if not v)

    def require_performance_unlocked(self):
        return AccountingReadiness.require_performance_unlocked(self)


class _BatchNormalizedCA(_Sealed, NormalizedCA):
    def __init__(self, original):
        self.binding = original.binding
        self.actions = tuple(_immutable_record(a) for a in original.actions)
        self._sealed = True

    def verify(self):
        # Already verified and detached at Day 0. No file or all-actions hash here.
        return None


class _BatchReviewedCA(_Sealed, ReviewedCA):
    def __init__(self, original):
        self.binding = original.binding
        self.action = _immutable_record(original.resolve('1315', '2020-10-26'))
        self._sealed = True

    def verify(self):
        return None

    def resolve(self, ticker, day):
        if (str(ticker), str(day)) != ('1315', '2020-10-26'):
            raise ValueError('corporate action lacks complete reviewed physical evidence')
        return self.action


class _BatchInputs(_Sealed, S3Inputs):
    def __init__(self, original, runtime):
        for name in ('binding_id', 'source_kind', 'fixture', 'probe', 'source_root', 'root',
                     ):
            setattr(self, name, getattr(original, name))
        self._panel_keys = _ImmutablePanelKeys.build(original._panel_keys)
        self._snapshot = _InputSnapshot(original.binding_id, original._snapshot.bars_sha,
                                        self._panel_keys, original._snapshot.ca_sha)
        self.manifest = _freeze(deepcopy(original.manifest))
        self.inventory = _freeze(deepcopy(original.inventory))
        self.official_event_types = MappingProxyType(dict(original.official_event_types))
        self.terminal_records = tuple(_immutable_record(t) for t in original.terminal_records)
        self.readiness = _BatchReadiness(*(getattr(original.readiness, f.name) for f in fields(AccountingReadiness)))
        self.normalized_ca = None if original.normalized_ca is None else _BatchNormalizedCA(original.normalized_ca)
        self.reviewed_ca = None if original.reviewed_ca is None else _BatchReviewedCA(original.reviewed_ca)
        self.calendar = runtime.calendar
        self.runtime = runtime
        self._sealed = True

    def verify(self):
        return None

    @property
    def _bars(self):
        # Parent initialization needs only the calendar; no mutable source frame survives.
        return pd.DataFrame({'date': pd.to_datetime(self.calendar)})


@dataclass(frozen=True, slots=True)
class _ImmutablePanelKeys:
    days: object
    stocks: object
    bits: bytes
    width: int

    @classmethod
    def build(cls, keys):
        days = {d: i for i, d in enumerate(sorted({d for d, _ in keys}))}
        stocks = {s: i for i, s in enumerate(sorted({s for _, s in keys}))}
        bits = np.zeros(len(days)*len(stocks), dtype=np.uint8)
        for d, s in keys:
            bits[days[d]*len(stocks)+stocks[s]] = 1
        return cls(MappingProxyType(days), MappingProxyType(stocks), bits.tobytes(), len(stocks))

    def __contains__(self, key):
        day, stock = key
        d, s = self.days.get(day), self.stocks.get(stock)
        return d is not None and s is not None and bool(self.bits[d*self.width+s])


@dataclass(frozen=True, slots=True, weakref_slot=True)
class _BatchSnapshot:
    days: object
    stocks: object
    features: object
    calendar: tuple
    day_index: object
    cache_sha: str
    input_binding: str

    @classmethod
    def build(cls, inputs):
        bars = inputs._bars
        calendar = tuple(sorted(_day(v) for v in bars.date.unique()))
        dates = pd.to_datetime(calendar)
        features, stocks = {}, {}
        tape = pd.read_parquet(inputs.role('tradability'))
        tape['stock_id'] = tape.stock_id.astype(str)
        tape['date'] = pd.to_datetime(tape.date).dt.normalize()
        if tape.duplicated(['stock_id', 'date']).any():
            raise ValueError('duplicate canonical tradability keys')
        tape = tape.set_index(['stock_id', 'date'])
        tape_by_stock = {stock: group.droplevel('stock_id')
                         for stock, group in tape.groupby(level='stock_id', sort=False)}
        digest = hashlib.sha256()
        for stock, group in bars.groupby('stock', sort=False):
            history = group.set_index('date').reindex(dates)
            history['stock_id'] = stock
            encoded = _feature_bytes(history)
            features[stock] = encoded
            digest.update(stock.encode()); digest.update(encoded)
            source_truth = tape_by_stock.get(stock)
            truth = source_truth.reindex(dates) if source_truth is not None else pd.DataFrame(index=dates)
            raw = history[['open', 'high', 'low', 'close', 'corporate_action']].copy()
            raw = raw.rename(columns={'high': 'max', 'low': 'min'})
            for column in ('observed_trade', 'valid_ohlc', 'buy_blocked', 'sell_blocked', 'reason'):
                raw[column] = truth[column] if column in truth else None
            raw['_raw_present'] = history.stock.notna()
            raw['_tape_present'] = truth.index.isin(source_truth.index) if source_truth is not None else False
            stocks[stock] = _arrow_bytes(raw.reset_index(drop=True))
        days = {_day(day): _arrow_bytes(group) for day, group in bars.groupby('date', sort=False)}
        snapshot = cls(MappingProxyType(days), MappingProxyType(stocks), MappingProxyType(features),
                   calendar, MappingProxyType({d: i for i, d in enumerate(calendar)}), digest.hexdigest(), inputs.binding_id)
        _BATCH_SNAPSHOTS[id(snapshot)] = snapshot
        return snapshot


class _BatchMarketData(ExecutionMarketData):
    """Use the same RAW/tradability resolver against immutable Day 0 records."""
    def __init__(self, source, snapshot):
        super().__init__(source)
        self.snapshot = snapshot

    def _snapshot_row(self, ticker, day):
        index = self.snapshot.day_index.get(_day(day))
        data = self.snapshot.stocks.get(str(ticker))
        if index is None or data is None:
            return None
        return _arrow_frame(data, index).iloc[0]

    def _raw_row(self, ticker, session_date):
        row = self._snapshot_row(ticker, session_date)
        return None if row is None or not row['_raw_present'] else row

    def _tradability_row(self, ticker, session_date):
        row = self._snapshot_row(ticker, session_date)
        return None if row is None or not row['_tape_present'] else row

    def _latest_valid_raw_before(self, *, ticker, day):
        data = self.snapshot.stocks.get(str(ticker))
        if data is None:
            return None
        frame = _arrow_frame(data)
        before = np.searchsorted(self.snapshot.calendar, _day(day))
        for i in range(before-1, -1, -1):
            row = frame.iloc[i]
            session = pd.Timestamp(self.snapshot.calendar[i])
            if row['_raw_present'] and self._bar_from_row(ticker, session, row) is not None:
                return session, row
        return None


class _ChunkRows:
    """Append-only eligibility records; durable immutable chunks keep RAM bounded."""
    def __init__(self, root=None, references=()):
        self.root = None if root is None else Path(root)
        self.references = list(references)
        self.live = []
        self.archived = sum(r['rows'] for r in references)

    def append(self, row):
        self.live.append(row)

    def batches(self):
        import gzip
        for reference in self.references:
            data = gzip.decompress((self.root / reference['path']).read_bytes())
            if hashlib.sha256(data).hexdigest() != reference['sha256']:
                raise ValueError('changed immutable eligibility checkpoint chunk')
            rows = json.loads(data)
            if len(rows) != reference['rows']:
                raise ValueError('eligibility checkpoint chunk row count mismatch')
            yield rows
        if self.live:
            yield self.live

    def __iter__(self):
        for rows in self.batches():
            yield from rows

    def __len__(self):
        return self.archived + len(self.live)

    def __getitem__(self, index):
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            if start >= self.archived:
                return self.live[start-self.archived:stop-self.archived:step]
            from itertools import islice
            return list(islice(self, start, stop, step))
        if index < 0: index += len(self)
        if index >= self.archived:
            return self.live[index-self.archived]
        from itertools import islice
        return next(islice(self, index, index+1))

    def spill(self, root, references):
        self.root = Path(root)
        self.references.extend(references)
        self.archived += len(self.live)
        self.live.clear()


class _BatchLedger(_S3Ledger):
    def __init__(self, *args):
        super().__init__(*args)
        self.rows['eligibility'] = _ChunkRows()
        self._indexes = {name: {} for name in self.schemas}
        self._indexed_rows = self.rows
        self.defer_tables = False
        self._checked_shapes = set()

    def _index(self):
        if self.rows is not self._indexed_rows:
            self._indexes = {name: {r['row_id']: r for r in rows} for name, rows in self.rows.items()}
            if any(len(self._indexes[name]) != len(rows) for name, rows in self.rows.items()):
                raise ValueError('duplicate restored S3 ledger key')
            self._indexed_rows = self.rows

    def find(self, table, row_id):
        self._index()
        hit = self._indexes[table].get(row_id)
        if hit is True:
            return next(r for r in self.rows[table] if r['row_id'] == row_id)
        return hit

    def add(self, table, row_id, **values):
        self._index()
        if row_id in self._indexes[table]:
            raise ValueError(f'duplicate {table} row: {row_id}')
        shape = (table, frozenset(values))
        if shape not in self._checked_shapes:
            unknown = set(values) - set(self.schemas[table])
            if unknown:
                raise ValueError(f'unknown {table} fields: {sorted(unknown)}')
            self._checked_shapes.add(shape)
        row = dict.fromkeys(self.schemas[table])
        row.update(self.identity, row_id=row_id, **values)
        self.rows[table].append(row)
        self._indexes[table][row_id] = row
        return row

    def tables(self):
        return {} if self.defer_tables else super().tables()

    def batches(self, name):
        rows = self.rows[name]
        batches = rows.batches() if isinstance(rows, _ChunkRows) else [rows]
        produced = False
        for batch in batches:
            produced = True
            temporary = _S3Ledger('chunk', 'backtest')
            temporary.rows[name] = batch
            yield temporary.table(name)
        if not produced:
            yield _S3Ledger('empty', 'backtest').table(name)

    def table(self, name):
        return pd.concat(list(self.batches(name)), ignore_index=True)


class S3BatchTradingPlanR1(S3TradingPlanR1):
    """Sealed Day 0 input/indicator snapshot; canonical accounting remains active."""
    def __init__(self, *, inputs, run_id, entry_mode, exit_mode, initial_cash=1_000_000,
                 snapshot=None):
        # Exactly the legacy verification at the loader boundary, never in the loop.
        if not isinstance(inputs, _BatchInputs):
            inputs.verify()
        snapshot = snapshot or (inputs.runtime if isinstance(inputs, _BatchInputs) else None) or next((s for s in list(_BATCH_SNAPSHOTS.values())
                                     if s.input_binding == inputs.binding_id), None)
        if snapshot is None:
            if isinstance(inputs, _BatchInputs):
                raise ValueError('sealed inputs require their verified runtime snapshot')
            snapshot = _BatchSnapshot.build(inputs)
        if (_BATCH_SNAPSHOTS.get(id(snapshot)) is not snapshot
                or snapshot.input_binding != inputs.binding_id):
            raise ValueError('unverified or wrong-input S3 indicator cache')
        sealed = inputs if isinstance(inputs, _BatchInputs) else _BatchInputs(inputs, snapshot)
        super().__init__(inputs=sealed, run_id=run_id, entry_mode=entry_mode,
                         exit_mode=exit_mode, initial_cash=initial_cash)
        self._runtime = snapshot
        self._declared_runtime = snapshot
        self._declared_inputs = sealed
        self._bound_bars = snapshot
        ledger = _BatchLedger(run_id, 'backtest', 's3-r1', entry_mode)
        ledger.identity = deepcopy(self.ledger.identity)
        self.ledger = ledger
        self.canonical.market_data = _BatchMarketData(SourceDataAdapter(inputs.source_root), snapshot)
        self._declared_market = self.canonical.market_data
        self._active_day = None
        self.runtime_manifest = dict(input_binding=inputs.binding_id, bars_sha256=inputs._snapshot.bars_sha,
            indicator_sha256=snapshot.cache_sha, formula='BB21/2.1/ddof0;SMA20;RSI13;causal-base-v1',
            validation_boundary='Day0', immutable_storage='owned bytes; mapping proxies; frozen scalar instructions',
            files=[dict(e) for e in inputs.inventory])
        self._checkpoint_chunks = []
        self._checkpoint_counts = {'eligibility': 0, 'equity': 0}
        self._economics_context = None

    def _check_accounts(self):
        # Rebuild from actual current records at each gate; no historical check is skipped.
        # Index once instead of rescanning every rejected order for each closed trade.
        by_trade, events = {}, {}
        for row in self.ledger.rows['fills']:
            if row['fill']:
                by_trade.setdefault(row['trade_id'], []).append(row)
        journal = {}
        for event in self.journal:
            if event['kind'] == 'fill':
                journal[event['id']] = event
            elif event['kind'] in {'reviewed_ca', 'normalized_ca'}:
                events.setdefault(event['trade_id'], []).append(event['event_id'])
        ca = self.canonical.portfolio.corporate_actions
        rights = {**ca.completed_cash_entitlements, **ca.cash_entitlement_receivables,
                  **ca.completed_dividends, **ca.dividend_receivables}
        self._economics_context = (by_trade, journal, events, rights)
        try:
            return super()._check_accounts()
        finally:
            self._economics_context = None

    def _trade_economics(self, trade_id):
        if self._economics_context is None:
            return super()._trade_economics(trade_id)
        by_trade, journal, events, rights = self._economics_context
        rows = by_trade.get(trade_id, ())
        buys = [r for r in rows if r['side'] == 'buy']
        sells = [r for r in rows if r['side'] == 'sell']
        if len(buys) != 1 or len(sells) != 1:
            raise ValueError('closed trade requires one canonical entry and exit')
        buy, sell = (journal[r['row_id']] for r in (buys[0], sells[0]))
        entry = buy['quantity'] * buy['price'] + buy['cost']
        proceeds = sell['quantity'] * sell['price'] - sell['cost']
        ids = events.get(trade_id, [])
        amount = sum(rights[event_id].amount for event_id in ids if event_id in rights)
        pnl = proceeds + amount - entry
        return dict(pnl=pnl, net_return=pnl / entry, cash_entitlement=amount, events=ids)

    def _verify_run(self):
        if (self.inputs is not self._declared_inputs or self._runtime is not self._declared_runtime
                or self.inputs.runtime is not self._runtime
                or self._bound_bars is not self._runtime
                or self.canonical.market_data is not self._declared_market
                or self.canonical.market_data.snapshot is not self._runtime
                or (self.entry_mode, self.exit_mode) != self._declared_cell
                or self.ledger.identity != self._declared_identity
                or tuple(self.sessions) != self._declared_sessions):
            raise ValueError('changed S3 execution cell/identity/calendar/immutable snapshot')

    def _prices(self, bars):
        self._verify_run()
        if bars is not self._runtime:
            raise ValueError('external bars cannot enter scoped S3')
        frame = _arrow_frame(self._runtime.days[self._active_day])
        frame['date'] = _day_labels(frame.date)
        return frame

    def _features(self, p, stock, day):
        row = np.frombuffer(self._runtime.features[stock], dtype=_FEATURE_DTYPE)[self._runtime.day_index[day]]
        return {name: row[name].item() for name in _FEATURE_DTYPE.names}

    def _execution_bar(self, stock, day):
        row = self.canonical.market_data._snapshot_row(stock, day)
        return pd.DataFrame() if row is None else pd.DataFrame([dict(corporate_action=row.corporate_action)])

    def _terminal_observation(self, terminal, day):
        position = self.canonical.portfolio.positions.positions.get(terminal.ticker)
        terms = next(e['sha256'] for e in self.inputs.inventory if e['role'] == 'terminal')
        return dict(kind='terminal_observation', ticker=terminal.ticker, day=day,
            candidate_boundary=str(terminal.suspension_from or terminal.effective_date),
            source_status='UNKNOWN_FINAL_TERMS', binding=self.inputs.binding_id, terms_sha=terms,
            held_quantity=0 if position is None else position.quantity,
            trade_id=self._holding_trade_id(terminal.ticker))

    def prepare(self, day):
        self._active_day = _day(day)
        self.ledger.defer_tables = True
        try:
            return super().prepare(day)
        finally:
            self.ledger.defer_tables = False

    def reconcile_session(self, day, *, observed_at):
        self.ledger.defer_tables = True
        try:
            return super().reconcile_session(day, observed_at=observed_at)
        finally:
            self.ledger.defer_tables = False

    def remaining_sessions(self):
        """Continue an unfinished prepared day, otherwise next declared trading session."""
        scope = tuple(self.inputs.manifest.get('probe_sessions', [d for d in self.sessions
            if self.inputs.manifest['period']['start'] <= d <= self.inputs.manifest['period']['end']]))
        if self.inputs.fixture and self.completed:
            # Engineering fixtures explicitly start after their synthetic warm-up.
            scope = scope[scope.index(self.completed[0]):]
        if self.completed != list(scope[:len(self.completed)]):
            raise ValueError('checkpoint is not a completed calendar prefix')
        if [r['date'] for r in self.ledger.rows['equity']] != self.completed:
            raise ValueError('checkpoint equity dates differ from completed sessions')
        if self.plans and tuple(self.plans) != scope[len(self.completed):len(self.completed)+1]:
            raise ValueError('checkpoint prepared day is not the next uncompleted session')
        return scope[len(self.completed):]

    def _state(self, tables=None):
        if tables is None:
            tables = dict(self.ledger.rows)
            tables['eligibility'] = list(tables['eligibility'])
        return super()._state(tables=tables)

    def save(self, path):
        if len(self.ledger.rows['eligibility']) > 100_000:
            self.save_checkpoint(path)
        else:
            super().save(path)

    def validate_tables(self, tables=None):
        if tables is not None:
            return super().validate_tables(tables)
        self._verify_run(); self._check_accounts()
        self.ledger._index()
        for name in S3_SCHEMAS:
            count = 0
            for frame in self.ledger.batches(name):
                if tuple(frame.columns) != S3_SCHEMAS[name] or frame.row_id.duplicated().any():
                    raise ValueError('S3 ledger schema/key mismatch')
                if any(not frame[key].eq(value).all() for key, value in self.ledger.identity.items()):
                    raise ValueError('S3 ledger identity/input binding mismatch')
                if any(row_id not in self.ledger._indexes[name] for row_id in frame.row_id):
                    raise ValueError('changed S3 ledger indexed row key')
                count += len(frame)
            if count != len(self.ledger._indexes[name]):
                raise ValueError('duplicate or missing S3 ledger key')

    def metric_tables(self):
        # The eight metrics consume only fills, decisions and equity, never eligibility.
        return {name: self.ledger.table(name) if name != 'eligibility'
                else _S3Ledger('empty', 'backtest').table(name) for name in S3_SCHEMAS}

    def export_tables(self, directory):
        self.validate_tables()
        target = Path(directory); target.mkdir(parents=True, exist_ok=True)
        for name in S3_SCHEMAS:
            first = True
            for frame in self.ledger.batches(name):
                for col in frame:
                    if col in OBJECT_COLUMNS:
                        frame[col] = frame[col].map(lambda v: json.dumps(_plain(v)))
                    elif col not in FLOAT_COLUMNS | BOOL_COLUMNS:
                        frame[col] = frame[col].map(lambda v: json.dumps(None if pd.isna(v) else str(v)))
                frame.to_csv(target / f's3_{name}.csv', index=False, mode='w' if first else 'a', header=first)
                first = False

    def run_remaining(self, *, checkpoint, after_checkpoint=None, max_sessions=None):
        done = 0
        for day in self.remaining_sessions():
            if self.frozen or (max_sessions is not None and done >= max_sessions):
                break
            self.prepare(day); self.reconcile_session(day, observed_at=day)
            self.save_checkpoint(checkpoint)
            if after_checkpoint is not None:
                after_checkpoint(self, Path(checkpoint))
            done += 1
        return done

    def save_checkpoint(self, path):
        """Append-only tables are immutable chunks; overwrite only the small state head."""
        import gzip
        self._verify_run(); self._check_accounts()
        target = Path(path); chunks = target.parent / 'checkpoint_chunks'
        chunks.mkdir(parents=True, exist_ok=True)
        references = list(self._checkpoint_chunks)
        counts = dict(self._checkpoint_counts)
        for table in ('eligibility', 'equity'):
            rows = self.ledger.rows[table][counts[table]:]
            if not rows:
                continue
            if table == 'eligibility':
                for row in rows:
                    if (set(row) != set(S3_SCHEMAS[table])
                            or any(row.get(k) != v for k, v in self.ledger.identity.items())
                            or row['row_id'] not in self.ledger._indexes[table]):
                        raise ValueError('changed new S3 eligibility checkpoint row')
            data = json.dumps(_plain(rows), allow_nan=False, separators=(',', ':')).encode()
            sha = hashlib.sha256(data).hexdigest()
            relative = 'checkpoint_chunks/' + sha + '.json.gz'
            _atomic_write(target.parent / relative, gzip.compress(data, mtime=0))
            references.append(dict(table=table, path=relative, sha256=sha, rows=len(rows)))
            counts[table] += len(rows)
        mutable = {k: v if k not in counts else [] for k, v in self.ledger.rows.items()}
        state = self._state(tables=mutable)
        state['checkpoint_storage'] = dict(version='s3-chunked-checkpoint-v1', chunks=references, counts=counts)
        state['state_digest'] = _digest(state)
        _atomic_write(target, json.dumps(state, allow_nan=False).encode())
        # Archive the committed generation as well as the atomic latest pointer.
        encoded = json.dumps(state, allow_nan=False).encode()
        label = self.completed[-1] if self.completed else 'Day0'
        _atomic_write(target.parent / 'checkpoint_heads' / (label + '-' + hashlib.sha256(encoded).hexdigest() + '.json'), encoded)
        self._checkpoint_chunks, self._checkpoint_counts = references, counts
        rows = self.ledger.rows['eligibility']
        if isinstance(rows, _ChunkRows):
            # references also contain equity chunks: select by cumulative eligibility count.
            eligible = [r for r in references if r['table'] == 'eligibility']
            newly = eligible[len(rows.references):]
            for row in rows.live:
                self.ledger._indexes['eligibility'][row['row_id']] = True
            rows.spill(target.parent, newly)

    @classmethod
    def load_checkpoint(cls, path, *, inputs, run_id=None, entry_mode=None, exit_mode=None):
        import gzip
        import tempfile
        target = Path(path).resolve()
        state = json.loads(target.read_text())
        identity = state.get('identity', {})
        for key, expected in [('run_id', run_id), ('entry_mode', entry_mode), ('exit_mode', exit_mode)]:
            if expected is not None and identity.get(key) != expected:
                raise ValueError('checkpoint execution identity mismatch: ' + key)
        if 'checkpoint_storage' not in state:
            return cls.load(target, inputs=inputs)
        digest = state.pop('state_digest', None)
        if digest != _digest(state):
            raise ValueError('checkpoint head integrity mismatch')
        storage = state.pop('checkpoint_storage')
        if storage['version'] != 's3-chunked-checkpoint-v1':
            raise ValueError('unknown checkpoint storage')
        eligible_index = {}
        eligible_references = []
        for reference in storage['chunks']:
            file = (target.parent / reference['path']).resolve(); file.relative_to(target.parent)
            if reference['table'] not in {'eligibility', 'equity'}:
                raise ValueError('unexpected checkpoint chunk table')
            data = gzip.decompress(file.read_bytes())
            rows = json.loads(data)
            if hashlib.sha256(data).hexdigest() != reference['sha256'] or len(rows) != reference['rows']:
                raise ValueError('checkpoint chunk integrity mismatch')
            if reference['table'] == 'eligibility':
                eligible_references.append(reference)
                for row in rows:
                    if (set(row) != set(S3_SCHEMAS['eligibility'])
                            or any(row.get(k) != v for k, v in identity.items())
                            or row['row_id'] in eligible_index):
                        raise ValueError('checkpoint eligibility schema/identity/key mismatch')
                    eligible_index[row['row_id']] = True
                temporary = _S3Ledger('chunk', 'backtest'); temporary.rows['eligibility'] = rows
                temporary.table('eligibility')  # Typed loader gate, bounded to one chunk.
            else:
                state['tables'][reference['table']].extend(rows)
        if any((len(eligible_index) if k == 'eligibility' else len(state['tables'][k])) != count
               for k, count in storage['counts'].items()):
            raise ValueError('checkpoint row count mismatch')
        state['state_digest'] = _digest(state)
        # Use the existing strict canonical replay/economics reader, not a second permissive loader.
        fd, temporary = tempfile.mkstemp(dir=target.parent, suffix='.replay.json')
        os.close(fd)
        try:
            Path(temporary).write_text(json.dumps(state, allow_nan=False))
            engine = cls.load(temporary, inputs=inputs)
        finally:
            Path(temporary).unlink(missing_ok=True)
        engine._checkpoint_chunks = storage['chunks']
        engine._checkpoint_counts = storage['counts']
        engine.ledger.rows['eligibility'] = _ChunkRows(target.parent, eligible_references)
        engine.ledger._index()
        engine.ledger._indexes['eligibility'] = eligible_index
        engine.remaining_sessions()
        return engine
