"""Human-in-the-loop approval workflow.

Anyone (including the agent) may *request* an action. Only the owner may
approve or reject it, and only a pending request can be decided.
"""
from sqlalchemy.orm import Session

from ..models import ActionKind, ActionRequest, ActionStatus, Post, PostStatus, utcnow
from . import audit


class ApprovalError(Exception):
    pass


class NotOwner(PermissionError):
    pass


AFFILIATE_DISCLOSURES = ("#ad", "#affiliate", "#sponsored", "#collab")


def check_post_ready(post: Post) -> list[str]:
    """Rules a post must pass before it can be submitted or approved."""
    problems: list[str] = []
    caption = (post.caption or "").strip()
    if not caption and post.media_type != "STORIES":
        problems.append("caption is empty")
    if len(caption) > 2200:
        problems.append("caption exceeds Instagram's 2,200 character limit")
    if caption.count("#") > 30:
        problems.append("more than 30 hashtags")
    if post.has_affiliate_link:
        head = caption[:150].lower()
        if not any(tag in head for tag in AFFILIATE_DISCLOSURES):
            problems.append("affiliate post must start with a clear disclosure (#Ad or #Affiliate) in the first 150 characters")
    if post.media_type == "REELS" and not post.media_urls:
        problems.append("Reel video production arrives in a later phase; Reels can't be submitted yet")
    elif not post.media_urls:
        problems.append("no images yet: render the slides first")
    if post.media_type == "CAROUSEL" and not (2 <= len(post.media_urls) <= 10):
        problems.append("carousel needs 2-10 items")
    return problems


def request_action(db: Session, kind: ActionKind, requested_by: str, *, post: Post | None = None,
                   payload: dict | None = None) -> ActionRequest:
    if kind == ActionKind.publish_post:
        if post is None:
            raise ApprovalError("publish_post needs a post")
        problems = check_post_ready(post)
        if problems:
            raise ApprovalError("; ".join(problems))
        post.status = PostStatus.pending_approval
    req = ActionRequest(kind=kind, requested_by=requested_by, post_id=post.id if post else None,
                        payload=payload or {})
    db.add(req)
    db.flush()
    audit.record(db, requested_by, "action_requested", req.id, kind=kind.value, payload=payload or {})
    return req


def decide(db: Session, req: ActionRequest, actor: str, owner_email: str, approve: bool,
           note: str | None = None) -> ActionRequest:
    if actor != owner_email:
        audit.record(db, actor, "decision_denied", req.id, kind=req.kind.value)
        raise NotOwner("only the owner can approve or reject actions")
    if req.status != ActionStatus.pending:
        raise ApprovalError(f"request is already {req.status.value}")
    if approve and req.post is not None:
        problems = check_post_ready(req.post)  # re-check: the post may have been edited
        if problems:
            raise ApprovalError("; ".join(problems))
    req.status = ActionStatus.approved if approve else ActionStatus.rejected
    req.decided_by, req.decided_at, req.decision_note = actor, utcnow(), note
    if req.post is not None:
        if approve:
            req.post.status = PostStatus.scheduled if req.post.scheduled_at else PostStatus.approved
        else:
            req.post.status = PostStatus.rejected
    audit.record(db, actor, "action_approved" if approve else "action_rejected", req.id,
                 kind=req.kind.value, note=note)
    return req
