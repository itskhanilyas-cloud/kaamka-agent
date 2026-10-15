import os
import hashlib
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import get_settings
from .db import init_engine
from .security import current_user

STATIC = Path(__file__).parent / "static"

SECURITY_HEADERS = {
    # Only our own scripts and styles; no inline script, no third-party code, no framing.
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                               "img-src 'self' data: https:; connect-src 'self'; frame-ancestors 'none'; "
                               "base-uri 'self'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def create_app() -> FastAPI:
    settings = get_settings()
    init_engine(settings.database_url)
    app = FastAPI(title="Kaam Ka AI — Instagram Business Agent", version="0.2.0",
                  docs_url="/api/docs" if settings.app_env != "production" else None, redoc_url=None)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-store")  # media sets its own
        elif request.url.path.startswith("/static"):
            response.headers.setdefault("Cache-Control", "no-cache")  # always revalidate (cheap: ETag)
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    app.include_router(router)
    from .instagram.routes import router as ig_router
    app.include_router(ig_router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "version": os.environ.get("KA_BUILD_VERSION", "dev")}

    @app.get("/whoami", include_in_schema=False)
    def whoami(user: str = Depends(current_user)):
        # Shows the signed-in identity so the owner can confirm KA_OWNER_EMAIL. Requires sign-in.
        return {"signed_in_as": user, "is_owner": user == settings.owner_email.lower()}

    # The dashboard shell holds no data; every number comes from /api, which requires the owner.
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    # Asset URLs carry a content hash, so a new deploy is picked up immediately, even from phone caches.
    def _ver(name: str) -> str:
        return hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:12]

    index_html = ((STATIC / "index.html").read_text()
                  .replace("/static/app.js", f"/static/app.js?v={_ver('app.js')}")
                  .replace("/static/app.css", f"/static/app.css?v={_ver('app.css')}"))

    @app.get("/", include_in_schema=False)
    def dashboard():
        return HTMLResponse(index_html, headers={"Cache-Control": "no-cache"})

    return app
