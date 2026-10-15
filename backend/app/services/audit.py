"""Append-only audit log with secret redaction."""
import re
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditLog

_SECRET_KEYS = re.compile(r"(token|secret|password|api[_-]?key|authorization|cookie)", re.I)
_SECRET_VALUES = [
    re.compile(r"EAA[A-Za-z0-9]{20,}"),          # Meta access tokens
    re.compile(r"IG[A-Za-z0-9]{30,}"),           # Instagram tokens
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),        # generic API keys
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.I),
]


def redact(value: Any) -> Any:
    """Return a copy of value with anything secret-looking replaced by '***'."""
    if isinstance(value, dict):
        return {k: ("***" if _SECRET_KEYS.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        for pattern in _SECRET_VALUES:
            value = pattern.sub("***", value)
        return value
    return value


def record(db: Session, actor: str, event: str, target: str | None = None, **detail: Any) -> AuditLog:
    entry = AuditLog(actor=actor, event=event, target=target, detail=redact(detail))
    db.add(entry)
    db.flush()
    return entry
