import pytest

from tests.conftest import as_owner, as_stranger


def test_health_is_public(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_api_requires_sign_in(client):
    assert client.get("/api/overview").status_code == 401


def test_api_rejects_non_owner(client):
    assert client.get("/api/overview", headers=as_stranger()).status_code == 403


def test_owner_email_is_case_insensitive(client):
    assert client.get("/api/overview", headers={"X-MS-CLIENT-PRINCIPAL-NAME": "OWNER@Example.com"}).status_code == 200


def test_dev_bypass_refused_in_production(monkeypatch):
    monkeypatch.setenv("KA_APP_ENV", "production")
    monkeypatch.setenv("KA_OWNER_EMAIL", "o@example.com")
    monkeypatch.setenv("KA_DEV_AUTH_BYPASS", "true")
    from app.config import get_settings
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        get_settings()
    get_settings.cache_clear()


def test_secrets_never_appear_in_overview(client, monkeypatch):
    body = client.get("/api/overview", headers=as_owner()).text
    assert "api_key" not in body and "secret" not in body.lower()


def test_whoami_requires_sign_in_and_reports_owner(client):
    assert client.get("/whoami").status_code == 401
    r = client.get("/whoami", headers=as_stranger()).json()
    assert r == {"signed_in_as": "someone@else.com", "is_owner": False}
    assert client.get("/whoami", headers=as_owner()).json()["is_owner"] is True


def test_forbidden_message_names_the_signed_in_account(client):
    r = client.get("/api/overview", headers=as_stranger())
    assert "someone@else.com" in r.json()["detail"]
