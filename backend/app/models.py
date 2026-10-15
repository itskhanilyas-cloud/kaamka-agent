"""Database schema (SQLAlchemy 2.x). PostgreSQL in Azure, SQLite locally and in tests."""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    scheduled = "scheduled"
    published = "published"
    rejected = "rejected"
    failed = "failed"


class MediaType(str, enum.Enum):
    image = "IMAGE"
    carousel = "CAROUSEL"
    reel = "REELS"
    story = "STORIES"


class ActionKind(str, enum.Enum):
    """Every consequential action the system can take. All require owner approval."""
    publish_post = "publish_post"
    reply_comment = "reply_comment"
    send_dm = "send_dm"
    spend = "spend"
    link_account = "link_account"
    grant_permission = "grant_permission"
    change_setting = "change_setting"
    change_affiliate_link = "change_affiliate_link"
    delete_content = "delete_content"
    financial_commitment = "financial_commitment"


class ActionStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"
    failed = "failed"


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType))
    caption: Mapped[str] = mapped_column(Text, default="")
    media_urls: Mapped[list] = mapped_column(JSON, default=list)  # blob paths, not public URLs
    pillar: Mapped[str | None] = mapped_column(String(64))
    has_affiliate_link: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[PostStatus] = mapped_column(Enum(PostStatus), default=PostStatus.draft)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ig_media_id: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)
    # Structured draft from the Content Studio: hook, slides or Reel script, alt text, hashtags.
    content: Mapped[dict | None] = mapped_column(JSON)
    quality: Mapped[dict | None] = mapped_column(JSON)
    generated_by: Mapped[str | None] = mapped_column(String(64))  # model name, or "MOCK"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActionRequest(Base):
    __tablename__ = "action_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[ActionKind] = mapped_column(Enum(ActionKind))
    status: Mapped[ActionStatus] = mapped_column(Enum(ActionStatus), default=ActionStatus.pending)
    post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id"))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by: Mapped[str] = mapped_column(String(255))
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    # One execution per approved action, ever (duplicate-publishing protection).
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, default=_uuid)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    post: Mapped[Post | None] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(255))
    event: Mapped[str] = mapped_column(String(64))
    target: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class SpendEntry(Base):
    __tablename__ = "spend"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    category: Mapped[str] = mapped_column(String(32))  # text_ai, image_ai, video_ai, tts, infra, ads, subscription
    amount_inr: Mapped[float] = mapped_column(Float)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)


class RevenueEntry(Base):
    __tablename__ = "revenue"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(32))  # affiliate, sponsorship, digital_product, referral, ads
    amount_inr: Mapped[float] = mapped_column(Float)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)  # True only with a statement/payout as evidence
    evidence: Mapped[str | None] = mapped_column(Text)
    post_id: Mapped[str | None] = mapped_column(ForeignKey("posts.id"))


class Policy(Base):
    """Owner-controlled switches. Only the owner may change them; never the agent."""
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[dict] = mapped_column(JSON)
    updated_by: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
