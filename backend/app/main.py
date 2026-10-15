from fastapi import FastAPI

from .api import router
from .config import get_settings
from .db import init_engine


def create_app() -> FastAPI:
    settings = get_settings()
    init_engine(settings.database_url)
    app = FastAPI(title="Kaam Ka AI — Instagram Business Agent", version="0.1.0",
                  docs_url="/api/docs" if settings.app_env != "production" else None)
    app.include_router(router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app
