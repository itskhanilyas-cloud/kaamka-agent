from tests.conftest import as_owner


def test_dashboard_shell_is_served_with_strict_headers(client):
    r = client.get("/")
    assert r.status_code == 200 and "Kaam Ka AI" in r.text
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert r.headers["x-frame-options"] == "DENY"


def test_dashboard_has_no_inline_script(client):
    html = client.get("/").text
    assert "<script>" not in html and 'src="/static/app.js"' in html


def test_static_assets_served(client):
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200


def test_frontend_never_uses_innerhtml(client):
    js = client.get("/static/app.js").text
    assert "innerHTML" not in js.replace("never innerHTML", "")


def test_api_responses_not_cached(client):
    assert client.get("/api/overview", headers=as_owner()).headers["cache-control"] == "no-store"


def test_overview_reports_text_provider(client):
    assert client.get("/api/overview", headers=as_owner()).json()["text_provider"] == "mock"
