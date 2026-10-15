import pytest
from fastapi.testclient import TestClient

OWNER = "owner@example.com"


@pytest.fixture()
def settings_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KA_APP_ENV", "test")
    monkeypatch.setenv("KA_OWNER_EMAIL", OWNER)
    monkeypatch.setenv("KA_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("KA_DEV_AUTH_BYPASS", "false")
    monkeypatch.setenv("KA_MONTHLY_BUDGET_INR", "100")
    monkeypatch.setenv("KA_MAX_POSTS_PER_DAY", "2")
    from app.config import get_settings
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture()
def client(settings_env):
    from app.main import create_app
    return TestClient(create_app())


@pytest.fixture()
def db(client):
    from app.db import get_db
    gen = get_db()
    session = next(gen)
    yield session
    session.close()


def as_owner():
    return {"X-MS-CLIENT-PRINCIPAL-NAME": OWNER}


def as_stranger():
    return {"X-MS-CLIENT-PRINCIPAL-NAME": "someone@else.com"}


def good_post(**overrides):
    body = {"media_type": "IMAGE", "caption": "3 free AI tools for college notes", "media_urls": ["media/a.png"]}
    body.update(overrides)
    return body
