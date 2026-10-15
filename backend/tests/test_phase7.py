"""Phase 7: Reel publishing, scheduled-only timer job, metrics sync and results."""
from datetime import timedelta

import httpx

from app.instagram import client as igc
from app.instagram import service
from app.models import ActionKind, MediaType, Post, PostMetric, PostStatus, utcnow
from app.render import service as render_service
from app.services import analytics, approvals, publishing
from tests.conftest import OWNER, as_owner
from tests.test_instagram import KEY, FakeIG, _account, _approved_carousel, ig_env, make_client  # noqa: F401
from tests.test_render import MP4


def _approved_reel(db, scheduled_at=None):
    p = Post(media_type=MediaType.reel, caption="A caption that is long enough to pass the checks. Save it.",
             pillar="offers", content={"hook": "Google AI plan free"}, scheduled_at=scheduled_at)
    db.add(p)
    db.flush()
    render_service.render_post(db, p, OWNER)
    render_service.attach_video(db, p, MP4, OWNER)
    req = approvals.request_action(db, ActionKind.publish_post, OWNER, post=p)
    approvals.decide(db, req, OWNER, OWNER, approve=True)
    return p


def test_reel_publishes_with_signed_video_and_cover(db, settings_env):
    _account(db)
    p = _approved_reel(db)
    fake = FakeIG()
    publishing.run_due(db, service.InstagramPublisher(db, make_client(fake), KEY, "https://app.example"), settings_env)
    assert p.status == PostStatus.published
    create = [c for c in fake.calls if c.method == "POST" and c.url.path.endswith("/media")][0].content.decode()
    assert "media_type=REELS" in create and ".mp4%3Fexp" in create and "cover_url=" in create and ".jpg%3Fexp" in create


def test_timer_job_only_publishes_posts_with_a_time(db, settings_env):
    unscheduled, _ = _approved_carousel(db)
    later = _approved_reel(db, scheduled_at=utcnow() + timedelta(hours=2))
    pub = publishing.DryRunPublisher()
    assert publishing.run_due(db, pub, settings_env, scheduled_only=True).published == 0
    assert unscheduled.status == PostStatus.approved and later.status == PostStatus.scheduled
    assert publishing.run_due(db, pub, settings_env, now=utcnow() + timedelta(hours=3), scheduled_only=True).published == 1
    assert later.status == PostStatus.published and unscheduled.status == PostStatus.approved


def test_insights_parse_and_fall_back_metric_by_metric():
    def handler(request):
        m = request.url.params.get("metric")
        if "," in m:
            return httpx.Response(400, json={"error": {"message": "metric not supported", "code": 100}})
        if m == "views":
            return httpx.Response(400, json={"error": {"message": "not supported", "code": 100}})
        if m == "reach":
            return httpx.Response(200, json={"data": [{"name": "reach", "values": [{"value": 120}]}]})
        return httpx.Response(200, json={"data": [{"name": m, "total_value": {"value": 3}}]})
    c = igc.InstagramClient("1", "s", "https://x/cb", http=httpx.Client(transport=httpx.MockTransport(handler)))
    v = c.media_insights("m1", "tok")
    assert v["reach"] == 120 and v["saved"] == 3 and "views" not in v


def test_sync_metrics_stores_snapshots_and_skips_dry_runs(db):
    _account(db)
    real = Post(media_type=MediaType.image, caption="x", status=PostStatus.published, ig_media_id="1789", published_at=utcnow())
    fake_pub = Post(media_type=MediaType.image, caption="x", status=PostStatus.published, ig_media_id="dryrun-abc", published_at=utcnow())
    db.add_all([real, fake_pub])
    db.flush()

    def handler(request):
        if request.url.path.endswith("/insights"):
            return httpx.Response(200, json={"data": [{"name": n, "values": [{"value": v}]} for n, v in
                                                      (("reach", 200), ("saved", 9), ("shares", 4), ("likes", 20))]})
        if request.url.path.endswith("/me"):
            return httpx.Response(200, json={"followers_count": 42, "media_count": 2})
        return httpx.Response(404)
    c = igc.InstagramClient("1", "s", "https://x/cb", http=httpx.Client(transport=httpx.MockTransport(handler)))
    r = service.sync_metrics(db, c, KEY)
    assert r == {"posts": 1, "errors": []}
    s = analytics.summary(db)
    row = [x for x in s["posts"] if x["id"] == real.id][0]
    assert s["followers"] == 42 and row["saved"] == 9 and row["save_rate"] == 0.045
    assert "Not enough data yet" in s["lessons"][0]


def test_lessons_compare_groups_only_with_enough_posts(db):
    for i, (fmt, saved) in enumerate([(MediaType.carousel, 10), (MediaType.carousel, 12), (MediaType.image, 1), (MediaType.image, 2)]):
        p = Post(media_type=fmt, caption="x", status=PostStatus.published, ig_media_id=str(i), published_at=utcnow(),
                 content={"hook": f"post {i}"})
        db.add(p)
        db.flush()
        db.add(PostMetric(post_id=p.id, reach=100, saved=saved, shares=0))
    db.flush()
    text = " ".join(analytics.summary(db)["lessons"])
    assert "'CAROUSEL' gets the most saves" in text and "hint, not a rule" in text


def test_video_upload_and_public_mp4(client, ig_env, db):
    p = Post(media_type=MediaType.reel, caption="x" * 90, content={"hook": "Hi"})
    db.add(p)
    db.commit()
    r = client.post(f"/api/posts/{p.id}/video", content=MP4, headers={**as_owner(), "content-type": "video/mp4"})
    assert r.status_code == 200 and r.json()["media"][0]["kind"] == "video"
    vid = r.json()["media"][0]["id"]
    link = service.media_link("https://app.example", KEY, vid, ext="mp4").replace("https://app.example", "")
    got = client.get(link)
    assert got.status_code == 200 and got.headers["content-type"] == "video/mp4" and got.content == MP4
    assert client.post(f"/api/posts/{p.id}/video", content=b"nope" * 500, headers=as_owner()).status_code == 422


def test_publish_now_runs_in_background(client):
    r = client.post("/api/publish/run", headers=as_owner())
    assert r.status_code == 202 and r.json() == {"started": True, "dry_run": True}


def test_analytics_endpoint_requires_owner(client):
    assert client.get("/api/analytics").status_code == 401
    assert client.get("/api/analytics", headers=as_owner()).json()["posts"] == []
