import json
import time
from datetime import timedelta

import httpx
import pytest

from app.instagram import client as igc
from app.instagram import service
from app.models import ActionKind, InstagramAccount, MediaType, Post, PostStatus, utcnow
from app.render import service as render_service
from app.services import approvals, publishing
from tests.conftest import OWNER, as_owner

KEY = "test-encryption-key-that-is-long-enough"
TOKEN = "IGAA" + "x" * 40


class FakeIG:
    """Records every request; answers like Instagram's API."""

    def __init__(self, status_sequence=("FINISHED",), fail_publish=None):
        self.calls, self.status_sequence, self.fail_publish = [], list(status_sequence), fail_publish
        self.n = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        url, path = str(request.url), request.url.path
        if "api.instagram.com/oauth/access_token" in url:
            return httpx.Response(200, json={"access_token": "short", "user_id": 1789, "permissions": "x"})
        if path == "/access_token":
            return httpx.Response(200, json={"access_token": TOKEN, "token_type": "bearer", "expires_in": 5183944})
        if path == "/refresh_access_token":
            return httpx.Response(200, json={"access_token": TOKEN + "r", "expires_in": 5183944})
        if path.endswith("/me"):
            return httpx.Response(200, json={"user_id": "1789", "username": "kaamkaai.official", "account_type": "MEDIA_CREATOR"})
        if path.endswith("/media_publish"):
            if self.fail_publish:
                return httpx.Response(*self.fail_publish)
            return httpx.Response(200, json={"id": "ig-post-1"})
        if path.endswith("/media") and request.method == "POST":
            self.n += 1
            return httpx.Response(200, json={"id": f"c{self.n}"})
        if request.method == "GET" and "status_code" in url:
            s = self.status_sequence.pop(0) if len(self.status_sequence) > 1 else self.status_sequence[0]
            return httpx.Response(200, json={"status_code": s})
        return httpx.Response(404, json={"error": {"message": "unexpected"}})


def make_client(fake):
    return igc.InstagramClient("980980594364526", "app-secret", "https://app.example/instagram/callback",
                               http=httpx.Client(transport=httpx.MockTransport(fake.handler)), sleep=lambda s: None)


# ---- crypto and signing -----------------------------------------------------------------
def test_token_encryption_roundtrip_and_wrong_key():
    enc = service.encrypt(KEY, TOKEN)
    assert TOKEN not in enc and service.decrypt(KEY, enc) == TOKEN
    with pytest.raises(service.NotConfigured):
        service.decrypt("other-key", enc)


def test_signed_media_links_expire_and_cannot_be_forged():
    now = time.time()
    url = service.media_link("https://app.example", KEY, "m1", now=now)
    exp = int(url.split("exp=")[1].split("&")[0])
    sig = url.split("sig=")[1]
    assert service.verify_media(KEY, "m1", exp, sig, now=now)
    assert not service.verify_media(KEY, "m2", exp, sig, now=now)            # other image
    assert not service.verify_media(KEY, "m1", exp + 1, sig, now=now)        # tampered expiry
    assert not service.verify_media(KEY, "m1", exp, sig, now=exp + 1)        # expired


# ---- OAuth -------------------------------------------------------------------------------
def test_authorize_url_requests_only_needed_scopes():
    url = make_client(FakeIG()).authorize_url("st")
    assert "instagram_business_content_publish" in url and "manage_messages" not in url and "state=st" in url


def test_connection_saves_encrypted_token(db):
    acct = service.save_connection(db, make_client(FakeIG()), KEY, "code#_", OWNER)
    assert acct.username == "kaamkaai.official" and acct.ig_user_id == "1789"
    assert TOKEN not in acct.token_enc and service.decrypt(KEY, acct.token_enc) == TOKEN
    assert acct.token_expires_at > utcnow() + timedelta(days=59)


def test_errors_never_include_tokens():
    r = httpx.Response(400, json={"error": {"message": "Invalid OAuth access token", "code": 190}})
    e = igc._safe_error(r)
    assert "IGAA" not in str(e) and not e.transient


def test_oauth_endpoint_errors_are_readable():
    r = httpx.Response(400, json={"error_type": "OAuthException", "code": 400, "error_message": "Invalid platform app"})
    assert "code exchange: Invalid platform app" in str(igc._safe_error(r, "code exchange"))


def test_rate_limit_errors_are_transient():
    assert igc._safe_error(httpx.Response(400, json={"error": {"message": "limit", "code": 4}})).transient
    assert igc._safe_error(httpx.Response(503, json={})).transient


# ---- refresh -----------------------------------------------------------------------------
def _account(db, days_left=10, refreshed_hours_ago=48):
    a = InstagramAccount(ig_user_id="1789", username="kaamkaai.official", token_enc=service.encrypt(KEY, TOKEN),
                         token_expires_at=utcnow() + timedelta(days=days_left),
                         token_refreshed_at=utcnow() - timedelta(hours=refreshed_hours_ago), active=True)
    db.add(a)
    db.flush()
    return a


