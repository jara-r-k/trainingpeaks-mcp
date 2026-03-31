"""Multi-level response cache for TrainingPeaks API.

Provides TTL-based caching of API responses to minimise redundant
network calls. Cache keys are deterministic and order-independent.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("tp-mcp")


class CacheTier(Enum):
    """TTL tiers for different data freshness requirements."""

    PROFILE = 3600      # 1 hour — rarely changes
    WORKOUT_LIST = 300  # 5 minutes — updated after syncs
    WORKOUT_DETAIL = 120  # 2 minutes — individual workout data
    REALTIME = 30       # 30 seconds — actively changing data


@dataclass
class CachedEntry:
    """A single cached API response with metadata."""

    data: Any
    timestamp: float
    ttl: float
    endpoint: str = ""

    @property
    def is_expired(self) -> bool:
        """Check whether this entry has exceeded its TTL."""
        return time.time() > (self.timestamp + self.ttl)

    @property
    def age_seconds(self) -> float:
        """Seconds since this entry was cached."""
        return time.time() - self.timestamp


def build_cache_key(
    endpoint: str,
    athlete_id: int | None = None,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> str:
    """Build a deterministic cache key from request components.

    The key is constructed by sorting all parameters alphabetically
    before hashing, so ordering of dict keys does not affect the
    result. This prevents collisions caused by parameter reordering.

    Args:
        endpoint: The API endpoint path.
        athlete_id: The athlete ID (included for namespace isolation).
        params: Query parameters dict.
        json_body: JSON request body dict.

    Returns:
        A hex digest string suitable as a cache key.
    """
    key_parts: dict[str, Any] = {
        "endpoint": endpoint,
    }
    if athlete_id is not None:
        key_parts["athlete_id"] = athlete_id
    if params:
        key_parts["params"] = params
    if json_body:
        key_parts["json_body"] = json_body

    # sort_keys ensures deterministic serialisation regardless of
    # the insertion order of dict keys
    canonical = json.dumps(key_parts, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class ResponseCache:
    """In-memory API response cache with TTL-based expiry.

    Organised as endpoint -> params_hash -> CachedEntry for efficient
    invalidation of entire endpoint families.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, CachedEntry]] = {}
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0

    def get(self, endpoint: str, cache_key: str) -> Any | None:
        """Retrieve a cached response if it exists and has not expired.

        Args:
            endpoint: The API endpoint (used as first-level key).
            cache_key: The deterministic hash key.

        Returns:
            The cached data, or None if not found / expired.
        """
        bucket = self._store.get(endpoint)
        if bucket is None:
            self._misses += 1
            logger.debug("Cache MISS (no bucket): %s", endpoint)
            return None

        entry = bucket.get(cache_key)
        if entry is None:
            self._misses += 1
            logger.debug("Cache MISS (no entry): %s", endpoint)
            return None

        if entry.is_expired:
            del bucket[cache_key]
            if not bucket:
                del self._store[endpoint]
            self._evictions += 1
            self._misses += 1
            logger.debug(
                "Cache MISS (expired after %.1fs): %s",
                entry.age_seconds,
                endpoint,
            )
            return None

        self._hits += 1
        logger.debug(
            "Cache HIT (age %.1fs / TTL %.0fs): %s",
            entry.age_seconds,
            entry.ttl,
            endpoint,
        )
        return entry.data

    def put(
        self,
        endpoint: str,
        cache_key: str,
        data: Any,
        ttl: float,
    ) -> None:
        """Store a response in the cache.

        Args:
            endpoint: The API endpoint (first-level key).
            cache_key: The deterministic hash key.
            data: The response data to cache.
            ttl: Time-to-live in seconds.
        """
        if endpoint not in self._store:
            self._store[endpoint] = {}

        self._store[endpoint][cache_key] = CachedEntry(
            data=data,
            timestamp=time.time(),
            ttl=ttl,
            endpoint=endpoint,
        )
        logger.debug("Cache PUT (TTL %.0fs): %s", ttl, endpoint)

    def invalidate(self, endpoint: str | None = None) -> int:
        """Remove cached entries.

        Args:
            endpoint: If provided, only invalidate entries for this
                endpoint. If None, clear the entire cache.

        Returns:
            Number of entries removed.
        """
        if endpoint is None:
            count = sum(len(bucket) for bucket in self._store.values())
            self._store.clear()
            self._evictions += count
            logger.debug("Cache INVALIDATE ALL: removed %d entries", count)
            return count

        bucket = self._store.pop(endpoint, {})
        count = len(bucket)
        self._evictions += count
        logger.debug(
            "Cache INVALIDATE endpoint %s: removed %d entries",
            endpoint,
            count,
        )
        return count

    def stats(self) -> dict[str, Any]:
        """Return cache performance statistics.

        Returns:
            Dict with hits, misses, hit_rate, size, and evictions.
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        size = sum(len(bucket) for bucket in self._store.values())
        endpoints = len(self._store)

        stats_dict = {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 1),
            "size": size,
            "endpoints": endpoints,
            "evictions": self._evictions,
        }
        logger.info("Cache stats: %s", stats_dict)
        return stats_dict
