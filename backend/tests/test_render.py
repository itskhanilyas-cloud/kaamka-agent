import io

import pytest
from PIL import Image

from app.models import Media, MediaType, Post, PostStatus
from app.render import service, templates
from tests.conftest import OWNER, as_owner, as_stranger

SLIDES = [{"title": "40-page PDF? Relax.", "body": "Turn long PDFs into short notes."},
          {"title": "Step 1: Get the text", "body": "Copy it or use a free OCR tool."},
          {"title": "Step 2: Ask the AI", "body": "Ask for exam revision points."},
          {"title": "Save this", "body": "Try it on your next PDF."}]


def _post(db, media_type=MediaType.carousel, **content):
    p = Post(media_type=media_type, caption="A caption that is long enough for the checks to pass. Save it.",
             pillar="workflow", content={"hook": "Turn PDFs into notes", "slides": SLIDES, **content})
    db.add(p)
    db.flush()
    return p


def _img(data):
    return Image.open(io.BytesIO(data))


def test_carousel_renders_one_jpeg_per_slide_at_instagram_size(db):
    p = _post(db)
    made = service.render_post(db, p, OWNER)
    assert len(made) == 4 and p.media_urls == [f"media:{m.id}" for m in made]
    for m in made:
        im = _img(m.data)
        assert im.format == "JPEG" and im.size == (1080, 1350)  # Instagram API accepts JPEG only


def test_image_post_renders_single_cover(db):
    p = _post(db, MediaType.image)
    made = service.render_post(db, p, OWNER)
    assert len(made) == 1 and _img(made[0].data).size == (1080, 1350)


def test_reel_gets_cover_but_stays_unsubmittable(db):
    from app.services.approvals import check_post_ready
    p = _post(db, MediaType.reel)
    made = service.render_post(db, p, OWNER)
    assert made[0].kind == "cover" and _img(made[0].data).size == (1080, 1920)
    assert p.media_urls == [] and any("Reel video" in c for c in check_post_ready(p))


def test_rerender_replaces_old_images(db):
    p = _post(db)
    service.render_post(db, p, OWNER)
    service.render_post(db, p, OWNER)
    assert db.query(Media).filter(Media.post_id == p.id).count() == 4


def test_published_posts_cannot_be_rerendered(db):
    p = _post(db)
    p.status = PostStatus.published
    with pytest.raises(service.RenderError):
        service.render_post(db, p, OWNER)


def test_carousel_needs_two_slides(db):
    p = _post(db, slides=[SLIDES[0]])
    with pytest.raises(service.RenderError):
        service.render_post(db, p, OWNER)


def test_extreme_text_never_crashes_and_emoji_is_removed():
    long = "word " * 400
    jpeg = templates.content(1, "🔥 " + long, long + " 🚀", templates.Brand(), "2/5", (1, 5))
    assert _img(jpeg).size == (1080, 1350)
    assert templates.clean("Save this 🔥✨ now") == "Save this now"


def test_duplicate_step_prefix_removed():
    assert templates._STEP_PREFIX.sub("", "Step 2: Ask the AI") == "Ask the AI"
    assert templates._STEP_PREFIX.sub("", "Stepping stones") == "Stepping stones"


# --- API -------------------------------------------------------------------------------
def _studio(client, fmt="CAROUSEL"):
    r = client.post("/api/studio/generate", headers=as_owner(),
                    json={"idea": "Free AI tools for college notes", "media_type": fmt, "pillar": "workflow", "variants": 1})
    assert r.status_code == 201
    return r.json()["drafts"][0]


def test_generation_renders_images_automatically(client):
    d = _studio(client)
    assert len(d["media"]) == 6 and d["checks"] == []  # mock carousel has 6 slides and is now complete


def test_media_endpoint_serves_jpeg_to_owner_only(client):
    url = _studio(client)["media"][0]["url"]
    r = client.get(url, headers=as_owner())
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert "private" in r.headers["cache-control"]
    assert client.get(url, headers=as_stranger()).status_code == 403
    assert client.get(url).status_code == 401


def test_editing_slide_text_rerenders(client):
    d = _studio(client)
    old = {m["id"] for m in d["media"]}
    slides = [{"title": f"New title {i}", "body": "New body"} for i in range(5)]
    r = client.patch(f"/api/posts/{d['post_id']}", headers=as_owner(), json={"slides": slides})
    assert r.status_code == 200
    new = {m["id"] for m in r.json()["media"]}
    assert len(new) == 5 and not (old & new)


def test_editing_approved_post_sends_it_back_for_approval(client):
    d = _studio(client)
    req = client.post(f"/api/posts/{d['post_id']}/submit", headers=as_owner()).json()
    client.post(f"/api/approvals/{req['id']}/decision", headers=as_owner(), json={"approve": True})
    r = client.patch(f"/api/posts/{d['post_id']}", headers=as_owner(), json={"caption": "Changed caption that is still long enough. Save it."})
    assert r.json()["status"] == "draft"
    still_approved = client.get("/api/approvals?status=approved", headers=as_owner()).json()
    assert still_approved == []


def test_render_endpoint(client):
    d = _studio(client, "IMAGE")
    r = client.post(f"/api/posts/{d['post_id']}/render", headers=as_owner())
    assert r.status_code == 200 and len(r.json()["media"]) == 1
