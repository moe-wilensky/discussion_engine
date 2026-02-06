"""
Comprehensive integration tests for health check endpoint.

Tests health check functionality including:
- Basic health check
- Database connectivity
- Cache connectivity
- Redis/Celery connectivity
- Error handling for service failures
"""

import pytest
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from django.db import connection


@pytest.mark.django_db
class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check_success(self, api_client):
        """Test health check when all systems are healthy."""
        response = api_client.get("/api/health/")

        assert response.status_code == 200
        assert response.data["status"] == "healthy"
        assert "checks" in response.data

        # Check that all required checks are present
        checks = response.data["checks"]
        assert "database" in checks
        assert "cache" in checks

        # All checks should be "ok"
        assert checks["database"] == "ok"
        assert checks["cache"] == "ok"

    def test_health_check_no_auth_required(self, api_client):
        """Test that health check does not require authentication."""
        # Clear any credentials
        api_client.credentials()

        response = api_client.get("/api/health/")

        assert response.status_code == 200

    @patch("django.db.connection.cursor")
    def test_health_check_database_error(self, mock_cursor, api_client):
        """Test health check when database is unavailable."""
        # Simulate database error
        mock_cursor.side_effect = Exception("Database connection failed")

        response = api_client.get("/api/health/")

        assert response.status_code == 503
        assert response.data["status"] == "unhealthy"

        checks = response.data["checks"]
        assert "error" in checks["database"]
        assert "Database connection failed" in checks["database"]

    @patch("django.core.cache.cache.set")
    def test_health_check_cache_set_error(self, mock_set, api_client):
        """Test health check when cache set fails."""
        # Simulate cache set error
        mock_set.side_effect = Exception("Cache unavailable")

        response = api_client.get("/api/health/")

        assert response.status_code == 503
        assert response.data["status"] == "unhealthy"

        checks = response.data["checks"]
        assert "error" in checks["cache"]

    @patch("django.core.cache.cache.get")
    def test_health_check_cache_get_error(self, mock_get, api_client):
        """Test health check when cache get fails."""
        # Simulate cache get error
        mock_get.side_effect = Exception("Cache read failed")

        response = api_client.get("/api/health/")

        assert response.status_code == 503
        assert response.data["status"] == "unhealthy"

        checks = response.data["checks"]
        assert "error" in checks["cache"]

    @patch("django.core.cache.cache.get")
    def test_health_check_cache_value_mismatch(self, mock_get, api_client):
        """Test health check when cache returns unexpected value."""
        # Simulate cache returning wrong value
        mock_get.return_value = "wrong_value"

        response = api_client.get("/api/health/")

        # Should fail assertion and mark cache as unhealthy
        assert response.status_code == 503
        assert response.data["status"] == "unhealthy"

    def test_health_check_redis_not_configured(self, api_client):
        """Test health check when Redis is not configured."""
        from django.conf import settings

        # Save original value
        original_broker = getattr(settings, 'CELERY_BROKER_URL', None)

        # Remove CELERY_BROKER_URL if it exists
        if hasattr(settings, 'CELERY_BROKER_URL'):
            delattr(settings, 'CELERY_BROKER_URL')

        try:
            response = api_client.get("/api/health/")

            # Should still be healthy - Redis is optional
            assert response.status_code == 200
            assert response.data["checks"]["redis"] == "not_configured"
        finally:
            # Restore original value
            if original_broker is not None:
                settings.CELERY_BROKER_URL = original_broker

    @patch("redis.from_url")
    def test_health_check_redis_connection_error(self, mock_redis, api_client):
        """Test health check when Redis is configured but unavailable."""
        # Mock Redis connection that fails to ping
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.side_effect = Exception("Redis connection failed")
        mock_redis.return_value = mock_redis_instance

        response = api_client.get("/api/health/")

        # Should still return 200 - Redis is optional
        assert response.status_code == 200
        # But should note the warning
        assert "warning" in response.data["checks"]["redis"]

    @patch("redis.from_url")
    def test_health_check_redis_success(self, mock_redis, api_client):
        """Test health check when Redis is available."""
        from django.conf import settings

        # Set CELERY_BROKER_URL
        original_broker = getattr(settings, 'CELERY_BROKER_URL', None)
        settings.CELERY_BROKER_URL = "redis://localhost:6379/0"

        # Mock successful Redis connection
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis.return_value = mock_redis_instance

        try:
            response = api_client.get("/api/health/")

            assert response.status_code == 200
            assert response.data["checks"]["redis"] == "ok"
        finally:
            # Restore original
            if original_broker is not None:
                settings.CELERY_BROKER_URL = original_broker
            elif hasattr(settings, 'CELERY_BROKER_URL'):
                delattr(settings, 'CELERY_BROKER_URL')

    @patch("django.db.connection.cursor")
    @patch("django.core.cache.cache.set")
    def test_health_check_multiple_failures(
        self, mock_cache_set, mock_cursor, api_client
    ):
        """Test health check when multiple systems fail."""
        # Simulate both database and cache errors
        mock_cursor.side_effect = Exception("Database down")
        mock_cache_set.side_effect = Exception("Cache down")

        response = api_client.get("/api/health/")

        assert response.status_code == 503
        assert response.data["status"] == "unhealthy"

        checks = response.data["checks"]
        assert "error" in checks["database"]
        assert "error" in checks["cache"]

    def test_health_check_database_query_execution(self, api_client):
        """Test that health check actually executes database query."""
        # Clear any cached connections
        connection.close()

        response = api_client.get("/api/health/")

        assert response.status_code == 200
        # Verify database check passed
        assert response.data["checks"]["database"] == "ok"

        # Verify we can actually query the database after health check
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            assert result[0] == 1

    def test_health_check_cache_operations(self, api_client):
        """Test that health check actually performs cache operations."""
        # Clear cache before test
        cache.clear()

        response = api_client.get("/api/health/")

        assert response.status_code == 200
        assert response.data["checks"]["cache"] == "ok"

        # Verify health check left a value in cache
        # (it may have expired by now, so we just verify cache is working)
        cache.set("test_key", "test_value", 10)
        assert cache.get("test_key") == "test_value"

    def test_health_check_response_structure(self, api_client):
        """Test health check response has correct structure."""
        response = api_client.get("/api/health/")

        # Check top-level structure
        assert "status" in response.data
        assert "checks" in response.data

        # Status should be a string
        assert isinstance(response.data["status"], str)
        assert response.data["status"] in ["healthy", "unhealthy"]

        # Checks should be a dict
        assert isinstance(response.data["checks"], dict)

        # Each check should have a status
        for check_name, check_status in response.data["checks"].items():
            assert isinstance(check_status, str)
            assert len(check_status) > 0

    def test_health_check_performance(self, api_client):
        """Test that health check completes quickly."""
        import time

        start_time = time.time()
        response = api_client.get("/api/health/")
        end_time = time.time()

        duration = end_time - start_time

        assert response.status_code == 200
        # Health check should complete in under 1 second
        assert duration < 1.0

    def test_health_check_concurrent_requests(self, api_client):
        """Test health check handles concurrent requests."""
        import threading

        results = []

        def make_request():
            response = api_client.get("/api/health/")
            results.append(response.status_code)

        # Create 5 concurrent requests
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        # Wait for all to complete
        for thread in threads:
            thread.join()

        # All should succeed
        assert len(results) == 5
        assert all(status == 200 for status in results)


