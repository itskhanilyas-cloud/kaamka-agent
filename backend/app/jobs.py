"""Entry point for Container Apps Jobs: `python -m app.jobs publish`."""
import sys

from .config import get_settings
from .db import get_db, init_engine
from .services import publishing


def main(argv: list[str]) -> int:
    settings = get_settings()
    init_engine(settings.database_url)
    job = argv[1] if len(argv) > 1 else ""
    db = next(get_db())
    try:
        if job == "publish":
            real = None
            if settings.app_env == "production" and settings.instagram_ready:
                from .instagram.routes import client_for
                from .instagram.service import InstagramPublisher, NotConfigured
                try:
                    real = InstagramPublisher(db, client_for(settings), settings.token_encryption_key.get_secret_value(),
                                              settings.public_base_url)
                except NotConfigured:
                    real = None
            result = publishing.run_due(db, publishing.get_publisher(settings, real), settings)
            db.commit()
            print(f"publish job: {result}")
            return 0
        if job == "refresh-token":
            if not settings.instagram_ready:
                print("instagram not configured"); return 0
            from .instagram.routes import client_for
            from .instagram.service import refresh_if_due
            print("token:", refresh_if_due(db, client_for(settings), settings.token_encryption_key.get_secret_value(), "system:agent"))
            db.commit()
            return 0
        print(f"unknown job '{job}'. Available: publish, refresh-token")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
