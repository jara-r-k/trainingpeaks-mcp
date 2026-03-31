"""End-to-end cache integration tests.

Validates that the ResponseCache is correctly wired into TPClient:
  - GET requests are cached and served from cache on repeat calls
  - POST/PUT/DELETE mutations invalidate related cached entries
  - TTL resolution maps endpoints to the correct cache tier
  - cache_key is always defined before use (no possibly-undefined)
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tp_mcp.client.cache import CacheTier, ResponseCache, build_cache_key
from tp_mcp.client.http import APIResponse, TPClient


@pytest.fixture(autouse=True)
def _reset_class_state():
    """Reset TPClient class-level state between tests."""
    TPClient._shared_token_cache = None
    TPClient._response_cache = None
    TPClient._cached_athlete_id = None
    TPClient._cached_user_data = None
    yield
    TPClient._shared_token_cache = None
    TPClient._response_cache = None
    TPClient._cached_athlete_id = None
    TPClient._cached_user_data = None


class TestCacheIntegrationE2E:
    """End-to-end tests for cache wiring in TPClient."""

    @pytest.mark.asyncio
    async def test_get_profile_caches_on_second_call(self):
        """GET /users/v3/user should cache — second call skips the network."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": 123, "FirstName": "Test"}
        mock_response.headers = {}

        with patch("tp_mcp.client.http.httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.aclose = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_http

            client = TPClient()
            client._client = mock_http
            # Pre-set a valid token so we skip the token exchange flow
            client._token_cache.access_token = "test-token"
            client._token_cache.expires_at = time.time() + 3600

            result1 = await client.get("/users/v3/user")
            result2 = await client.get("/users/v3/user")

            # First call hits the network, second should be served from cache
            assert result1.success
            assert result2.success
            assert result2.data == {"Id": 123, "FirstName": "Test"}
            assert mock_http.request.call_count == 1

            await client.close()

    @pytest.mark.asyncio
    async def test_uncacheable_endpoint_always_hits_network(self):
        """Endpoints not in _CACHE_TTL_MAP should never be cached."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.headers = {}

        with patch("tp_mcp.client.http.httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.aclose = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_http

            client = TPClient()
            client._client = mock_http
            client._token_cache.access_token = "test-token"
            client._token_cache.expires_at = time.time() + 3600

            await client.get("/some/random/endpoint")
            await client.get("/some/random/endpoint")

            # Both calls should hit the network
            assert mock_http.request.call_count == 2

            await client.close()

    @pytest.mark.asyncio
    async def test_cache_disabled_flag_bypasses_cache(self):
        """GET with cache=False should always hit the network."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": 123}
        mock_response.headers = {}

        with patch("tp_mcp.client.http.httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.aclose = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_http

            client = TPClient()
            client._client = mock_http
            client._token_cache.access_token = "test-token"
            client._token_cache.expires_at = time.time() + 3600

            await client.get("/users/v3/user", cache=False)
            await client.get("/users/v3/user", cache=False)

            assert mock_http.request.call_count == 2

            await client.close()

    @pytest.mark.asyncio
    async def test_post_invalidates_related_cache(self):
        """POST should invalidate cached entries for the same endpoint."""
        endpoint = "/fitness/v1/athletes/123/reporting/performancedata/2026-01-01/2026-03-31"

        # Set up a client with a pre-populated cache
        mock_response_get = MagicMock()
        mock_response_get.status_code = 200
        mock_response_get.json.return_value = [{"ctl": 50, "atl": 40}]
        mock_response_get.headers = {}

        mock_response_post = MagicMock()
        mock_response_post.status_code = 200
        mock_response_post.json.return_value = {"success": True}
        mock_response_post.headers = {}

        with patch("tp_mcp.client.http.httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.aclose = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response_get)
            mock_client_cls.return_value = mock_http

            client = TPClient()
            client._client = mock_http
            client._token_cache.access_token = "test-token"
            client._token_cache.expires_at = time.time() + 3600

            # GET populates cache (endpoint matches fitness pattern)
            await client.get(endpoint)
            assert mock_http.request.call_count == 1

            # POST invalidates the cache for this endpoint
            mock_http.request.return_value = mock_response_post
            await client.post(endpoint, json={"data": "new"})

            # Next GET should hit the network again
            mock_http.request.return_value = mock_response_get
            await client.get(endpoint)

            # 1 GET + 1 POST + 1 GET = 3 network calls
            assert mock_http.request.call_count == 3

            await client.close()

    @pytest.mark.asyncio
    async def test_put_invalidates_cache(self):
        """PUT should invalidate cached entries for the same endpoint."""
        endpoint = "/users/v3/user"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": 123}
        mock_response.headers = {}

        with patch("tp_mcp.client.http.httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.aclose = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_http

            client = TPClient()
            client._client = mock_http
            client._token_cache.access_token = "test-token"
            client._token_cache.expires_at = time.time() + 3600

            # Populate cache
            await client.get(endpoint)
            assert mock_http.request.call_count == 1

            # PUT invalidates
            await client.put(endpoint, json={"name": "Updated"})

            # Next GET must hit the network
            await client.get(endpoint)
            # 1 GET + 1 PUT + 1 GET = 3
            assert mock_http.request.call_count == 3

            await client.close()

    @pytest.mark.asyncio
    async def test_delete_invalidates_cache(self):
        """DELETE should invalidate cached entries for the same endpoint."""
        endpoint = "/users/v3/user"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": 123}
        mock_response.headers = {}

        with patch("tp_mcp.client.http.httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.aclose = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_http

            client = TPClient()
            client._client = mock_http
            client._token_cache.access_token = "test-token"
            client._token_cache.expires_at = time.time() + 3600

            # Populate cache
            await client.get(endpoint)
            # DELETE invalidates
            await client.delete(endpoint)
            # Next GET must hit the network
            await client.get(endpoint)

            # 1 GET + 1 DELETE + 1 GET = 3
            assert mock_http.request.call_count == 3

            await client.close()

    @pytest.mark.asyncio
    async def test_failed_response_is_not_cached(self):
        """Error responses should never be stored in the cache."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {}
        mock_response.headers = {}
        mock_response.text = "Internal Server Error"

        with patch("tp_mcp.client.http.httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.aclose = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_http

            client = TPClient()
            client._client = mock_http
            client._token_cache.access_token = "test-token"
            client._token_cache.expires_at = time.time() + 3600

            result1 = await client.get("/users/v3/user")
            result2 = await client.get("/users/v3/user")

            assert not result1.success
            assert not result2.success
            # Both calls hit the network — error was not cached
            assert mock_http.request.call_count == 2

            await client.close()

    @pytest.mark.asyncio
    async def test_cache_stats_reflect_usage(self):
        """cache_stats() should track hits and misses accurately."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": 123}
        mock_response.headers = {}

        with patch("tp_mcp.client.http.httpx.AsyncClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.aclose = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_http

            client = TPClient()
            client._client = mock_http
            client._token_cache.access_token = "test-token"
            client._token_cache.expires_at = time.time() + 3600

            # First call: miss (nothing cached yet), then stored
            await client.get("/users/v3/user")
            # Second call: hit from cache
            await client.get("/users/v3/user")

            stats = client.cache_stats()
            assert stats["hits"] == 1
            assert stats["misses"] == 1
            assert stats["size"] == 1

            await client.close()


class TestResolveTTL:
    """Tests for endpoint-to-TTL resolution."""

    def test_profile_endpoint(self):
        client = TPClient()
        assert client._resolve_ttl("/users/v3/user") == CacheTier.PROFILE.value

    def test_fitness_v1_endpoint(self):
        client = TPClient()
        ttl = client._resolve_ttl("/fitness/v1/athletes/123/settings")
        assert ttl == CacheTier.WORKOUT_LIST.value

    def test_fitness_v2_endpoint(self):
        client = TPClient()
        ttl = client._resolve_ttl("/fitness/v2/athletes/123/zones")
        assert ttl == CacheTier.WORKOUT_DETAIL.value

    def test_fitness_v6_workouts_endpoint(self):
        client = TPClient()
        ttl = client._resolve_ttl("/fitness/v6/athletes/123/workouts")
        assert ttl == CacheTier.WORKOUT_LIST.value

    def test_personal_records_endpoint(self):
        client = TPClient()
        ttl = client._resolve_ttl("/personalrecord/v1/athletes/123/peaks")
        assert ttl == CacheTier.WORKOUT_LIST.value

    def test_metrics_endpoint(self):
        client = TPClient()
        ttl = client._resolve_ttl("/metrics/v1/athletes/123/daily")
        assert ttl == CacheTier.WORKOUT_LIST.value

    def test_unknown_endpoint_returns_none(self):
        client = TPClient()
        assert client._resolve_ttl("/some/random/path") is None


class TestCacheInvalidationDirect:
    """Direct tests for cache invalidation via ResponseCache API."""

    def test_invalidate_exact_endpoint(self):
        cache = ResponseCache()
        cache.put("/workouts/v1/athletes/123/workouts", "key1", {"data": "cached"}, CacheTier.WORKOUT_LIST.value)

        assert cache.get("/workouts/v1/athletes/123/workouts", "key1") is not None

        cache.invalidate("/workouts/v1/athletes/123/workouts")

        assert cache.get("/workouts/v1/athletes/123/workouts", "key1") is None

    def test_invalidate_does_not_affect_other_endpoints(self):
        cache = ResponseCache()
        cache.put("/endpoint/a", "key1", "data_a", CacheTier.PROFILE.value)
        cache.put("/endpoint/b", "key2", "data_b", CacheTier.PROFILE.value)

        cache.invalidate("/endpoint/a")

        assert cache.get("/endpoint/a", "key1") is None
        assert cache.get("/endpoint/b", "key2") == "data_b"

    def test_invalidate_all_clears_everything(self):
        cache = ResponseCache()
        cache.put("/endpoint/a", "key1", "data_a", CacheTier.PROFILE.value)
        cache.put("/endpoint/b", "key2", "data_b", CacheTier.WORKOUT_LIST.value)

        removed = cache.invalidate()
        assert removed == 2

        assert cache.get("/endpoint/a", "key1") is None
        assert cache.get("/endpoint/b", "key2") is None
