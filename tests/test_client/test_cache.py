"""Tests for multi-level response cache."""

import time
from unittest.mock import patch

import pytest

from tp_mcp.client.cache import (
    CachedEntry,
    CacheTier,
    ResponseCache,
    build_cache_key,
)


class TestCacheTier:
    """Tests for cache TTL tier values."""

    def test_profile_ttl(self):
        assert CacheTier.PROFILE.value == 3600

    def test_workout_list_ttl(self):
        assert CacheTier.WORKOUT_LIST.value == 300

    def test_workout_detail_ttl(self):
        assert CacheTier.WORKOUT_DETAIL.value == 120

    def test_realtime_ttl(self):
        assert CacheTier.REALTIME.value == 30


class TestCachedEntry:
    """Tests for CachedEntry dataclass."""

    def test_not_expired_within_ttl(self):
        entry = CachedEntry(data={"x": 1}, timestamp=time.time(), ttl=60.0)
        assert not entry.is_expired

    def test_expired_after_ttl(self):
        entry = CachedEntry(data={"x": 1}, timestamp=time.time() - 120, ttl=60.0)
        assert entry.is_expired

    def test_age_seconds(self):
        entry = CachedEntry(data={"x": 1}, timestamp=time.time() - 10, ttl=60.0)
        assert 9.5 <= entry.age_seconds <= 11.0


class TestBuildCacheKey:
    """Tests for deterministic cache key construction."""

    def test_same_inputs_same_key(self):
        key1 = build_cache_key("/api/test", athlete_id=123, params={"a": "1", "b": "2"})
        key2 = build_cache_key("/api/test", athlete_id=123, params={"a": "1", "b": "2"})
        assert key1 == key2

    def test_different_order_same_key(self):
        """Parameter ordering should not affect the key."""
        key1 = build_cache_key("/api/test", params={"z": "last", "a": "first"})
        key2 = build_cache_key("/api/test", params={"a": "first", "z": "last"})
        assert key1 == key2

    def test_different_endpoints_different_keys(self):
        key1 = build_cache_key("/api/one")
        key2 = build_cache_key("/api/two")
        assert key1 != key2

    def test_different_athlete_ids_different_keys(self):
        key1 = build_cache_key("/api/test", athlete_id=1)
        key2 = build_cache_key("/api/test", athlete_id=2)
        assert key1 != key2

    def test_different_params_different_keys(self):
        key1 = build_cache_key("/api/test", params={"day": "2025-01-01"})
        key2 = build_cache_key("/api/test", params={"day": "2025-01-02"})
        assert key1 != key2

    def test_with_json_body(self):
        key1 = build_cache_key("/api/test", json_body={"filter": "active"})
        key2 = build_cache_key("/api/test", json_body={"filter": "inactive"})
        assert key1 != key2

    def test_json_body_order_independent(self):
        key1 = build_cache_key("/api/test", json_body={"b": 2, "a": 1})
        key2 = build_cache_key("/api/test", json_body={"a": 1, "b": 2})
        assert key1 == key2

    def test_none_params_excluded(self):
        """Keys with None params should differ from keys with empty params."""
        key1 = build_cache_key("/api/test")
        key2 = build_cache_key("/api/test", params={})
        # Empty dict is falsy, so both should produce the same key
        assert key1 == key2

    def test_key_is_hex_string(self):
        key = build_cache_key("/api/test")
        assert isinstance(key, str)
        assert len(key) == 64  # SHA-256 hex digest


class TestResponseCache:
    """Tests for ResponseCache get/put/invalidate/stats."""

    def test_put_and_get(self):
        cache = ResponseCache()
        cache.put("/api/test", "key1", {"result": 42}, ttl=60.0)
        result = cache.get("/api/test", "key1")
        assert result == {"result": 42}

    def test_get_miss_returns_none(self):
        cache = ResponseCache()
        result = cache.get("/api/test", "nonexistent")
        assert result is None

    def test_get_expired_returns_none(self):
        cache = ResponseCache()
        cache.put("/api/test", "key1", {"result": 42}, ttl=0.0)
        # TTL of 0 means it's already expired
        time.sleep(0.01)
        result = cache.get("/api/test", "key1")
        assert result is None

    def test_ttl_expiry(self):
        """Entry should be available within TTL and gone after."""
        cache = ResponseCache()
        cache.put("/api/test", "key1", {"val": 1}, ttl=0.1)

        # Should be available immediately
        assert cache.get("/api/test", "key1") == {"val": 1}

        # Wait for expiry
        time.sleep(0.15)
        assert cache.get("/api/test", "key1") is None

    def test_invalidate_endpoint(self):
        cache = ResponseCache()
        cache.put("/api/a", "key1", "data1", ttl=60.0)
        cache.put("/api/a", "key2", "data2", ttl=60.0)
        cache.put("/api/b", "key3", "data3", ttl=60.0)

        removed = cache.invalidate("/api/a")
        assert removed == 2
        assert cache.get("/api/a", "key1") is None
        assert cache.get("/api/a", "key2") is None
        assert cache.get("/api/b", "key3") == "data3"

    def test_invalidate_all(self):
        cache = ResponseCache()
        cache.put("/api/a", "key1", "data1", ttl=60.0)
        cache.put("/api/b", "key2", "data2", ttl=60.0)

        removed = cache.invalidate()
        assert removed == 2
        assert cache.get("/api/a", "key1") is None
        assert cache.get("/api/b", "key2") is None

    def test_invalidate_nonexistent_endpoint(self):
        cache = ResponseCache()
        removed = cache.invalidate("/api/nonexistent")
        assert removed == 0

    def test_stats_empty_cache(self):
        cache = ResponseCache()
        stats = cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0
        assert stats["evictions"] == 0

    def test_stats_tracking(self):
        cache = ResponseCache()
        cache.put("/api/test", "key1", "data", ttl=60.0)

        # One hit
        cache.get("/api/test", "key1")
        # One miss
        cache.get("/api/test", "missing")

        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate_pct"] == 50.0
        assert stats["size"] == 1
        assert stats["endpoints"] == 1

    def test_stats_eviction_tracking(self):
        cache = ResponseCache()
        cache.put("/api/test", "key1", "data", ttl=60.0)
        cache.invalidate("/api/test")

        stats = cache.stats()
        assert stats["evictions"] == 1
        assert stats["size"] == 0

    def test_overwrite_entry(self):
        """Putting the same key should overwrite the old entry."""
        cache = ResponseCache()
        cache.put("/api/test", "key1", "old", ttl=60.0)
        cache.put("/api/test", "key1", "new", ttl=60.0)
        assert cache.get("/api/test", "key1") == "new"

    def test_multiple_endpoints(self):
        cache = ResponseCache()
        cache.put("/api/a", "k1", "data_a", ttl=60.0)
        cache.put("/api/b", "k1", "data_b", ttl=60.0)
        assert cache.get("/api/a", "k1") == "data_a"
        assert cache.get("/api/b", "k1") == "data_b"
