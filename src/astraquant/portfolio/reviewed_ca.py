"""Input-bound accounting for the independently reviewed official event overlay."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from astraquant.portfolio.corporate_actions import CorporateActionEvent, CorporateActionType

OVERLAY_SHA = "1c1917620f3f7fe7d266d488588b3872c540c8adfa27beb3b84b422009f2c4d4"
BASE_SHA = "78d481ef10a3e3e6691d803ecf2805a8096b1c4bec4f63ac4faf717c8785300c"
REVIEW = "6061085838"
ACCEPTED_KEY = ("1315", "2020-10-26")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class ReviewedReduction:
    binding: str
    event: CorporateActionEvent


class ReviewedCA:
    """Revalidate original evidence before mutation; never elevate partial rows."""

    def __init__(self, overlay, base, *, engineering_fixture=False):
        self.overlay, self.base = Path(overlay), Path(base)
        self.engineering_fixture = engineering_fixture
        self._base_sha = sha(self.base) if engineering_fixture else BASE_SHA
        self.verify()
        self.binding = hashlib.sha256((OVERLAY_SHA + self._base_sha + REVIEW).encode()).hexdigest()

    def verify(self):
        if sha(self.overlay) != OVERLAY_SHA or sha(self.base) != self._base_sha:
            raise ValueError("reviewed corporate-action input hash mismatch")
        data = json.loads(self.overlay.read_text())
        for original in data["originals"]:
            path = (self.overlay.parent / original["path"]).resolve()
            path.relative_to(self.overlay.parent.resolve())
            if path.stat().st_size != original["bytes"] or sha(path) != original["sha256"]:
                raise ValueError("reviewed corporate-action physical evidence mismatch")

    def resolve(self, ticker, day):
        self.verify()
        if (str(ticker), str(day)) != ACCEPTED_KEY:
            raise ValueError("corporate action lacks complete reviewed physical evidence")
        base = pd.read_csv(self.base, dtype={"stock_id": str})
        rows = base[base.stock_id.eq(str(ticker)) & base.event_date.eq(str(day))]
        if len(rows) != 1 or rows.iloc[0].event_type != "capital_reduction":
            raise ValueError("reviewed corporate-action source key mismatch")
        row = next(e for e in json.loads(self.overlay.read_text())["events"]
                   if (e["stock_id"], e["source_event_date"]) == ACCEPTED_KEY)
        f = row["verified_fields"]
        # The engine uses naive Asia/Taipei wall time, as do canonical sessions.
        known = pd.Timestamp(f["announcement_at"]).tz_convert("Asia/Taipei").tz_localize(None).to_pydatetime()
        effective = datetime.fromisoformat(f["event_date"])
        payment = datetime.fromisoformat(f["payment_date"])
        if known > effective or payment < effective:
            raise ValueError("unsafe reviewed corporate-action availability/payment date")
        return ReviewedReduction(self.binding, CorporateActionEvent(
            event_id=f"reviewed:{ticker}:{day}:capital_reduction", ticker=str(ticker),
            event_type=CorporateActionType.CAPITAL_REDUCTION, effective_at=effective,
            known_at=known, payment_at=payment, cash_per_share=f["cash_per_share"],
            share_multiplier=f["share_multiplier"], source=f"official_overlay:{self.binding}:review:{REVIEW}"))

    def apply(self, *, portfolio, ticker, day, stop_price):
        action = self.resolve(ticker, day)
        event = action.event
        ca = portfolio.corporate_actions
        if event.event_id in ca.share_mutations or event.event_id in portfolio.positions.applied_share_mutation_ids:
            raise ValueError("duplicate reviewed corporate-action replay")
        position = portfolio.positions.positions.get(ticker)
        old = 0.0 if position is None else position.quantity
        if not math.isfinite(old) or old < 0:
            raise ValueError("invalid reviewed corporate-action opening quantity")
        quantity = Decimal(str(old)) * Decimal(str(event.share_multiplier))
        # Five reviewed fields do not establish fractional-share cash-out terms.
        # Refuse BEFORE either receivable or share-count mutation.
        if quantity != quantity.to_integral_value():
            raise ValueError("fractional-share settlement lacks reviewed physical evidence")
        if stop_price is not None and (not math.isfinite(stop_price) or stop_price <= event.cash_per_share):
            raise ValueError("equivalent stop lacks positive supported price")
        new_stop = None if stop_price is None else (stop_price - event.cash_per_share) / event.share_multiplier
        if event.event_id in ca.cash_entitlement_receivables or event.event_id in ca.completed_cash_entitlements:
            raise ValueError("duplicate reviewed corporate-action cash entitlement")
        ca.accrue_cash_entitlement(event=event, shares_entitled=old,
            accrued_at=event.effective_at, component="CAPITAL_REDUCTION_REFUND")
        ca.apply_share_multiplier(event=event, positions=portfolio.positions, applied_at=event.effective_at)
        return dict(kind="reviewed_ca", ticker=ticker, day=day, binding=action.binding,
                    old_quantity=old, new_quantity=float(quantity), cash_receivable=old * event.cash_per_share,
                    old_stop=stop_price, new_stop=new_stop, event_id=event.event_id)

    def pay_due(self, *, portfolio, day):
        self.verify()
        at = datetime.fromisoformat(day)
        paid = []
        for event_id, r in list(portfolio.corporate_actions.cash_entitlement_receivables.items()):
            if not event_id.startswith("reviewed:"):
                continue
            if r.payment_at is not None and r.payment_at <= at:
                portfolio.corporate_actions.pay_cash_entitlement(event_id, paid_at=at)
                paid.append(dict(kind="reviewed_ca_payment", event_id=event_id, day=day, amount=r.amount))
        return paid
