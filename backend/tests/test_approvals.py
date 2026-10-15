import pytest

from app.models import ActionKind, Post
from app.services import approvals
from app.services.policy import SYSTEM_ACTOR
from tests.conftest import OWNER, as_owner, good_post


def _create_and_submit(client, **kw):
    post = client.post("/api/posts", json=good_post(**kw), headers=as_owner()).json()
    req = client.post(f"/api/posts/{post['id']}/submit", headers=as_owner())
    return post, req


def test_owner_can_approve(client):
    post, req = _create_and_submit(client)
    assert req.status_code == 201
    r = client.post(f"/api/approvals/{req.json()['id']}/decision", json={"approve": True}, headers=as_owner())
    assert r.json()["status"] == "approved"
    assert client.get("/api/posts", headers=as_owner()).json()[0]["status"] == "approved"


def test_reject_marks_post_rejected(client):
    post, req = _create_and_submit(client)
    client.post(f"/api/approvals/{req.json()['id']}/decision", json={"approve": False, "note": "weak hook"},
                headers=as_owner())
    assert client.get("/api/posts", headers=as_owner()).json()[0]["status"] == "rejected"


def test_cannot_decide_twice(client):
    _, req = _create_and_submit(client)
    rid = req.json()["id"]
    client.post(f"/api/approvals/{rid}/decision", json={"approve": True}, headers=as_owner())
    r = client.post(f"/api/approvals/{rid}/decision", json={"approve": False}, headers=as_owner())
    assert r.status_code == 409


def test_agent_cannot_approve(db):
    post = Post(media_type="IMAGE", caption="hello", media_urls=["x.png"])
    db.add(post)
    db.flush()
    req = approvals.request_action(db, ActionKind.publish_post, SYSTEM_ACTOR, post=post)
    with pytest.raises(approvals.NotOwner):
        approvals.decide(db, req, SYSTEM_ACTOR, OWNER, approve=True)


def test_affiliate_post_without_disclosure_is_blocked(client):
    _, req = _create_and_submit(client, has_affiliate_link=True, caption="Best laptop stand, link in bio")
    assert req.status_code == 422
    assert "disclosure" in req.json()["detail"]


def test_affiliate_post_with_disclosure_passes(client):
    _, req = _create_and_submit(client, has_affiliate_link=True, caption="#Affiliate Best laptop stand, link in bio")
    assert req.status_code == 201


def test_edit_after_submit_is_rechecked_on_approval(client):
    post, req = _create_and_submit(client)
    client.patch(f"/api/posts/{post['id']}", json={"caption": ""}, headers=as_owner())
    r = client.post(f"/api/approvals/{req.json()['id']}/decision", json={"approve": True}, headers=as_owner())
    assert r.status_code == 409


def test_carousel_needs_two_to_ten_items(client):
    _, req = _create_and_submit(client, media_type="CAROUSEL", media_urls=["a.png"])
    assert req.status_code == 422


def test_actions_are_audited(client):
    _, req = _create_and_submit(client)
    client.post(f"/api/approvals/{req.json()['id']}/decision", json={"approve": True}, headers=as_owner())
    events = [e["event"] for e in client.get("/api/audit", headers=as_owner()).json()]
    assert {"post_created", "action_requested", "action_approved"} <= set(events)
