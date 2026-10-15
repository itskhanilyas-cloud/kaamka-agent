"""Monthly spend cap. Every paid call must pass `reserve()` first."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import SpendEntry, utcnow
from . import audit


class BudgetExceeded(Exception):
    pass


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def spent_this_month(db: Session, now: datetime | None = None) -> float:
    now = now or utcnow()
    total = db.scalar(select(func.coalesce(func.sum(SpendEntry.amount_inr), 0.0))
                      .where(SpendEntry.at >= _month_start(now)))
    return round(float(total), 2)


def reserve(db: Session, category: str, estimated_inr: float, cap_inr: float, actor: str,
            note: str | None = None) -> SpendEntry:
    """Record an estimated cost, refusing if it would push the month over the cap."""
    if estimated_inr < 0:
        raise ValueError("cost cannot be negative")
    spent = spent_this_month(db)
    if spent + estimated_inr > cap_inr:
        audit.record(db, actor, "budget_blocked", category, spent=spent, requested=estimated_inr, cap=cap_inr)
        raise BudgetExceeded(f"₹{estimated_inr:.2f} would exceed the ₹{cap_inr:.0f} monthly cap (₹{spent:.2f} spent)")
    entry = SpendEntry(category=category, amount_inr=estimated_inr, is_estimate=True, note=note)
    db.add(entry)
    db.flush()
    return entry
