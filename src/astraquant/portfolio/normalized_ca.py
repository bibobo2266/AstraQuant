"""File-bound FinMind dividend instructions for the existing S3 replay."""
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from astraquant.data.corporate_actions import build_finmind_normalized_actions, NormalizedCorporateActionKind


def _digest(actions):
    return hashlib.sha256(json.dumps([asdict(a) for a in actions],sort_keys=True,default=str).encode()).hexdigest()


class NormalizedCA:
    def __init__(self, path):
        self.path = Path(path)
        self.binding = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.actions = tuple(build_finmind_normalized_actions(pd.read_parquet(self.path)))
        self._actions_sha = _digest(self.actions)

    def verify(self):
        if (hashlib.sha256(self.path.read_bytes()).hexdigest() != self.binding
                or _digest(self.actions) != self._actions_sha):
            raise ValueError('changed bound normalized corporate actions')

    def resolve(self, ticker, day):
        self.verify()
        actions = tuple(a for a in self.actions if a.ticker==ticker and str(a.effective_date)==day)
        if not actions or len({a.kind for a in actions}) != len(actions):
            raise ValueError('missing or ambiguous normalized source event')
        return tuple(sorted(actions,key=lambda a:a.kind.value))  # cash before stock

    def expected_records(self, *, ticker, day, quantity, stop_price):
        actions = self.resolve(ticker,day)
        at = datetime.fromisoformat(day+'T09:00:00')
        stop = stop_price
        records = []
        # Preflight the entire same-day bundle before any cash/share mutation.
        for action in actions:
            if action.known_at is None or action.known_at > at or action.known_at.date()>action.effective_date:
                raise ValueError('normalized source event is not point-in-time safe')
            event_id=f'normalized:{ticker}:{day}:{action.kind.value}'
            old_quantity, old_stop = quantity, stop
            cash = 0.
            if action.kind is NormalizedCorporateActionKind.CASH_DIVIDEND:
                value=action.cash_per_share
                if (value is None or not math.isfinite(value) or value<=0 or action.payment_at is None
                        or action.payment_at.date()<action.effective_date):
                    raise ValueError('normalized payment/amount evidence is UNKNOWN')
                cash=quantity*value
                stop-=value
            elif action.kind is NormalizedCorporateActionKind.STOCK_DIVIDEND:
                value=action.share_multiplier
                if value is None or not math.isfinite(value) or value<=0:
                    raise ValueError('normalized share ratio evidence is UNKNOWN')
                shares=Decimal(str(quantity))*Decimal(str(value))
                if shares != shares.to_integral_value():
                    raise ValueError('normalized fractional-share terms are UNKNOWN')
                quantity=float(shares)
                stop/=value
            else:
                raise ValueError('unsupported normalized corporate action')
            if not math.isfinite(stop) or stop<=0:
                raise ValueError('normalized equivalent stop is not positive')
            records.append(dict(kind='normalized_ca',ticker=ticker,day=day,binding=self.binding,
                action_kind=action.kind.value,source_row=action.source_row,event_id=event_id,
                old_quantity=old_quantity,new_quantity=quantity,cash_receivable=cash,
                old_stop=old_stop,new_stop=stop))
        return records

    def apply(self, *, replay, ticker, day, stop_price):
        actions = self.resolve(ticker,day)
        records = self.expected_records(ticker=ticker,day=day,
            quantity=replay.portfolio.positions.positions[ticker].quantity,stop_price=stop_price)
        ca = replay.portfolio.corporate_actions
        for record in records:
            event_id = record['event_id']
            if (event_id in ca.dividend_receivables or event_id in ca.completed_dividends
                    or event_id in ca.share_mutations or event_id in replay.portfolio.positions.applied_share_mutation_ids):
                raise ValueError('duplicate normalized corporate-action replay')
        for action in actions:
            replay.apply_normalized_action(action,applied_at=datetime.fromisoformat(day+'T09:00:00'))
        return records

    def pay_due(self, *, replay, day):
        self.verify()
        at=datetime.fromisoformat(day)
        paid=[]
        for event_id,r in list(replay.portfolio.corporate_actions.dividend_receivables.items()):
            if event_id.startswith('normalized:') and r.payment_at is not None and r.payment_at<=at:
                replay.pay_cash_dividend(event_id,at)
                paid.append(dict(kind='normalized_ca_payment',event_id=event_id,day=day,amount=r.amount))
        return paid
