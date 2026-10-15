"""Turns a post's structured content into branded images and attaches them to the post."""
import hashlib
import io

from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Media, MediaType, Post, PostStatus
from ..services import audit
from . import templates as t

MEDIA_PREFIX = "media:"
EDITABLE = {PostStatus.draft, PostStatus.rejected, PostStatus.failed, PostStatus.pending_approval}


class RenderError(Exception):
    pass


def _store(db: Session, post: Post, position: int, kind: str, jpeg: bytes) -> Media:
    with Image.open(io.BytesIO(jpeg)) as im:
        w, h = im.size
    m = Media(post_id=post.id, position=position, kind=kind, width=w, height=h,
              sha256=hashlib.sha256(jpeg).hexdigest(), data=jpeg)
    db.add(m)
    db.flush()
    return m


def _first_sentence(text: str, limit: int = 140) -> str:
    text = t.clean(text).split("\n")[0]
    for stop in (". ", "? ", "! "):
        if stop in text:
            text = text.split(stop)[0] + stop.strip()
            break
    return text[:limit]


def render_post(db: Session, post: Post, actor: str, brand: t.Brand | None = None) -> list[Media]:
    if post.status not in EDITABLE:
        raise RenderError(f"cannot re-render a post that is {post.status.value}")
    brand = brand or t.Brand()
    c = post.content or {}
    hook = (c.get("hook") or "").strip()
    if not hook and not (c.get("slides")):
        raise RenderError("post has no hook or slides to render")

    db.execute(delete(Media).where(Media.post_id == post.id))
    made: list[Media] = []

    if post.media_type == MediaType.carousel:
        slides = [s for s in (c.get("slides") or []) if isinstance(s, dict)][:10]
        if len(slides) < 2:
            raise RenderError("a carousel needs at least 2 slides")
        n = len(slides)
        for i, s in enumerate(slides):
            counter = f"{i + 1}/{n}"
            title, body = s.get("title") or "", s.get("body") or ""
            if i == 0:
                jpeg = t.cover(title or hook, body, post.pillar, brand, counter, swipe=True)
            elif i == n - 1 and n > 2:
                jpeg = t.cta(title, body, brand, counter)
            else:
                jpeg = t.content(i, title, body, brand, counter, (i, n))
            made.append(_store(db, post, i, "slide", jpeg))
        post.media_urls = [MEDIA_PREFIX + m.id for m in made]

    elif post.media_type == MediaType.image:
        jpeg = t.cover(hook, _first_sentence(c.get("caption") or post.caption), post.pillar, brand)
        made.append(_store(db, post, 0, "slide", jpeg))
        post.media_urls = [MEDIA_PREFIX + made[0].id]

    elif post.media_type == MediaType.reel:
        # Cover only; the Reel video itself is produced in a later phase, so it is not publishable yet.
        jpeg = t.cover(hook, "", post.pillar, brand, height=1920)
        made.append(_store(db, post, 0, "cover", jpeg))
        post.media_urls = []
    else:
        raise RenderError(f"no template for {post.media_type.value}")

    audit.record(db, actor, "media_rendered", post.id, images=len(made), format=post.media_type.value)
    return made


def media_for(db: Session, post_id: str) -> list[Media]:
    return list(db.scalars(select(Media).where(Media.post_id == post_id).order_by(Media.position)).all())
