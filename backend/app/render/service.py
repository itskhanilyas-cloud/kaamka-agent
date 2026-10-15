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

    db.execute(delete(Media).where(Media.post_id == post.id, Media.kind != "video"))  # an uploaded video stays
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
        # The cover is drawn here; the video itself is uploaded by the owner (attach_video).
        jpeg = t.cover(hook, "", post.pillar, brand, height=1920)
        made.append(_store(db, post, 1, "cover", jpeg))
        video = _video(db, post.id)
        post.media_urls = [MEDIA_PREFIX + video.id] if video else []
    else:
        raise RenderError(f"no template for {post.media_type.value}")

    audit.record(db, actor, "media_rendered", post.id, images=len(made), format=post.media_type.value)
    return made


MAX_VIDEO_BYTES = 100 * 1024 * 1024


def _video(db: Session, post_id: str) -> Media | None:
    return db.scalar(select(Media).where(Media.post_id == post_id, Media.kind == "video"))


def attach_video(db: Session, post: Post, data: bytes, actor: str) -> Media:
    """Stores an MP4 for a Reel (replacing any earlier one). Instagram fetches it via a signed link."""
    if post.media_type != MediaType.reel:
        raise RenderError("only Reels take a video")
    if post.status not in EDITABLE:
        raise RenderError(f"cannot change a post that is {post.status.value}")
    if len(data) > MAX_VIDEO_BYTES:
        raise RenderError("video is larger than 100 MB")
    if len(data) < 1024 or data[4:8] != b"ftyp":
        raise RenderError("that file is not an MP4 video")
    db.execute(delete(Media).where(Media.post_id == post.id, Media.kind == "video"))
    m = Media(post_id=post.id, position=0, kind="video", mime="video/mp4", width=1080, height=1920,
              sha256=hashlib.sha256(data).hexdigest(), data=data)
    db.add(m)
    db.flush()
    post.media_urls = [MEDIA_PREFIX + m.id]
    audit.record(db, actor, "video_attached", post.id, bytes=len(data))
    return m


def media_for(db: Session, post_id: str) -> list[Media]:
    return list(db.scalars(select(Media).where(Media.post_id == post_id).order_by(Media.position)).all())
