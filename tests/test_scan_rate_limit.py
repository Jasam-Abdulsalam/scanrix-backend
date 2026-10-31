import asyncio
import time

import pytest
from fastapi import HTTPException

from app.api import deps
from app.core.config import settings
from app.db import redis as redis_module


class FakeRedis:
    def __init__(self, fail=False):
        self.counts, self.ttls, self.fail = {}, {}, fail

    def incr(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key, seconds):
        self.ttls[key] = seconds


USER = {"_id": "u1"}
NOW = 1_000_040  # 20 seconds into a minute (1_000_040 % 60 == 20)


def setup(monkeypatch, limit=3, now=NOW, fail=False):
    r = FakeRedis(fail)
    monkeypatch.setattr(redis_module, "get_redis", lambda: r)
    monkeypatch.setattr(time, "time", lambda: now)
    monkeypatch.setattr(settings, "SCAN_RATE_LIMIT_PER_MINUTE", limit)
    monkeypatch.setattr(settings, "TEST_MODE", False)  # don't inherit a local .env TEST_MODE=true
    return r


def scan():
    return asyncio.run(deps.check_rate_limit(USER))


def test_allows_up_to_the_limit_then_429_with_code_and_retry_after(monkeypatch):
    r = setup(monkeypatch, limit=3)
    for _ in range(3):
        assert scan() is USER
    with pytest.raises(HTTPException) as e:
        scan()
    assert e.value.status_code == 429
    assert e.value.detail["code"] == "scan_rate_limited"
    assert e.value.headers["Retry-After"] == "40"  # seconds left in the current minute
    assert list(r.ttls.values()) == [60]


def test_next_minute_starts_a_fresh_window(monkeypatch):
    setup(monkeypatch, limit=1)
    scan()
    monkeypatch.setattr(time, "time", lambda: NOW + 60)
    assert scan() is USER


def test_fails_open_when_redis_is_down(monkeypatch):
    setup(monkeypatch, fail=True)
    assert scan() is USER


def test_test_mode_skips_the_limit(monkeypatch):
    r = setup(monkeypatch, limit=1)
    monkeypatch.setattr(settings, "TEST_MODE", True)
    for _ in range(5):
        assert scan() is USER
    assert r.counts == {}
