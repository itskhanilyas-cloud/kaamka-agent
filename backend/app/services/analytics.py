"""Results from real Instagram numbers only. Nothing here is estimated or predicted."""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AccountSnapshot, Post, PostMetric, PostStatus

MIN_POSTS_FOR_LESSONS = 3


def _rate(part, whole):
    return round(part / whole, 4) if part is not None and whole else None


def latest_metrics(db: Session) -> dict[str, PostMetric]:
    out: dict[str, PostMetric] = {}
    for m in db.scalars(select(PostMetric).order_by(PostMetric.fetched_at)).all():
        out[m.post_id] = m  # later rows overwrite earlier ones
    return out


def summary(db: Session) -> dict:
    latest = latest_metrics(db)
    posts = db.scalars(select(Post).where(Post.status == PostStatus.published).order_by(Post.published_at.desc())).all()
    rows = []
    for p in posts:
        m = latest.get(p.id)
        hook = (p.content or {}).get("hook") or (p.caption or "")[:60]
        row = {"id": p.id, "hook": hook, "format": p.media_type.value, "pillar": p.pillar,
               "published_at": p.published_at, "ig_media_id": p.ig_media_id, "has_data": m is not None}
        if m:
            row.update(views=m.views, reach=m.reach, likes=m.likes, comments=m.comments, saved=m.saved,
                       shares=m.shares, interactions=m.total_interactions, avg_watch_s=(m.avg_watch_ms or 0) / 1000 or None,
                       save_rate=_rate(m.saved, m.reach), share_rate=_rate(m.shares, m.reach), fetched_at=m.fetched_at)
        rows.append(row)

    snaps = db.scalars(select(AccountSnapshot).order_by(AccountSnapshot.fetched_at.desc()).limit(60)).all()
    with_data = [r for r in rows if r["has_data"]]
    totals = {k: sum(r.get(k) or 0 for r in with_data) for k in ("views", "reach", "likes", "comments", "saved", "shares")}
    return {
        "followers": snaps[0].followers if snaps else None,
        "followers_history": [{"at": s.fetched_at, "followers": s.followers} for s in reversed(snaps)],
        "last_synced_at": max((r["fetched_at"] for r in with_data), default=None),
        "posts": rows,
        "totals": totals,
        "lessons": lessons(with_data),
    }


def lessons(rows: list[dict]) -> list[str]:
    """Plain comparisons between groups of real posts. Says so when there isn't enough data."""
    if len(rows) < MIN_POSTS_FOR_LESSONS:
        need = MIN_POSTS_FOR_LESSONS - len(rows)
        return [f"Not enough data yet: {need} more published post{'s' if need > 1 else ''} with numbers before comparisons mean anything."]
    out = []
    for key, label in (("format", "format"), ("pillar", "topic")):
        groups = defaultdict(list)
        for r in rows:
            if r.get("reach"):
                groups[r.get(key) or "other"].append(r)
        scored = {g: sum((x.get("saved") or 0) + (x.get("shares") or 0) for x in v) / sum(x["reach"] for x in v)
                  for g, v in groups.items() if len(v) >= 2}
        if len(scored) >= 2:
            best = max(scored, key=scored.get)
            worst = min(scored, key=scored.get)
            out.append(f"By {label}: '{best}' gets the most saves + shares per person reached "
                       f"({scored[best]:.1%}) vs '{worst}' ({scored[worst]:.1%}). Based on {len(rows)} posts; treat as a hint, not a rule.")
    top = max(rows, key=lambda r: ((r.get("saved") or 0) + (r.get("shares") or 0), r.get("reach") or 0))
    out.append(f"Most saved + shared so far: \"{top['hook'][:70]}\" ({(top.get('saved') or 0)} saves, {(top.get('shares') or 0)} shares).")
    return out
