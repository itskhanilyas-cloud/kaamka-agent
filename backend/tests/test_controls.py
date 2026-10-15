import pytest

from app.services import audit, budget, policy, revenue
from tests.conftest import OWNER, as_owner


# --- budget ---------------------------------------------------------------
def test_budget_blocks_over_cap(db):  # cap is ₹100 in tests
    budget.reserve(db, "image_ai", 60, 100, "system:agent")
    with pytest.raises(budget.BudgetExceeded):
        budget.reserve(db, "video_ai", 50, 100, "system:agent")
    assert budget.spent_this_month(db) == 60


def test_budget_rejects_negative(db):
    with pytest.raises(ValueError):
        budget.reserve(db, "image_ai", -1, 100, "x")


# --- policy ---------------------------------------------------------------
def test_auto_publish_off_by_default(client):
    assert client.get("/api/policies/auto_publish", headers=as_owner()).json()["enabled"] is False


def test_agent_cannot_change_policy(db):
    with pytest.raises(policy.PolicyChangeForbidden):
        policy.set_policy(db, "auto_publish", {"enabled": True}, policy.SYSTEM_ACTOR, OWNER)
    assert policy.get_policy(db, "auto_publish")["enabled"] is False


def test_owner_can_change_policy_and_it_is_audited(client):
    r = client.put("/api/policies/auto_publish", json={"value": {"enabled": True, "allowed_media_types": ["IMAGE"]}},
                   headers=as_owner())
    assert r.status_code == 200
    events = [e["event"] for e in client.get("/api/audit", headers=as_owner()).json()]
    assert "policy_changed" in events


# --- secret redaction -----------------------------------------------------
def test_redaction_of_keys_and_values():
    out = audit.redact({"access_token": "abc", "note": "Bearer xyz.123", "nested": [{"api_key": "k"}],
                        "msg": "token EAA" + "B" * 30})
    assert out["access_token"] == "***" and out["nested"][0]["api_key"] == "***"
    assert "xyz" not in out["note"] and "EAAB" not in out["msg"]


def test_audit_entries_are_redacted(db):
    e = audit.record(db, "x", "test", None, password="hunter2")
    assert e.detail["password"] == "***"


# --- revenue --------------------------------------------------------------
def test_revenue_keeps_confirmed_and_estimated_separate(db):
    revenue.add_revenue(db, "affiliate", 500, confirmed=True, evidence="Amazon payout 2026-10")
    revenue.add_revenue(db, "sponsorship", 2000, confirmed=False, evidence=None)
    budget.reserve(db, "infra", 90, 100, "x")
    s = revenue.summary(db)
    assert s["revenue_confirmed_inr"] == 500 and s["revenue_estimated_inr"] == 2000
    assert s["profit_confirmed_inr"] == 410 and s["profit_if_estimates_land_inr"] == 2410


def test_confirmed_revenue_requires_evidence(db):
    with pytest.raises(ValueError):
        revenue.add_revenue(db, "affiliate", 100, confirmed=True, evidence=None)
