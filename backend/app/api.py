"""REST API used by the dashboard. Every route requires the signed-in owner."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .models import ActionKind, ActionRequest, ActionStatus, AuditLog, MediaType, Post, PostStatus
from .security import require_owner
from .services import approvals, budget, policy, revenue

router = APIRouter(prefix="/api", dependencies=[Depends(require_owner)])


class PostIn(BaseModel):
    media_type: MediaType
    caption: str = ""
    media_urls: list[str] = Field(default_factory=list)
    pillar: str | None = None
    has_affiliate_link: bool = False
    scheduled_at: datetime | None = None


class PostEdit(BaseModel):
    caption: str | None = None
    media_urls: list[str] | None = None
    scheduled_at: datetime | None = None
    has_affiliate_link: bool | None = None


class Decision(BaseModel):
    approve: bool
    note: str | None = None


class PolicyIn(BaseModel):
    value: dict


class RevenueIn(BaseModel):
    source: str
    amount_inr: float
    confirmed: bool = False
    evidence: str | None = None
    post_id: str | None = None


class GenerateIn(BaseModel):
    idea: str
    media_type: MediaType
    pillar: str
    variants: int = 3
    has_affiliate_link: bool = False
    test_notes: str | None = None


def _post_out(p: Post) -> dict:
    return {"id": p.id, "media_type": p.media_type.value, "caption": p.caption, "media_urls": p.media_urls,
            "pillar": p.pillar, "has_affiliate_link": p.has_affiliate_link, "status": p.status.value,
            "scheduled_at": p.scheduled_at, "published_at": p.published_at, "ig_media_id": p.ig_media_id,
            "last_error": p.last_error, "content": p.content, "quality": p.quality,
            "generated_by": p.generated_by, "is_mock": p.generated_by == "MOCK",
            "checks": approvals.check_post_ready(p)}


@router.post("/studio/generate", status_code=201)
def studio_generate(body: GenerateIn, db: Session = Depends(get_db), user: str = Depends(require_owner),
                    settings: Settings = Depends(get_settings)):
    from .ai import generator, providers

    try:
        provider = providers.get_text_provider(settings)
        drafts = generator.generate(
            db, provider, idea=body.idea, media_type=body.media_type.value, pillar=body.pillar,
            variants=body.variants, has_affiliate_link=body.has_affiliate_link, test_notes=body.test_notes,
            pricing=generator.Pricing(settings.text_price_in_inr_per_m, settings.text_price_out_inr_per_m),
            monthly_cap_inr=settings.monthly_budget_inr, max_output_tokens=settings.text_max_output_tokens,
            actor=user)
    except generator.GenerationError as e:
        db.rollback()
        raise HTTPException(422, str(e))
    except budget.BudgetExceeded as e:
        db.commit()  # keep the audit record of the block
        raise HTTPException(402, str(e))
    except providers.ProviderError as e:
        db.commit()
        raise HTTPException(502, str(e))
    db.commit()
    return {"provider": provider.name, "drafts": drafts}


def _req_out(r: ActionRequest) -> dict:
    return {"id": r.id, "kind": r.kind.value, "status": r.status.value, "post_id": r.post_id,
            "payload": r.payload, "requested_by": r.requested_by, "decided_by": r.decided_by,
            "decided_at": r.decided_at, "created_at": r.created_at}


@router.get("/overview")
def overview(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    counts = {s.value: 0 for s in PostStatus}
    for p in db.scalars(select(Post)).all():
        counts[p.status.value] += 1
    pending = db.query(ActionRequest).filter(ActionRequest.status == ActionStatus.pending).count()
    return {"environment": settings.app_env, "posts_by_status": counts, "pending_approvals": pending,
            "spent_this_month_inr": budget.spent_this_month(db), "monthly_budget_inr": settings.monthly_budget_inr,
            "auto_publish": policy.get_policy(db, "auto_publish"),
            "instagram_connected": False, "data_note": "Instagram metrics appear after Phase 6 connects your account."}


@router.post("/posts", status_code=201)
def create_post(body: PostIn, db: Session = Depends(get_db), user: str = Depends(require_owner)):
    p = Post(**body.model_dump(), status=PostStatus.draft)
    db.add(p)
    db.flush()
    from .services import audit
    audit.record(db, user, "post_created", p.id)
    db.commit()
    return _post_out(p)


@router.get("/posts")
def list_posts(status: PostStatus | None = None, db: Session = Depends(get_db)):
    q = select(Post).order_by(Post.created_at.desc())
    if status:
        q = q.where(Post.status == status)
    return [_post_out(p) for p in db.scalars(q).all()]


@router.patch("/posts/{post_id}")
def edit_post(post_id: str, body: PostEdit, db: Session = Depends(get_db), user: str = Depends(require_owner)):
    p = db.get(Post, post_id) or _404()
    if p.status in (PostStatus.published,):
        raise HTTPException(409, "published posts cannot be edited here")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(p, k, v)
    from .services import audit
    audit.record(db, user, "post_edited", p.id, fields=sorted(changes))
    db.commit()
    return _post_out(p)


@router.post("/posts/{post_id}/submit", status_code=201)
def submit_for_approval(post_id: str, db: Session = Depends(get_db), user: str = Depends(require_owner)):
    p = db.get(Post, post_id) or _404()
    if p.status not in (PostStatus.draft, PostStatus.rejected, PostStatus.failed):
        raise HTTPException(409, f"post is {p.status.value}")
    try:
        req = approvals.request_action(db, ActionKind.publish_post, user, post=p)
    except approvals.ApprovalError as e:
        raise HTTPException(422, str(e))
    db.commit()
    return _req_out(req)


@router.get("/approvals")
def list_approvals(status: ActionStatus | None = ActionStatus.pending, db: Session = Depends(get_db)):
    q = select(ActionRequest).order_by(ActionRequest.created_at.desc())
    if status:
        q = q.where(ActionRequest.status == status)
    return [_req_out(r) | {"post": _post_out(r.post) if r.post else None} for r in db.scalars(q).all()]


@router.post("/approvals/{req_id}/decision")
def decide(req_id: str, body: Decision, db: Session = Depends(get_db), user: str = Depends(require_owner),
           settings: Settings = Depends(get_settings)):
    req = db.get(ActionRequest, req_id) or _404()
    try:
        approvals.decide(db, req, user, settings.owner_email.lower(), body.approve, body.note)
    except approvals.ApprovalError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return _req_out(req)


@router.get("/policies/{key}")
def read_policy(key: str, db: Session = Depends(get_db)):
    if key not in policy.DEFAULTS:
        _404()
    return policy.get_policy(db, key)


@router.put("/policies/{key}")
def write_policy(key: str, body: PolicyIn, db: Session = Depends(get_db), user: str = Depends(require_owner),
                 settings: Settings = Depends(get_settings)):
    if key not in policy.DEFAULTS:
        _404()
    value = policy.set_policy(db, key, body.value, user, settings.owner_email.lower())
    db.commit()
    return value


@router.get("/revenue/summary")
def revenue_summary(db: Session = Depends(get_db)):
    return revenue.summary(db)


@router.post("/revenue", status_code=201)
def add_revenue(body: RevenueIn, db: Session = Depends(get_db), user: str = Depends(require_owner)):
    try:
        e = revenue.add_revenue(db, body.source, body.amount_inr, body.confirmed, body.evidence, body.post_id)
    except ValueError as err:
        raise HTTPException(422, str(err))
    from .services import audit
    audit.record(db, user, "revenue_recorded", str(e.id), source=e.source, confirmed=e.confirmed)
    db.commit()
    return {"id": e.id}


@router.get("/audit")
def audit_log(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500))).all()
    return [{"at": r.at, "actor": r.actor, "event": r.event, "target": r.target, "detail": r.detail} for r in rows]


def _404():
    raise HTTPException(404, "not found")
