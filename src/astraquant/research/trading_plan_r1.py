from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from astraquant.execution.assumptions import SideAwareBpsFeeModel


RULE_VERSION = "trading-plan-r1-owner-20261008-r2"
COMMISSION = 0.001425 * 0.6
TAX = 0.003
SLIPPAGE = 0.002
FEES = SideAwareBpsFeeModel(COMMISSION * 10000, (COMMISSION + TAX) * 10000)
COMMON = ("run_id", "portfolio_id", "mode", "entry_mode", "source_kind", "rule_version", "row_id")
SCHEMAS = {
    "eligibility": COMMON + (
        "date", "stock", "condition_values", "condition_passes", "source",
        "available_date", "eligible", "data_status",
    ),
    "decisions": COMMON + (
        "date", "stock", "trade_id", "order_id", "direction", "trigger",
        "want_price", "price_cap", "stop_price", "reject_reason", "reject_reasons", "rs",
        "pivot", "structure_stop", "base_sessions", "status",
    ),
    "fills": COMMON + (
        "date", "stock", "trade_id", "order_id", "side", "order", "fill",
        "cancel", "exit", "cost", "corporate_action", "truncated", "status",
        "reason", "quantity", "want_price", "fill_price", "fill_date",
        "commission", "tax", "slippage", "cash_flow", "pnl", "net_return",
        "holding_sessions", "reconciled_at", "price_semantics",
    ),
    "equity": COMMON + (
        "date", "cash", "positions", "equity", "blocked_opportunities",
        "frozen", "freeze_reason", "last_reliable_equity", "capital_occupied",
        "reconciled_at",
    ),
}
FLOAT_COLUMNS = {
    "want_price", "price_cap", "stop_price", "rs", "pivot", "structure_stop",
    "base_sessions", "cost", "quantity", "fill_price", "commission", "tax",
    "slippage", "cash_flow", "pnl", "net_return", "holding_sessions", "cash",
    "equity", "last_reliable_equity", "capital_occupied",
}
BOOL_COLUMNS = {"eligible", "order", "fill", "cancel", "exit", "truncated", "frozen"}
OBJECT_COLUMNS = {"condition_values", "condition_passes", "positions", "blocked_opportunities", "corporate_action", "reject_reasons"}


