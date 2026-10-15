"""Instagram API with Instagram Login: OAuth, token refresh and content publishing.

Endpoints (Meta docs, checked 2026-10-15):
  authorize      https://www.instagram.com/oauth/authorize
  code->token    POST https://api.instagram.com/oauth/access_token
  long-lived     GET  https://graph.instagram.com/access_token?grant_type=ig_exchange_token   (60 days)
  refresh        GET  https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token (token >= 24h old)
  publish        POST /{ig-user-id}/media -> GET /{container}?fields=status_code -> POST /{ig-user-id}/media_publish
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

GRAPH = "https://graph.instagram.com"
API_VERSION = "v25.0"
SCOPES = ["instagram_business_basic", "instagram_business_content_publish",
          "instagram_business_manage_comments", "instagram_business_manage_insights"]


class InstagramError(Exception):
    def __init__(self, message: str, *, transient: bool = False, code: int | None = None):
        super().__init__(message)
        self.transient, self.code = transient, code


def _safe_error(resp: httpx.Response) -> InstagramError:
    """Build an error without ever including tokens or secrets from the request."""
    try:
        err = resp.json().get("error", {})
    except ValueError:
        err = {}
    code = err.get("code")
    msg = err.get("error_user_msg") or err.get("message") or f"HTTP {resp.status_code}"
    transient = resp.status_code >= 500 or resp.status_code == 429 or code in (1, 2, 4, 17, 32, 341, 613)
    return InstagramError(f"Instagram: {msg}"[:300], transient=transient, code=code)


@dataclass
class Token:
    access_token: str
    expires_in: int
    user_id: str | None = None


class InstagramClient:
    def __init__(self, app_id: str, app_secret: str, redirect_uri: str, http: httpx.Client | None = None,
                 sleep=time.sleep):
        self.app_id, self.app_secret, self.redirect_uri = app_id, app_secret, redirect_uri
        self.http = http or httpx.Client(timeout=30)
        self.sleep = sleep

    # ---- OAuth -------------------------------------------------------------------------
    def authorize_url(self, state: str) -> str:
        q = {"client_id": self.app_id, "redirect_uri": self.redirect_uri, "response_type": "code",
             "scope": ",".join(SCOPES), "state": state, "enable_fb_login": "false"}
        return "https://www.instagram.com/oauth/authorize?" + urlencode(q)

    def exchange_code(self, code: str) -> Token:
        code = code.split("#")[0]
        r = self.http.post("https://api.instagram.com/oauth/access_token", data={
            "client_id": self.app_id, "client_secret": self.app_secret, "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri, "code": code})
        if r.status_code != 200:
            raise _safe_error(r)
        short = r.json()
        user_id = str(short.get("user_id") or "")
        r = self.http.get(f"{GRAPH}/access_token", params={
            "grant_type": "ig_exchange_token", "client_secret": self.app_secret, "access_token": short["access_token"]})
        if r.status_code != 200:
            raise _safe_error(r)
        j = r.json()
        return Token(j["access_token"], int(j.get("expires_in", 0)), user_id)

    def refresh(self, token: str) -> Token:
        r = self.http.get(f"{GRAPH}/refresh_access_token", params={"grant_type": "ig_refresh_token", "access_token": token})
        if r.status_code != 200:
            raise _safe_error(r)
        j = r.json()
        return Token(j["access_token"], int(j.get("expires_in", 0)))

    def me(self, token: str) -> dict:
        r = self.http.get(f"{GRAPH}/{API_VERSION}/me", params={
            "fields": "user_id,username,account_type", "access_token": token})
        if r.status_code != 200:
            raise _safe_error(r)
        return r.json()

    # ---- Publishing ----------------------------------------------------------------------
    def _post(self, path: str, token: str, data: dict) -> dict:
        r = self.http.post(f"{GRAPH}/{API_VERSION}/{path}", data={**data, "access_token": token})
        if r.status_code != 200:
            raise _safe_error(r)
        return r.json()

    def _wait_ready(self, container_id: str, token: str, attempts: int = 30, delay: float = 3.0) -> None:
        for _ in range(attempts):
            r = self.http.get(f"{GRAPH}/{API_VERSION}/{container_id}", params={"fields": "status_code", "access_token": token})
            if r.status_code != 200:
                raise _safe_error(r)
            status = r.json().get("status_code")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise InstagramError(f"Instagram could not process the media ({status})")
            self.sleep(delay)
        raise InstagramError("Instagram is still processing the media; will retry", transient=True)

    def publish_image(self, ig_user_id: str, token: str, image_url: str, caption: str, alt_text: str | None = None) -> str:
        data = {"image_url": image_url, "caption": caption}
        if alt_text:
            data["alt_text"] = alt_text[:1000]
        c = self._post(f"{ig_user_id}/media", token, data)["id"]
        self._wait_ready(c, token)
        return self._post(f"{ig_user_id}/media_publish", token, {"creation_id": c})["id"]

    def publish_carousel(self, ig_user_id: str, token: str, image_urls: list[str], caption: str) -> str:
        if not 2 <= len(image_urls) <= 10:
            raise InstagramError("a carousel needs 2-10 images")
        children = [self._post(f"{ig_user_id}/media", token, {"image_url": u, "is_carousel_item": "true"})["id"]
                    for u in image_urls]
        for c in children:
            self._wait_ready(c, token)
        parent = self._post(f"{ig_user_id}/media", token,
                            {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})["id"]
        self._wait_ready(parent, token)
        return self._post(f"{ig_user_id}/media_publish", token, {"creation_id": parent})["id"]

    def publishing_limit(self, ig_user_id: str, token: str) -> dict:
        r = self.http.get(f"{GRAPH}/{API_VERSION}/{ig_user_id}/content_publishing_limit",
                          params={"fields": "quota_usage,config", "access_token": token})
        if r.status_code != 200:
            raise _safe_error(r)
        data = r.json().get("data") or [{}]
        return data[0]