def test_refresh_only_when_due(db):
    _account(db, days_left=50)
    assert service.refresh_if_due(db, make_client(FakeIG()), KEY, OWNER) == "not due"


def test_refresh_respects_24_hour_rule(db):
    _account(db, days_left=5, refreshed_hours_ago=3)
    assert service.refresh_if_due(db, make_client(FakeIG()), KEY, OWNER).startswith("too soon")


def test_refresh_updates_token(db):
    a = _account(db, days_left=5)
    assert service.refresh_if_due(db, make_client(FakeIG()), KEY, OWNER) == "refreshed"
    assert service.decrypt(KEY, a.token_enc) == TOKEN + "r"


# ---- publishing --------------------------------------------------------------------------
def _approved_carousel(db):
    p = Post(media_type=MediaType.carousel, caption="A caption that is long enough to pass the checks. Save it.",
             pillar="workflow", content={"hook": "Hook", "slides": [{"title": f"T{i}", "body": "B"} for i in range(3)]})
    db.add(p)
    db.flush()
    render_service.render_post(db, p, OWNER)
    req = approvals.request_action(db, ActionKind.publish_post, OWNER, post=p)
    approvals.decide(db, req, OWNER, OWNER, approve=True)
    return p, req


def test_carousel_publishes_with_signed_links(db, settings_env):
    _account(db)
    p, req = _approved_carousel(db)
    fake = FakeIG(status_sequence=("IN_PROGRESS", "FINISHED"))
    pub = service.InstagramPublisher(db, make_client(fake), KEY, "https://app.example")
    result = publishing.run_due(db, pub, settings_env)
    assert result.published == 1 and p.ig_media_id == "ig-post-1" and p.status == PostStatus.published
    child_posts = [c for c in fake.calls if c.method == "POST" and c.url.path.endswith("/media") and b"is_carousel_item" in c.content]
    assert len(child_posts) == 3
    body = child_posts[0].content.decode()
    assert "public%2Fmedia" in body and "sig%3D" in body
    parent = [c for c in fake.calls if b"CAROUSEL" in (c.content or b"")][0]
    assert b"caption=" in parent.content


def test_instagram_rejection_marks_post_failed_without_retry(db, settings_env):
    _account(db)
    p, req = _approved_carousel(db)
    fake_handler = FakeIG().handler

    def handler(request):
        if request.url.path.endswith("/media_publish"):
            return httpx.Response(400, json={"error": {"message": "The image format is not supported", "code": 9004}})
        return fake_handler(request)
    client = igc.InstagramClient("1", "s", "https://x/cb", http=httpx.Client(transport=httpx.MockTransport(handler)),
                                 sleep=lambda s: None)
    pub = service.InstagramPublisher(db, client, KEY, "https://app.example")
    publishing.run_due(db, pub, settings_env)
    assert p.status == PostStatus.failed and "image format" in p.last_error


def test_publisher_requires_connection(db):
    with pytest.raises(service.NotConfigured):
        service.InstagramPublisher(db, make_client(FakeIG()), KEY, "https://app.example")


# ---- routes ------------------------------------------------------------------------------
@pytest.fixture()
def ig_env(monkeypatch, settings_env):
    monkeypatch.setattr(settings_env, "instagram_app_id", "980980594364526")
    from pydantic import SecretStr
    monkeypatch.setattr(settings_env, "instagram_app_secret", SecretStr("app-secret"))
    monkeypatch.setattr(settings_env, "token_encryption_key", SecretStr(KEY))
    monkeypatch.setattr(settings_env, "public_base_url", "https://app.example")
    return settings_env


def test_status_reports_not_configured(client):
    r = client.get("/api/instagram/status", headers=as_owner()).json()
    assert r == {"configured": False, "connected": False, "username": None, "account_type": None, "token_expires_at": None}


def test_connect_requires_configuration(client):
    assert client.get("/instagram/connect", headers=as_owner(), follow_redirects=False).status_code == 503


def test_connect_redirects_to_instagram_with_state(client, ig_env):
    r = client.get("/instagram/connect", headers=as_owner(), follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://www.instagram.com/oauth/authorize?")
    assert "redirect_uri=https%3A%2F%2Fapp.example%2Finstagram%2Fcallback" in r.headers["location"]


def test_callback_rejects_unknown_state(client, ig_env):
    r = client.get("/instagram/callback?code=abc&state=forged", headers=as_owner(), follow_redirects=False)
    assert r.status_code == 400


def test_public_media_requires_valid_signature(client, ig_env, db):
    p = Post(media_type=MediaType.image, caption="x" * 90, content={"hook": "Hello"})
    db.add(p)
    db.flush()
    m = render_service.render_post(db, p, OWNER)[0]
    db.commit()
    good = service.media_link("https://app.example", KEY, m.id).replace("https://app.example", "")
    r = client.get(good)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get(good.replace("sig=", "sig=0")).status_code == 404
    assert client.get(f"/public/media/{m.id}.jpg?exp=9999999999&sig=abc").status_code == 404
