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
            # Phase 6 passes the real Instagram publisher here; until then this is always a dry run.
            result = publishing.run_due(db, publishing.get_publisher(settings), settings)
            db.commit()
            print(f"publish job: {result}")
            return 0
        print(f"unknown job '{job}'. Available: publish")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
