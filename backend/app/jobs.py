"""Entry point for Container Apps Jobs.

  python -m app.jobs publish        every 15 min: approved posts whose scheduled time has come
  python -m app.jobs sync-metrics   every 6 h: views, reach, likes, saves, shares, followers
  python -m app.jobs refresh-token  daily: renews Instagram access well before it expires
"""
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
            from .instagram.routes import publisher_for
            real = publisher_for(db, settings)
            result = publishing.run_due(db, publishing.get_publisher(settings, real), settings, scheduled_only=True)
            db.commit()
            print(f"publish job: {result} dry_run={real is None}")
            return 0
        if job in ("refresh-token", "sync-metrics") and not settings.instagram_ready:
            print("instagram not configured"); return 0
        if job == "refresh-token":
            from .instagram.routes import client_for
            from .instagram.service import refresh_if_due
            print("token:", refresh_if_due(db, client_for(settings), settings.token_encryption_key.get_secret_value(), "system:agent"))
            db.commit()
            return 0
        if job == "sync-metrics":
            from .instagram.routes import client_for
            from .instagram.service import NotConfigured, sync_metrics
            try:
                print("metrics:", sync_metrics(db, client_for(settings), settings.token_encryption_key.get_secret_value()))
            except NotConfigured as e:
                print(e); return 0
            db.commit()
            return 0
        print(f"unknown job '{job}'. Available: publish, sync-metrics, refresh-token")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
