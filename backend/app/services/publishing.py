"""Publish worker: publishes approved, due posts exactly once.

Safety rules enforced here, not in prompts:
- Only `approved` publish_post requests are ever published.
- Outside production the publisher is always a dry run; nothing reaches Instagram.
- A request is claimed with a conditional UPDATE so two workers cannot publish it twice.
- A rolling 24-hour cap (KA_MAX_POSTS_PER_DAY) is enforced before every publish.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import ActionKind, ActionRequest, ActionStatus, Post, PostStatus, utcnow
from . import audit
from .policy import SYSTEM_ACTOR

MAX_ATTEMPTS = 3


class TransientPublishError(Exception):
    """Network blip, rate limit, container still processing: safe to retry."""


class PermanentPublishError(Exception):
    """Invalid media, expired permission, daily cap hit at Meta: do not retry."""


class Publisher(Protocol):
    def publish(self, post: Post, idempotency_key: str) -> str: ...


class DryRunPublisher:
    """Used in development and test. Records what would be published, returns a fake id."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def publish(self, post: Post, idempotency_key: str) -> str:
        self.calls.append((post.id, idempotency_key))
        return f"dryrun-{idempotency_key[:8]}"


def get_publisher(settings: Settings, real: Publisher | None = None) -> Publisher:
    if settings.app_env != "production" or real is None:
        return DryRunPublisher()
    return real


@dataclass
class RunResult:
    published: int = 0
    skipped_cap: int = 0
    retried: int = 0
    failed: int = 0


def published_last_24h(db: Session, now: datetime) -> int:
    return db.scalar(select(func.count()).select_from(Post)
                     .where(Post.status == PostStatus.published, Post.published_at >= now - timedelta(hours=24))) or 0


def _claim(db: Session, req: ActionRequest) -> bool:
    res = db.execute(update(ActionRequest)
                     .where(ActionRequest.id == req.id, ActionRequest.status == ActionStatus.approved,
                            ActionRequest.attempts == req.attempts)
                     .values(attempts=req.attempts + 1))
    db.flush()
    if res.rowcount == 1:
        db.refresh(req)
        return True
    return False


def run_due(db: Session, publisher: Publisher, settings: Settings, now: datetime | None = None) -> RunResult:
    now = now or utcnow()
    result = RunResult()
    due = db.scalars(select(ActionRequest).join(Post, ActionRequest.post_id == Post.id)
                     .where(ActionRequest.kind == ActionKind.publish_post,
                            ActionRequest.status == ActionStatus.approved,
                            (Post.scheduled_at.is_(None)) | (Post.scheduled_at <= now))
                     .order_by(Post.scheduled_at)).all()
    for req in due:
        post = req.post
        if post.ig_media_id:  # already live: never publish twice
            req.status = ActionStatus.executed
            continue
        if published_last_24h(db, now) >= settings.max_posts_per_day:
            result.skipped_cap += 1
            audit.record(db, SYSTEM_ACTOR, "publish_deferred_daily_cap", req.id)
            continue
        if not _claim(db, req):
            continue
        try:
            media_id = publisher.publish(post, req.idempotency_key)
        except TransientPublishError as e:
            post.last_error = str(e)
            if req.attempts >= MAX_ATTEMPTS:
                req.status, post.status = ActionStatus.failed, PostStatus.failed
                result.failed += 1
                audit.record(db, SYSTEM_ACTOR, "publish_failed", req.id, error=str(e), attempts=req.attempts)
            else:
                result.retried += 1
                audit.record(db, SYSTEM_ACTOR, "publish_retry_scheduled", req.id, error=str(e), attempts=req.attempts)
            continue
        except PermanentPublishError as e:
            req.status, post.status, post.last_error = ActionStatus.failed, PostStatus.failed, str(e)
            result.failed += 1
            audit.record(db, SYSTEM_ACTOR, "publish_failed", req.id, error=str(e), attempts=req.attempts)
            continue
        post.ig_media_id, post.published_at, post.status = media_id, now, PostStatus.published
        req.status = ActionStatus.executed
        result.published += 1
        audit.record(db, SYSTEM_ACTOR, "post_published", post.id, ig_media_id=media_id,
                     dry_run=media_id.startswith("dryrun-"))
    db.flush()
    return result
