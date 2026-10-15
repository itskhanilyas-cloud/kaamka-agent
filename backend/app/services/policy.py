"""Owner-only policy switches (auto-publish, etc.).

The agent and background jobs run as SYSTEM_ACTOR and can read policies but
never write them, so the system cannot loosen its own rules.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Policy, utcnow
from . import audit

SYSTEM_ACTOR = "system:agent"

DEFAULTS: dict[str, dict] = {
    # Off by default. Even when on, it only skips the per-post click for posts
    # whose kind is listed; it never applies outside production.
    "auto_publish": {"enabled": False, "allowed_media_types": []},
}


class PolicyChangeForbidden(PermissionError):
    pass


def get_policy(db: Session, key: str) -> dict:
    row = db.scalar(select(Policy).where(Policy.key == key))
    return dict(row.value) if row else dict(DEFAULTS[key])


def set_policy(db: Session, key: str, value: dict, actor: str, owner_email: str) -> dict:
    if actor != owner_email:
        audit.record(db, actor, "policy_change_denied", key, attempted=value)
        raise PolicyChangeForbidden(f"only the owner can change policy '{key}'")
    if key not in DEFAULTS:
        raise KeyError(key)
    row = db.scalar(select(Policy).where(Policy.key == key))
    before = dict(row.value) if row else dict(DEFAULTS[key])
    if row is None:
        row = Policy(key=key, value=value, updated_by=actor)
        db.add(row)
    else:
        row.value, row.updated_by, row.updated_at = value, actor, utcnow()
    audit.record(db, actor, "policy_changed", key, before=before, after=value)
    return value