def _day(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return _day(value)
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class SharedLedger:
    """Four tables; a fill intent keeps its row_id when reconciled."""

    def __init__(self, run_id: str, mode: str, portfolio_id: str = "synthetic-r1", entry_mode: str = "close"):
        if mode not in {"backtest", "daily"}:
            raise ValueError("mode must be backtest or daily")
        if entry_mode not in {"close", "next_open"}:
            raise ValueError("entry_mode must be close or next_open")
        self.identity = dict(run_id=run_id, portfolio_id=portfolio_id, mode=mode, entry_mode=entry_mode,
                             source_kind="synthetic", rule_version=RULE_VERSION)
        self.rows: dict[str, list[dict]] = {name: [] for name in SCHEMAS}

    def add(self, table: str, row_id: str, **values: Any) -> dict:
        if self.find(table, row_id) is not None:
            raise ValueError(f"duplicate {table} row: {row_id}")
        unknown = set(values) - set(SCHEMAS[table])
        if unknown:
            raise ValueError(f"unknown {table} fields: {sorted(unknown)}")
        row = dict.fromkeys(SCHEMAS[table])
        row.update(self.identity, row_id=row_id, **values)
        self.rows[table].append(row)
        return row

    def find(self, table: str, row_id: str) -> dict | None:
        return next((r for r in self.rows[table] if r["row_id"] == row_id), None)

    def table(self, name: str) -> pd.DataFrame:
        frame = pd.DataFrame(deepcopy(self.rows[name]), columns=SCHEMAS[name])
        for col in frame:
            if col in FLOAT_COLUMNS:
                frame[col] = pd.array(frame[col], dtype="Float64")
            elif col in BOOL_COLUMNS:
                frame[col] = pd.array(frame[col], dtype="boolean")
            elif col not in OBJECT_COLUMNS:
                frame[col] = pd.array(frame[col], dtype="string")
        return frame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {name: self.table(name) for name in SCHEMAS}


@dataclass
class Position:
    stock: str
    trade_id: str
    quantity: int
    entry_price: float
    entry_cash: float
    entry_date: str
    entry_index: int
    stop_price: float
    pending_exit: str | None = None
    pending_stop: str | None = None
    truncated: bool = False


class TradingPlanR1:
    """Owner's close/next-open simulation. Synthetic-only; no source gate bypass.

    A final close both confirms the signal and prices the same-session fill.
    This is an explicit close-fill simulation convention, not proof that a live
    pre-close order can know the final close. Slippage is an additional cash cost
    so fill_price retains the owner's exact close/open/observed stop-fill price.
    """

    def __init__(self, *, run_id: str, mode: str, sessions: list[str],
                 initial_cash: float = 1_000_000, portfolio_id: str = "synthetic-r1", entry_mode: str = "close"):
        self.sessions = [_day(d) for d in sessions]
        if not self.sessions or self.sessions != sorted(set(self.sessions)):
            raise ValueError("sessions must be a sorted, unique trading calendar")
        if not _finite(initial_cash) or initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.ledger = SharedLedger(run_id, mode, portfolio_id, entry_mode)
        self.entry_mode = entry_mode
        self.pending_entries: dict[str, dict] = {}
        self.positions: dict[str, Position] = {}
        self.plans: dict[str, dict] = {}
        self.completed: list[str] = []
        self.frozen = False
        self.freeze_reason = ""
        self.last_reliable_equity = float(initial_cash)

    def _id(self, *parts: str) -> str:
        return ":".join((self.ledger.identity["run_id"], *parts))

    @staticmethod
    def _prices(bars: pd.DataFrame) -> pd.DataFrame:
        required = {"date", "stock", "open", "high", "low", "close", "volume", "source_kind",
                    "eligible", "available_date", "source", "rs", "limit_up_price"}
        if not required.issubset(bars):
            raise ValueError(f"missing bar columns: {sorted(required - set(bars))}")
        if bars.empty or not bars.source_kind.eq("synthetic").all():
            raise ValueError("R1 currently accepts explicitly labelled synthetic bars only")
        p = bars.copy()
        p["date"] = p.date.map(_day)
        p["stock"] = p.stock.astype(str)
        if p.duplicated(["date", "stock"]).any():
            raise ValueError("duplicate stock/session bars")
        for col in ("open", "high", "low", "close", "volume"):
            p[col] = pd.to_numeric(p[col], errors="coerce")
        return p.sort_values(["stock", "date"])

    @staticmethod
    def _bar_problem(bar: dict | None) -> str:
        if bar is None:
            return "missing_bar"
        if any(not _finite(bar.get(k)) or float(bar[k]) <= 0 for k in ("open", "high", "low", "close")):
            return "invalid_bar"
        if float(bar["low"]) > min(float(bar["open"]), float(bar["close"])) or float(bar["high"]) < max(float(bar["open"]), float(bar["close"])):
            return "invalid_geometry"
        if bool(bar.get("suspended", False)):
            return "suspended"
        if not _finite(bar.get("volume")) or float(bar["volume"]) <= 0:
            return "no_volume"
        if bar.get("corporate_action"):
            return "unsupported_corporate_action"
        return ""

    def _features(self, p: pd.DataFrame, stock: str, day: str) -> dict:
        index = self.sessions.index(day)
        hist = p[(p.stock == stock) & (p.date <= day)].set_index("date")
        hist = hist.reindex(self.sessions[:index + 1])
        close = hist.close
        upper = close.rolling(21, min_periods=21).mean() + 2.1 * close.rolling(21, min_periods=21).std(ddof=0)
        trigger = bool(index > 0 and _finite(upper.iloc[-1]) and _finite(upper.iloc[-2])
                       and close.iloc[-1] > upper.iloc[-1] and close.iloc[-2] <= upper.iloc[-2])
        previous_above = [i for i in range(max(0, index - 60), index)
                          if _finite(upper.iloc[i]) and close.iloc[i] > upper.iloc[i]]
        start = previous_above[-1] + 1 if previous_above else index - 60
        base = close.iloc[max(0, start):index]
        full_base = start >= 0 and len(base) == index - start and base.notna().all()
        return dict(trigger=trigger, bb_upper=float(upper.iloc[-1]),
                    sma20=float(close.rolling(20, min_periods=20).mean().iloc[-1]),
                    prev_close=float(close.iloc[-2]) if index else float("nan"),
                    base_sessions=len(base), base_valid=bool(full_base),
                    pivot=float(base.max()) if len(base) else float("nan"),
                    structure_stop=float(base.min()) if len(base) else float("nan"))

    def _intent(self, *, day: str, stock: str, trade_id: str, side: str,
                reason: str, want_price: float | None, quantity: int = 0) -> dict:
        oid = self._id(trade_id, side, day, reason)
        return self.ledger.add("fills", oid, date=day, stock=stock, trade_id=trade_id,
                               order_id=oid, side=side, order=True, fill=False,
                               cancel=False, exit=side == "sell", cost=0.0,
                               corporate_action=None, truncated=False, status="INTENT",
                               reason=reason, quantity=quantity, want_price=want_price,
                               commission=0.0, tax=0.0, slippage=0.0, cash_flow=0.0,
                               price_semantics="OWNER_CLOSE_FILL_SIMULATION" if self.entry_mode == "close" else "OWNER_NEXT_OPEN_SIMULATION")

    def _reject(self, decision: dict, reasons: str | list[str]) -> None:
        reasons = [reasons] if isinstance(reasons, str) else list(dict.fromkeys(reasons))
        if not reasons:
            raise ValueError("rejection needs at least one reason")
        reason = reasons[0]
        decision.update(status="REJECTED", reject_reason=reason, reject_reasons=reasons)
        row = self.ledger.find("fills", decision["order_id"])
        if row is not None:
            row.update(status="REJECTED", cancel=True, reason=reason)

    def _execution_reasons(self, decision: dict, bar: dict | None, previous_close: float) -> list[str]:
        reasons = []
        if self.frozen:
            reasons.append("portfolio_frozen")
        problem = self._bar_problem(bar)
        if problem:
            reasons.append(problem)
        if bar is None:
            return reasons
        price = bar["close"] if self.entry_mode == "close" else bar["open"]
        if not _finite(bar.get("limit_up_price")) or bar["limit_up_price"] <= 0:
            reasons.append("limit_up_price_unavailable")
        if _finite(price) and _finite(decision["price_cap"]) and price > decision["price_cap"]:
            reasons.append("price_cap_exceeded")
        if _finite(bar["open"]) and _finite(previous_close) and bar["open"] > previous_close * 1.05:
            reasons.append("gap_up_over_5pct")
        if _finite(price) and _finite(bar.get("limit_up_price")) and math.isclose(price, bar["limit_up_price"], rel_tol=0, abs_tol=1e-8):
            reasons.append("limit_up")
        if decision["stock"] in self.positions:
            reasons.append("already_held_no_add")
        return reasons

    def prepare_session(self, bars: pd.DataFrame, day: str) -> dict[str, pd.DataFrame]:
        """Write intentions now; reconcile this same session after bars are available."""
        day = _day(day)
        if day not in self.sessions:
            raise ValueError("session not in declared calendar")
        if day in self.plans or day in self.completed:
            return self.ledger.tables()
        if self.plans:
            raise ValueError("reconcile the prior session before preparing another")
        if self.completed and day <= self.completed[-1]:
            raise ValueError("sessions must advance monotonically")
        p = self._prices(bars)
        if set(p.date) - set(self.sessions):
            raise ValueError("bars outside declared calendar")
        today = {r["stock"]: _plain(r) for r in p[p.date == day].to_dict("records")}
        features: dict[str, dict] = {}
        candidates = []
        if self.entry_mode == "next_open":
            for rid, pending in list(self.pending_entries.items()):
                if pending["signal_date"] >= day:
                    continue
                decision = self.ledger.find("decisions", rid)
                bar = today.get(decision["stock"])
                if bar is not None and _finite(bar.get("open")) and _finite(decision["structure_stop"]):
                    price = bar["open"]
                    decision.update(want_price=price, stop_price=max(price * 0.93, decision["structure_stop"]))
                    self.ledger.find("fills", decision["order_id"])["want_price"] = price
                reasons = self._execution_reasons(decision, bar, pending["signal_close"])
                if self.sessions.index(day) != self.sessions.index(pending["signal_date"]) + 1:
                    reasons.append("missed_next_open")
                if reasons:
                    self._reject(decision, reasons)
                else:
                    candidates.append(rid)
                del self.pending_entries[rid]
        for stock, bar in sorted(today.items(), key=lambda item: (
            -float(item[1].get("rs", 0)) if _finite(item[1].get("rs", 0)) else math.inf,
            item[0],
        )):
            feat = _plain(self._features(p, stock, day))
            features[stock] = feat
            available = _day(bar.get("available_date", day))
            data_status = self._bar_problem(bar) or "valid"
            passes = {"source_eligible": bool(bar.get("eligible", True)),
                      "available": available <= day, "valid": data_status == "valid"}
            values = {**feat, "close": bar["close"], "open": bar["open"],
                      "rs": bar.get("rs", 0.0), "source_values": bar.get("condition_values", {})}
            er = self.ledger.add("eligibility", self._id("eligible", day, stock),
                                 date=day, stock=stock, condition_values=values,
                                 condition_passes=passes, source=bar.get("source", "synthetic_fixture"),
                                 available_date=available, eligible=all(passes.values()), data_status=data_status)
            if not feat["trigger"]:
                continue
            trade_id = self._id("trade", day, stock)
            pivot = feat["pivot"]
            price_cap = pivot * 1.05 if pivot is not None else None
            want_price = bar["close"] if self.entry_mode == "close" else None
            stop = max(bar["close"] * 0.93, feat["structure_stop"]) if self.entry_mode == "close" and feat["structure_stop"] is not None else None
            order = self._intent(day=day, stock=stock, trade_id=trade_id, side="buy",
                                 reason="bollinger_breakout", want_price=want_price)
            decision = self.ledger.add("decisions", self._id("decision", day, stock),
                                      date=day, stock=stock, trade_id=trade_id, order_id=order["row_id"],
                                      direction="LONG", trigger="BB21_2.1_UPPER_CROSS", want_price=want_price,
                                      price_cap=price_cap, stop_price=stop, rs=bar.get("rs", 0.0),
                                      pivot=pivot, structure_stop=feat["structure_stop"],
                                      base_sessions=feat["base_sessions"], status="INTENT", reject_reason="", reject_reasons=[])
            reasons = []
            if self.frozen:
                reasons.append("portfolio_frozen")
            if not er["eligible"]:
                reasons.append(data_status if data_status != "valid" else "not_eligible_or_not_available")
            if not _finite(bar.get("rs")):
                reasons.append("rs_unavailable")
            if self.entry_mode == "close" and (not _finite(bar.get("limit_up_price")) or bar["limit_up_price"] <= 0):
                reasons.append("limit_up_price_unavailable")
            if not feat["base_valid"]:
                reasons.append("base_history_missing")
            if feat["base_sessions"] < 10:
                reasons.append("base_too_short")
            if self.entry_mode == "close":
                reasons.extend(self._execution_reasons(decision, bar, feat["prev_close"]))
            elif stock in self.positions:
                reasons.append("already_held_no_add")
            if reasons:
                self._reject(decision, reasons)
            elif self.entry_mode == "next_open":
                decision["status"] = "PENDING_NEXT_OPEN"
                self.pending_entries[decision["row_id"]] = dict(signal_date=day, signal_close=bar["close"])
            else:
                candidates.append(decision["row_id"])
        sell_intents, close_exit_intents = {}, {}
        for stock, pos in self.positions.items():
            bar = today.get(stock)
            if bar is None or pos.truncated or self.frozen:
                continue
            problem = self._bar_problem(bar)
            if problem and problem not in {"suspended", "no_volume"}:
                continue
            if pos.pending_stop:
                sell_intents[stock] = pos.pending_stop
            elif pos.pending_exit and bar["open"] > pos.stop_price:
                sell_intents[stock] = pos.pending_exit
            elif bar["open"] <= pos.stop_price or bar["low"] <= pos.stop_price:
                reason = "stop_gap_open" if bar["open"] <= pos.stop_price else "stop_observed" if _finite(bar.get("stop_fill_price")) else "stop_price_assumption"
                row = self._intent(day=day, stock=stock, trade_id=pos.trade_id, side="sell",
                                   reason=reason, want_price=pos.stop_price, quantity=pos.quantity)
                sell_intents[stock] = row["row_id"]
            else:
                sma = features.get(stock, {}).get("sma20")
                if _finite(sma) and bar["close"] < sma:
                    row = self._intent(day=day, stock=stock, trade_id=pos.trade_id, side="sell",
                                       reason="sma20_next_open", want_price=None, quantity=pos.quantity)
                    close_exit_intents[stock] = row["row_id"]
        self.plans[day] = dict(bars=today, features=features, candidates=candidates,
                               sell_intents=sell_intents, close_exit_intents=close_exit_intents)
        return self.ledger.tables()

    def _charge(self, row: dict, *, price: float, quantity: int, day: str, observed_at: str) -> float:
        gross = price * quantity
        side = row["side"]
        commission = gross * COMMISSION
        tax = gross * TAX if side == "sell" else 0.0
        slip = gross * SLIPPAGE
        cost = FEES.fee(side=side, quantity=quantity, price=price) + slip
        flow = -(gross + cost) if side == "buy" else gross - cost
        row.update(fill=True, status="FILLED", quantity=quantity, fill_price=price,
                   fill_date=day, commission=commission, tax=tax, slippage=slip,
                   cost=cost, cash_flow=flow, reconciled_at=observed_at)
        self.cash += flow
        return flow

    def _truncate(self, pos: Position, day: str, reason: str, ca: Any = None) -> None:
        pos.truncated = True
        self.frozen, self.freeze_reason = True, f"{pos.stock}:{reason}"
        if pos.pending_exit:
            self.ledger.find("fills", pos.pending_exit).update(status="BLOCKED", reason=reason)
        if pos.pending_stop:
            self.ledger.find("fills", pos.pending_stop).update(status="BLOCKED", reason=reason)
        self.ledger.add("fills", self._id(pos.trade_id, "truncated", day),
                        date=day, stock=pos.stock, trade_id=pos.trade_id, side="state",
                        order=False, fill=False, cancel=False, exit=False, cost=0.0,
                        corporate_action=ca, truncated=True, status="TRUNCATED", reason=reason,
                        quantity=pos.quantity, holding_sessions=self.sessions.index(day) - pos.entry_index,
                        price_semantics="OWNER_CLOSE_FILL_SIMULATION" if self.entry_mode == "close" else "OWNER_NEXT_OPEN_SIMULATION")

    def _sell(self, pos: Position, bar: dict, day: str, observed_at: str, *, open_only: bool = False) -> None:
        problem = self._bar_problem(bar)
        locked_down = (_finite(bar.get("limit_down_price")) and
                       math.isclose(bar["open"], bar["high"], abs_tol=1e-8) and
                       math.isclose(bar["high"], bar["low"], abs_tol=1e-8) and
                       math.isclose(bar["low"], bar["limit_down_price"], abs_tol=1e-8))
        staged_id = self.plans[day]["sell_intents"].get(pos.stock)
        if problem in {"suspended", "no_volume"} or locked_down:
            reason = problem or "limit_down_locked"
            if bar["low"] <= pos.stop_price and not pos.pending_stop:
                row = self.ledger.find("fills", staged_id) if staged_id else self._intent(
                    day=day, stock=pos.stock, trade_id=pos.trade_id, side="sell",
                    reason="stop_unexecutable", want_price=pos.stop_price, quantity=pos.quantity)
                row.update(status="BLOCKED", reason=reason)
                pos.pending_stop = row["row_id"]
            elif staged_id:
                self.ledger.find("fills", staged_id).update(status="BLOCKED", reason=reason)
            return
        price = None
        row = None
        reason = ""
        # A pending close exit happens at open; later high/low cannot affect it.
        if pos.pending_stop:
            row = self.ledger.find("fills", pos.pending_stop)
            price, reason = bar["open"], "stop_pending_next_open"
            if pos.pending_exit:
                self.ledger.find("fills", pos.pending_exit).update(status="CANCELLED", cancel=True, reason="stop_priority")
        elif bar["open"] <= pos.stop_price:
            price, reason = bar["open"], "stop_gap_open"
        elif pos.pending_exit:
            row = self.ledger.find("fills", pos.pending_exit)
            price, reason = bar["open"], "sma20_next_open"
        elif not open_only and bar["low"] <= pos.stop_price:
            observed = bar.get("stop_fill_price")
            price = float(observed) if _finite(observed) else pos.stop_price
            if not bar["low"] <= price <= bar["high"] or price > pos.stop_price:
                raise ValueError("stop fill must be an executable price at or below the triggered stop")
            reason = "stop_observed" if _finite(observed) else "stop_price_assumption"
        if price is None:
            return
        if row is None:
            row = self.ledger.find("fills", staged_id) if staged_id else self._intent(
                day=day, stock=pos.stock, trade_id=pos.trade_id,
                side="sell", reason=reason, want_price=pos.stop_price, quantity=pos.quantity)
            if pos.pending_exit:
                self.ledger.find("fills", pos.pending_exit).update(status="CANCELLED", cancel=True, reason="stop_priority")
        row["reason"] = reason
        proceeds = self._charge(row, price=price, quantity=pos.quantity, day=day, observed_at=observed_at)
        row.update(pnl=proceeds - pos.entry_cash, net_return=proceeds / pos.entry_cash - 1,
                   holding_sessions=self.sessions.index(day) - pos.entry_index)
        del self.positions[pos.stock]

    def reconcile_session(self, day: str, *, observed_at: str) -> dict[str, pd.DataFrame]:
        """Backtest immediately or daily on the following close; update original rows."""
        day, observed_at = _day(day), _day(observed_at)
        if observed_at < day:
            raise ValueError("cannot reconcile before the simulated session")
        if day in self.completed:
            return self.ledger.tables()
        if day not in self.plans:
            raise ValueError("session has no saved intentions")
        plan = self.plans[day]
        today, features = plan["bars"], plan["features"]
        for pos in list(self.positions.values()):
            if pos.truncated:
                continue
            bar = today.get(pos.stock)
            problem = self._bar_problem(bar)
            if problem and problem not in {"suspended", "no_volume"}:
                self._truncate(pos, day, problem, (bar or {}).get("corporate_action"))
        blocked = []
        if not self.frozen:
            for pos in list(self.positions.values()):
                self._sell(pos, today[pos.stock], day, observed_at, open_only=self.entry_mode == "next_open")
        candidates = [self.ledger.find("decisions", rid) for rid in plan["candidates"]]
        candidates.sort(key=lambda r: (-float(r["rs"]), r["stock"]))
        # Allocation uses the execution-time mark, never a next-open day's future close.
        price_field = "close" if self.entry_mode == "close" else "open"
        budget_equity = self.cash + sum(pos.quantity * today[pos.stock][price_field]
                                       for pos in self.positions.values() if pos.stock in today)
        for decision in candidates:
            stock = decision["stock"]
            bar = today[stock]
            reasons = []
            if self.frozen:
                reasons.append("portfolio_frozen")
            if stock in self.positions:
                reasons.append("already_held_no_add")
            if len(self.positions) >= 5:
                reasons.append("max_positions")
            target = min(budget_equity * 0.07, budget_equity * 0.25)
            price = bar[price_field]
            per_share = price * (1 + COMMISSION + SLIPPAGE)
            qty = int(math.floor(target / per_share))
            if qty <= 0:
                reasons.append("insufficient_size")
            if qty * per_share > self.cash + 1e-8:
                reasons.append("insufficient_cash")
            if reasons:
                self._reject(decision, reasons)
                blocked.append(dict(stock=stock, trade_id=decision["trade_id"], rs=decision["rs"],
                                    reason=reasons[0], reject_reasons=reasons))
                continue
            row = self.ledger.find("fills", decision["order_id"])
            spent = -self._charge(row, price=price, quantity=qty, day=day, observed_at=observed_at)
            self.positions[stock] = Position(stock, decision["trade_id"], qty, price, spent,
                                             day, self.sessions.index(day), decision["stop_price"])
            decision["status"] = "FILLED"
        if self.entry_mode == "next_open" and not self.frozen:
            # Newly opened holdings can stop intraday. Existing intraday stops must
            # not release a slot or cash before the opening allocation above.
            for pos in list(self.positions.values()):
                self._sell(pos, today[pos.stock], day, observed_at)
        if not self.frozen:
            for stock, pos in list(self.positions.items()):
                bar = today[stock]
                sma = features.get(stock, {}).get("sma20")
                if not pos.pending_exit and not pos.pending_stop and _finite(sma) and bar["close"] < sma:
                    staged_id = plan["close_exit_intents"].get(stock)
                    row = self.ledger.find("fills", staged_id) if staged_id else self._intent(
                        day=day, stock=stock, trade_id=pos.trade_id, side="sell",
                        reason="sma20_next_open", want_price=None, quantity=pos.quantity)
                    pos.pending_exit = row["row_id"]
        else:
            for rid in list(self.pending_entries):
                self._reject(self.ledger.find("decisions", rid), "portfolio_frozen")
                del self.pending_entries[rid]
        equity = None if self.frozen else self.cash + sum(pos.quantity * today[pos.stock]["close"] for pos in self.positions.values())
        if equity is not None:
            self.last_reliable_equity = equity
        self.ledger.add("equity", self._id("equity", day), date=day, cash=self.cash,
                        positions={stock: asdict(pos) for stock, pos in self.positions.items()},
                        equity=equity, blocked_opportunities=blocked, frozen=self.frozen,
                        freeze_reason=self.freeze_reason, last_reliable_equity=self.last_reliable_equity,
                        capital_occupied=sum(p.entry_cash for p in self.positions.values()), reconciled_at=observed_at)
        self.completed.append(day)
        del self.plans[day]
        return self.ledger.tables()

    def finish(self) -> dict[str, pd.DataFrame]:
        if self.plans:
            raise ValueError("unreconciled intentions remain")
        # Open holdings stay holdings: no artificial end-of-sample sale.
        return self.ledger.tables()

    def save(self, path: str | Path) -> None:
        state = dict(sessions=self.sessions, initial_cash=self.initial_cash, cash=self.cash,
                     identity=self.ledger.identity, tables=self.ledger.rows,
                     positions={s: asdict(p) for s, p in self.positions.items()}, plans=self.plans,
                     pending_entries=self.pending_entries,
                     completed=self.completed, frozen=self.frozen, freeze_reason=self.freeze_reason,
                     last_reliable_equity=self.last_reliable_equity)
        Path(path).write_text(json.dumps(_plain(state), ensure_ascii=False, allow_nan=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> TradingPlanR1:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
        identity = state["identity"]
        if identity["source_kind"] != "synthetic" or identity["rule_version"] != RULE_VERSION:
            raise ValueError("unsupported saved source or rule version")
        engine = cls(run_id=identity["run_id"], mode=identity["mode"], sessions=state["sessions"],
                     initial_cash=state["initial_cash"], portfolio_id=identity["portfolio_id"], entry_mode=identity["entry_mode"])
        engine.ledger.rows = state["tables"]
        engine.positions = {s: Position(**p) for s, p in state["positions"].items()}
        for key in ("cash", "plans", "pending_entries", "completed", "frozen", "freeze_reason", "last_reliable_equity"):
            setattr(engine, key, state[key])
        validate_tables(engine.ledger.tables())
        return engine


def validate_tables(tables: dict[str, pd.DataFrame]) -> None:
    if set(tables) != set(SCHEMAS):
        raise ValueError("exactly four ledger tables are required")
    for name, frame in tables.items():
        if tuple(frame.columns) != SCHEMAS[name]:
            raise ValueError(f"{name} schema mismatch")
        if frame.duplicated(["run_id", "portfolio_id", "row_id"]).any():
            raise ValueError(f"duplicate {name} rows; concat distinct runs, not repeated snapshots")
        if not frame.source_kind.eq("synthetic").all() or not frame.rule_version.eq(RULE_VERSION).all():
            raise ValueError("synthetic R1 ledger required")


def concat_ledgers(*ledgers: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    for tables in ledgers:
        validate_tables(tables)
    joined = {name: pd.concat([t[name] for t in ledgers], ignore_index=True) for name in SCHEMAS}
    validate_tables(joined)
    return joined


def load_tables(directory: str | Path, *, prefix: str = "synthetic_") -> dict[str, pd.DataFrame]:
    """Restore exported CSV types, including nested conditions and positions."""
    tables = {}
    for name, columns in SCHEMAS.items():
        strings = {c: "string" for c in columns if c not in FLOAT_COLUMNS | BOOL_COLUMNS | OBJECT_COLUMNS}
        frame = pd.read_csv(Path(directory) / f"{prefix}{name}.csv", dtype=strings)
        for col in frame:
            if col in OBJECT_COLUMNS:
                frame[col] = frame[col].map(lambda v: json.loads(v) if isinstance(v, str) else None)
            elif col in FLOAT_COLUMNS:
                frame[col] = pd.array(frame[col], dtype="Float64")
            elif col in BOOL_COLUMNS:
                frame[col] = pd.array(frame[col], dtype="boolean")
        tables[name] = frame
    validate_tables(tables)
    return tables


def load_r1_config(path: str | Path) -> dict:
    import yaml
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("entry_mode") not in {"close", "next_open"}:
        raise ValueError("config entry_mode must be close or next_open")
    if config.get("bollinger") != {"window": 21, "stddev": 2.1, "ddof": 0}:
        raise ValueError("owner's Bollinger 21/2.1/ddof=0 parameters are fixed")
    return config


def metrics(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One metrics path for either mode or their concatenation; report each run."""
    validate_tables(tables)
    fills, equity, decisions = tables["fills"], tables["equity"], tables["decisions"]
    rows = []
    groups = sorted(set(zip(fills.run_id, fills.portfolio_id)) | set(zip(equity.run_id, equity.portfolio_id)))
    for run, portfolio in groups:
        f = fills[(fills.run_id == run) & (fills.portfolio_id == portfolio)]
        e = equity[(equity.run_id == run) & (equity.portfolio_id == portfolio)].sort_values("date")
        d = decisions[(decisions.run_id == run) & (decisions.portfolio_id == portfolio)]
        reason_counts = {}
        for reasons in d.loc[d.status.eq("REJECTED"), "reject_reasons"]:
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        buys = f[f.side.eq("buy") & f.fill.fillna(False)]
        closed = f[f.side.eq("sell") & f.fill.fillna(False)]
        censored = set(f.loc[f.truncated.fillna(False), "trade_id"])
        closed_ids = set(closed.trade_id)
        open_ids = set(buys.trade_id) - closed_ids - censored
        returns = closed.net_return.dropna().astype(float)
        winners, losers = returns[returns > 0], returns[returns < 0]
        avg_win = float(winners.mean()) if len(winners) else None
        avg_loss = float(-losers.mean()) if len(losers) else None
        holdings = closed.holding_sessions.dropna().astype(float)
        last_positions = e.iloc[-1].positions if len(e) else {}
        occupied_days = float(holdings.sum())
        if len(e):
            day_index = {d: i for i, d in enumerate(e.date)}
            for pos in last_positions.values():
                entry_day = pos["entry_date"]
                occupied_days += max(0, len(e) - 1 - day_index.get(entry_day, 0))
        frozen = bool(e.frozen.fillna(False).any()) if len(e) else False
        rows.append(dict(run_id=run, portfolio_id=portfolio,
                         entry_mode=str(e.iloc[-1].entry_mode) if len(e) else str(f.iloc[0].entry_mode),
                         closed_count=len(returns),
                         net_win_rate=float((returns > 0).mean()) if len(returns) else None,
                         avg_win=avg_win, avg_loss=avg_loss,
                         payoff_ratio=avg_win / avg_loss if avg_win is not None and avg_loss else None,
                         expectancy=float(returns.mean()) if len(returns) else None,
                         median_holding_sessions=float(holdings.median()) if len(holdings) else None,
                         capital_occupied_position_days=None if frozen else occupied_days,
                         open_count=len(open_ids), truncated_count=len(censored),
                         rejected_count=int(f.status.eq("REJECTED").sum()),
                         pending_entry_count=int((f.side.eq("buy") & f.status.eq("INTENT")).sum()),
                         reject_reason_counts=reason_counts,
                         portfolio_frozen=frozen,
                         final_equity=None if frozen or not len(e) else float(e.iloc[-1].equity),
                         metrics_scope="synthetic_entry_mode_simulation"))
    return pd.DataFrame(rows)


def run_backtest(bars: pd.DataFrame, *, run_id: str, sessions: list[str], start: str, entry_mode: str = "close") -> TradingPlanR1:
    engine = TradingPlanR1(run_id=run_id, mode="backtest", sessions=sessions, entry_mode=entry_mode)
    for day in engine.sessions:
        if day >= _day(start):
            engine.prepare_session(bars, day)
            engine.reconcile_session(day, observed_at=day)
    engine.finish()
    return engine


def run_daily(bars: pd.DataFrame, *, run_id: str, sessions: list[str], start: str, entry_mode: str = "close") -> TradingPlanR1:
    engine = TradingPlanR1(run_id=run_id, mode="daily", sessions=sessions, entry_mode=entry_mode)
    previous = None
    for day in engine.sessions:
        if day < _day(start):
            continue
        if previous is not None:
            engine.reconcile_session(previous, observed_at=day)
        engine.prepare_session(bars, day)
        previous = day
    if previous is not None:
        # Only the reconciliation timestamp advances; no fabricated future bar.
        engine.reconcile_session(previous, observed_at=_day(pd.Timestamp(previous) + pd.offsets.BDay()))
    engine.finish()
    return engine
