"""Cache effectiveness benchmarks for TrainingPeaks MCP.

Verifies that repeated API calls to the same endpoint hit the cache
rather than triggering redundant network requests, and that cache
statistics are accurately reported for monitoring.
"""

import pytest
from tp_mcp.client.cache import ResponseCache, CacheTier


class TestCacheBenchmarks:
    def test_repeated_gets_use_cache(self):
        """Repeated GET calls to same endpoint should hit cache after first call."""
        cache = ResponseCache()
        cache.put(
            "/fitness/v1/athletes/123/summary",
            "key1",
            {"ctl": 50},
            CacheTier.PROFILE.value,
        )

        for _ in range(10):
            result = cache.get("/fitness/v1/athletes/123/summary", "key1")
            assert result is not None

        stats = cache.stats()
        assert stats["hits"] >= 10
        assert stats["hit_rate_pct"] > 90.0

    def test_cache_stats_report(self):
        """Cache stats should be reportable for monitoring."""
        cache = ResponseCache()
        cache.put("/endpoint/a", "k1", {}, CacheTier.WORKOUT_LIST.value)
        cache.put("/endpoint/b", "k2", {}, CacheTier.PROFILE.value)
        cache.get("/endpoint/a", "k1")  # hit
        cache.get("/endpoint/c", "k3")  # miss

        stats = cache.stats()
        assert stats["size"] == 2
        assert stats["hits"] == 1
        assert stats["misses"] == 1
