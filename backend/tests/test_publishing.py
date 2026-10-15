from datetime import timedelta

from app.models import ActionKind, ActionStatus, Post, PostStatus, utcnow
from app.services import approvals, publishing
from tests.conftest import OWNER


def _approved_post(db, scheduled_at=None):
    post = Post(media_type="IMAGE", caption="tip", media_urls=["a.png"], scheduled_at=scheduled_at)
    db.add(post)
    db.flush()
    req = approvals.request_action(db, ActionKind.publish_post, OWNER, post=post)
    approvals.decide(db, req, OWNER, OWNER, approve=True)
    return post, req


class FlakyPublisher:
    def __init__(self, failures, exc=publishing.TransientPublishError):
        self.failures, self.exc, self.calls = failures, exc, 0

    def publish(self, post, key):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc("temporary")
        return "ig-123"


def test_non_production_always_dry_runs(settings_env):
    real = FlakyPublisher(0)
    assert isinstance(publishing.get_publisher(settings_env, real), publishing.DryRunPublisher)


def test_unapproved_posts_are_never_published(db, settings_env):
    post = Post(media_type="IMAGE", caption="tip", media_urls=["a.png"])
    db.add(post)
    db.flush()
    approvals.request_action(db, ActionKind.publish_post, OWNER, post=post)  # pending, not approved
    pub = publishing.DryRunPublisher()
    assert publishing.run_due(db, pub, settings_env).published == 0
    assert pub.calls == []


def test_publishes_once_even_if_run_twice(db, settings_env):
    post, req = _approved_post(db)
    pub = publishing.DryRunPublisher()
    publishing.run_due(db, pub, settings_env)
    publishing.run_due(db, pub, settings_env)
    assert len(pub.calls) == 1
    assert post.status == PostStatus.published and req.status == ActionStatus.executed


def test_future_scheduled_post_waits(db, settings_env):
    _approved_post(db, scheduled_at=utcnow() + timedelta(hours=2))
    pub = publishing.DryRunPublisher()
    assert publishing.run_due(db, pub, settings_env).published == 0
    assert publishing.run_due(db, pub, settings_env, now=utcnow() + timedelta(hours=3)).published == 1


def test_daily_cap(db, settings_env):  # cap is 2 in tests
    for _ in range(3):
        _approved_post(db)
    result = publishing.run_due(db, publishing.DryRunPublisher(), settings_env)
    assert result.published == 2 and result.skipped_cap == 1


def test_transient_errors_retry_then_succeed(db, settings_env):
    post, req = _approved_post(db)
    pub = FlakyPublisher(failures=2)
    publishing.run_due(db, pub, settings_env)
    publishing.run_due(db, pub, settings_env)
    assert req.status == ActionStatus.approved  # still waiting to retry
    publishing.run_due(db, pub, settings_env)
    assert post.ig_media_id == "ig-123" and req.attempts == 3


def test_gives_up_after_max_attempts(db, settings_env):
    post, req = _approved_post(db)
    pub = FlakyPublisher(failures=99)
    for _ in range(5):
        publishing.run_due(db, pub, settings_env)
    assert pub.calls == publishing.MAX_ATTEMPTS
    assert req.status == ActionStatus.failed and post.status == PostStatus.failed


def test_permanent_error_is_not_retried(db, settings_env):
    post, req = _approved_post(db)
    pub = FlakyPublisher(failures=99, exc=publishing.PermanentPublishError)
    publishing.run_due(db, pub, settings_env)
    publishing.run_due(db, pub, settings_env)
    assert pub.calls == 1 and req.status == ActionStatus.failed


def test_production_without_instagram_never_marks_published(db, settings_env, monkeypatch):
    monkeypatch.setattr(settings_env, "app_env", "production")
    post, req = _approved_post(db)
    pub = publishing.get_publisher(settings_env, None)  # no real Instagram publisher yet
    result = publishing.run_due(db, pub, settings_env)
    assert result.published == 0 and post.status == PostStatus.approved and req.status == ActionStatus.approved
