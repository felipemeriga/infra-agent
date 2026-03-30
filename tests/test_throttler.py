# tests/test_throttler.py
import time
from unittest.mock import patch


def test_throttler_allows_first_notification():
    from throttler import NotificationThrottler

    t = NotificationThrottler(cooldown=900)
    assert t.should_notify("rag-backend", "die") is True


def test_throttler_blocks_duplicate_within_cooldown():
    from throttler import NotificationThrottler

    t = NotificationThrottler(cooldown=900)
    t.record("rag-backend", "die")
    assert t.should_notify("rag-backend", "die") is False


def test_throttler_allows_after_cooldown_expires():
    from throttler import NotificationThrottler

    t = NotificationThrottler(cooldown=10)
    t.record("rag-backend", "die")

    with patch("time.time", return_value=time.time() + 11):
        assert t.should_notify("rag-backend", "die") is True


def test_throttler_allows_different_event_types():
    from throttler import NotificationThrottler

    t = NotificationThrottler(cooldown=900)
    t.record("rag-backend", "die")
    assert t.should_notify("rag-backend", "oom") is True


def test_throttler_allows_different_services():
    from throttler import NotificationThrottler

    t = NotificationThrottler(cooldown=900)
    t.record("rag-backend", "die")
    assert t.should_notify("rag-frontend", "die") is True


def test_throttler_force_bypasses_cooldown():
    from throttler import NotificationThrottler

    t = NotificationThrottler(cooldown=900)
    t.record("rag-backend", "die")
    assert t.should_notify("rag-backend", "die", force=True) is True


def test_throttler_clear_resets_service():
    from throttler import NotificationThrottler

    t = NotificationThrottler(cooldown=900)
    t.record("rag-backend", "die")
    t.clear("rag-backend")
    assert t.should_notify("rag-backend", "die") is True