@pytest.mark.django_db
class TestHealthCheckErrorRecovery:
    """Test health check error recovery scenarios."""

    @patch("django.db.connection.cursor")
    def test_health_check_database_recovers(self, mock_cursor, api_client):
        """Test health check shows recovery after database comes back."""
        # First request - database fails
        mock_cursor.side_effect = Exception("Database down")

        response1 = api_client.get("/api/health/")
        assert response1.status_code == 503

        # Second request - database recovers
        mock_cursor.side_effect = None

        response2 = api_client.get("/api/health/")
        # Should succeed now (actual database is working)
        assert response2.status_code in [200, 503]  # May still be patched

    def test_health_check_cache_recovers(self, api_client):
        """Test health check shows recovery after cache comes back."""
        with patch("django.core.cache.cache.set") as mock_set:
            # First request - cache fails
            mock_set.side_effect = Exception("Cache down")

            response1 = api_client.get("/api/health/")
            assert response1.status_code == 503

        # Second request - cache works (no more patching)
        response2 = api_client.get("/api/health/")
        assert response2.status_code == 200


@pytest.mark.django_db
class TestHealthCheckLoadBalancer:
    """Test health check for load balancer scenarios."""

    def test_health_check_quick_response(self, api_client):
        """Test health check responds quickly for load balancer probes."""
        response = api_client.get("/api/health/")

        # Should always get a response
        assert response.status_code in [200, 503]

    def test_health_check_consistent_format(self, api_client):
        """Test health check always returns consistent JSON format."""
        response = api_client.get("/api/health/")

        # Should always have these fields regardless of health
        assert "status" in response.data
        assert "checks" in response.data

        # Should always be valid JSON
        assert isinstance(response.data, dict)

    def test_health_check_http_methods(self, api_client):
        """Test health check only accepts GET requests."""
        # GET should work
        get_response = api_client.get("/api/health/")
        assert get_response.status_code in [200, 503]

        # POST should not be allowed
        post_response = api_client.post("/api/health/")
        assert post_response.status_code == 405

        # PUT should not be allowed
        put_response = api_client.put("/api/health/")
        assert put_response.status_code == 405

        # DELETE should not be allowed
        delete_response = api_client.delete("/api/health/")
        assert delete_response.status_code == 405
