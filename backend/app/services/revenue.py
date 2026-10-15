"""Revenue and profit summary. Confirmed and estimated figures are never mixed."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RevenueEntry, SpendEntry

SOURCES = {"affiliate", "sponsorship", "digital_product", "referral", "ads", "other"}


def add_revenue(db: Session, source: str, amount_inr: float, confirmed: bool, evidence: str | None,
                post_id: str | None = None) -> RevenueEntry:
    if source not in SOURCES:
        raise ValueError(f"unknown source '{source}'")
    if amount_inr < 0:
        raise ValueError("amount cannot be negative")
    if confirmed and not evidence:
        raise ValueError("confirmed revenue needs evidence (statement, payout id or invoice)")
    entry = RevenueEntry(source=source, amount_inr=amount_inr, confirmed=confirmed, evidence=evidence, post_id=post_id)
    db.add(entry)
    db.flush()
    return entry


def summary(db: Session) -> dict:
    rev = db.scalars(select(RevenueEntry)).all()
    spend = db.scalars(select(SpendEntry)).all()
    confirmed = round(sum(r.amount_inr for r in rev if r.confirmed), 2)
    estimated = round(sum(r.amount_inr for r in rev if not r.confirmed), 2)
    by_source: dict[str, dict[str, float]] = {}
    for r in rev:
        s = by_source.setdefault(r.source, {"confirmed": 0.0, "estimated": 0.0})
        s["confirmed" if r.confirmed else "estimated"] = round(s["confirmed" if r.confirmed else "estimated"] + r.amount_inr, 2)
    costs = round(sum(s.amount_inr for s in spend), 2)
    return {
        "revenue_confirmed_inr": confirmed,
        "revenue_estimated_inr": estimated,
        "costs_inr": costs,
        "profit_confirmed_inr": round(confirmed - costs, 2),
        "profit_if_estimates_land_inr": round(confirmed + estimated - costs, 2),
        "by_source": by_source,
    }
