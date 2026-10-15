"""Connection state, encrypted token storage, signed media links and the real publisher."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InstagramAccount, Media, Post, utcnow
from ..services import audit
from ..services.publishing import PermanentPublishError, TransientPublishError
from .client import InstagramClient, InstagramError

MEDIA_LINK_TTL = 3600  # seconds a signed image link stays valid; Instagram fetches within minutes
REFRESH_WHEN_DAYS_LEFT = 20


class NotConfigured(Exception):
    pass


def _fernet(key: str) -> Fernet:
    # Accept any strong secret string: derive a 32-byte Fernet key from it.
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


def encrypt(key: str, value: str) -> str:
    return _fernet(key).encrypt(value.encode()).decode()


def decrypt(key: str, value: str) -> str:
    try:
        return _fernet(key).decrypt(value.encode()).decode()
    except InvalidToken as e:
        raise NotConfigured("stored Instagram token cannot be decrypted (key changed?)") from e


# ---- signed public media links --------------------------------------------------------
def sign_media(key: str, media_id: str, expires: int) -> str:
    msg = f"{media_id}.{expires}".encode()
    return hmac.new(hashlib.sha256(key.encode()).digest(), msg, hashlib.sha256).hexdigest()


def media_link(base_url: str, key: str, media_id: str, now: float | None = None, ext: str = "jpg") -> str:
    exp = int((now or time.time()) + MEDIA_LINK_TTL)
    return f"{base_url.rstrip('/')}/public/media/{media_id}.{ext}?exp={exp}&sig={sign_media(key, media_id, exp)}"


def verify_media(key: str, media_id: str, exp: int, sig: str, now: float | None = None) -> bool:
    if exp < (now or time.time()):
        return False
    return hmac.compare_digest(sign_media(key, media_id, exp), sig)


# ---- account ---------------------------------------------------------------------------
def current_account(db: Session) -> InstagramAccount | None:
    return db.scalar(select(InstagramAccount).where(InstagramAccount.active.is_(True)))


def new_state() -> str:
    return secrets.token_urlsafe(24)


def save_connection(db: Session, client: InstagramClient, key: str, code: str, actor: str) -> InstagramAccount:
    tok = client.exchange_code(code)
    me = client.me(tok.access_token)
    for old in db.scalars(select(InstagramAccount)).all():
        old.active = False
    acct = InstagramAccount(ig_user_id=str(me.get("user_id") or tok.user_id), username=me.get("username", ""),
                            account_type=me.get("account_type"), token_enc=encrypt(key, tok.access_token),
                            token_expires_at=utcnow() + timedelta(seconds=tok.expires_in or 60 * 86400),
                            token_refreshed_at=utcnow(), active=True)
    db.add(acct)
    db.flush()
    audit.record(db, actor, "instagram_connected", acct.ig_user_id, username=acct.username,
                 account_type=acct.account_type)
    return acct


def disconnect(db: Session, actor: str) -> None:
    acct = current_account(db)
    if acct:
        acct.active = False
        acct.token_enc = ""
        audit.record(db, actor, "instagram_disconnected", acct.ig_user_id, username=acct.username)


def refresh_if_due(db: Session, client: InstagramClient, key: str, actor: str) -> str:
    acct = current_account(db)
    if not acct:
        return "not connected"
    now = utcnow()
    expires = acct.token_expires_at if acct.token_expires_at.tzinfo else acct.token_expires_at.replace(tzinfo=now.tzinfo)
    refreshed = acct.token_refreshed_at if acct.token_refreshed_at.tzinfo else acct.token_refreshed_at.replace(tzinfo=now.tzinfo)
    if expires - now > timedelta(days=REFRESH_WHEN_DAYS_LEFT):
        return "not due"
    if now - refreshed < timedelta(hours=24):
        return "too soon (Instagram requires the token to be 24h old)"
    try:
        tok = client.refresh(decrypt(key, acct.token_enc))
    except InstagramError as e:
        audit.record(db, actor, "instagram_token_refresh_failed", acct.ig_user_id, error=str(e))
        raise
    acct.token_enc = encrypt(key, tok.access_token)
    acct.token_expires_at = now + timedelta(seconds=tok.expires_in or 60 * 86400)
    acct.token_refreshed_at = now
    audit.record(db, actor, "instagram_token_refreshed", acct.ig_user_id)
    return "refreshed"


class InstagramPublisher:
    """Publisher used by the publish worker in production once an account is connected."""

    def __init__(self, db: Session, client: InstagramClient, key: str, base_url: str):
        acct = current_account(db)
        if not acct or not acct.token_enc:
            raise NotConfigured("Instagram is not connected")
        self.db, self.client, self.key, self.base_url, self.acct = db, client, key, base_url, acct

    def publish(self, post: Post, idempotency_key: str) -> str:
        token = decrypt(self.key, self.acct.token_enc)
        ids = [u.split(":", 1)[1] for u in (post.media_urls or []) if u.startswith("media:")]
        if not ids:
            raise PermanentPublishError("post has no rendered images or video")
        items = [self.db.get(Media, i) for i in ids]
        if not all(items):
            raise PermanentPublishError("an image or video for this post is missing; add it again")
        urls = [media_link(self.base_url, self.key, m.id, ext="mp4" if m.mime == "video/mp4" else "jpg") for m in items]
        alt = (post.content or {}).get("alt_text")
        try:
            if post.media_type.value == "REELS":
                if items[0].mime != "video/mp4":
                    raise PermanentPublishError("a Reel needs an MP4 video")
                cover = self.db.scalar(select(Media).where(Media.post_id == post.id, Media.kind == "cover"))
                cover_url = media_link(self.base_url, self.key, cover.id) if cover else None
                return self.client.publish_reel(self.acct.ig_user_id, token, urls[0], post.caption, cover_url)
            if post.media_type.value == "CAROUSEL":
                return self.client.publish_carousel(self.acct.ig_user_id, token, urls, post.caption)
            if post.media_type.value == "IMAGE":
                return self.client.publish_image(self.acct.ig_user_id, token, urls[0], post.caption, alt)
            raise PermanentPublishError(f"{post.media_type.value} publishing is not supported yet")
        except InstagramError as e:
            raise (TransientPublishError if e.transient else PermanentPublishError)(str(e)) from e


# ---- results -----------------------------------------------------------------------------
def sync_metrics(db: Session, client: InstagramClient, key: str, now=None) -> dict:
    """Pulls lifetime numbers for every published post plus the follower count.
    Stores a new snapshot each run; nothing is estimated or invented."""
    from ..models import AccountSnapshot, Post, PostMetric, PostStatus
    acct = current_account(db)
    if not acct or not acct.token_enc:
        raise NotConfigured("Instagram is not connected")
    token = decrypt(key, acct.token_enc)
    done, errors = 0, []
    posts = db.scalars(select(Post).where(Post.status == PostStatus.published, Post.ig_media_id.is_not(None))).all()
    for p in posts:
        if p.ig_media_id.startswith("dryrun-"):
            continue
        try:
            v = client.media_insights(p.ig_media_id, token, reel=p.media_type.value == "REELS")
        except InstagramError as e:
            errors.append(f"{p.id[:8]}: {e}")
            continue
        db.add(PostMetric(post_id=p.id, views=v.get("views"), reach=v.get("reach"), likes=v.get("likes"),
                          comments=v.get("comments"), saved=v.get("saved"), shares=v.get("shares"),
                          total_interactions=v.get("total_interactions"), avg_watch_ms=v.get("ig_reels_avg_watch_time")))
        done += 1
    try:
        info = client.account_info(token)
        db.add(AccountSnapshot(followers=info.get("followers_count"), media_count=info.get("media_count")))
    except InstagramError as e:
        errors.append(f"account: {e}")
    db.flush()
    audit.record(db, "system:agent", "metrics_synced", None, posts=done, errors=len(errors))
    return {"posts": done, "errors": errors}
