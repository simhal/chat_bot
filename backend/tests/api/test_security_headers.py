"""
Security headers tests.

Tests for HTTP security headers on API responses.
Verifies that all security-critical headers are present and correctly configured.
"""
import pytest
from fastapi.testclient import TestClient


class TestSecurityHeaders:
    """Test that security headers are present on all responses."""

    def test_x_frame_options_header(self, client: TestClient):
        """Test X-Frame-Options header prevents clickjacking."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_x_content_type_options_header(self, client: TestClient):
        """Test X-Content-Type-Options prevents MIME sniffing."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_xss_protection_header(self, client: TestClient):
        """Test X-XSS-Protection enables browser XSS filter."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_strict_transport_security_header(self, client: TestClient):
        """Test HSTS header enforces HTTPS."""
        response = client.get("/health")
        assert response.status_code == 200
        hsts = response.headers.get("Strict-Transport-Security")
        assert hsts is not None
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts

    def test_content_security_policy_header(self, client: TestClient):
        """Test CSP header restricts content sources."""
        response = client.get("/health")
        assert response.status_code == 200
        csp = response.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_referrer_policy_header(self, client: TestClient):
        """Test Referrer-Policy header limits referrer leakage."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy_header(self, client: TestClient):
        """Test Permissions-Policy restricts browser features."""
        response = client.get("/health")
        assert response.status_code == 200
        pp = response.headers.get("Permissions-Policy")
        assert pp is not None
        assert "camera=()" in pp
        assert "microphone=()" in pp
        assert "geolocation=()" in pp

    def test_security_headers_on_authenticated_endpoint(
        self, client: TestClient, auth_headers, mock_redis
    ):
        """Test security headers are present on authenticated endpoints."""
        response = client.get("/api/me", headers=auth_headers)
        assert response.status_code == 200

        # All headers should be present
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert response.headers.get("Strict-Transport-Security") is not None
        assert response.headers.get("Content-Security-Policy") is not None
        assert response.headers.get("Referrer-Policy") is not None
        assert response.headers.get("Permissions-Policy") is not None

    def test_security_headers_on_error_response(self, client: TestClient):
        """Test security headers are present even on error responses."""
        response = client.get("/nonexistent-endpoint")
        assert response.status_code == 404

        # Security headers should still be present
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_security_headers_on_post_endpoint(
        self, client: TestClient, auth_headers, mock_redis
    ):
        """Test security headers on POST requests."""
        response = client.post(
            "/api/auth/logout",
            json={},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-Content-Type-Options") == "nosniff"


class TestCORSConfiguration:
    """Test CORS configuration is properly tightened."""

    def test_cors_preflight_request(self, client: TestClient):
        """Test CORS preflight OPTIONS request returns expected headers."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )
        # CORS preflight should succeed
        assert response.status_code == 200

    def test_cors_allows_configured_origin(self, client: TestClient):
        """Test that configured origins are allowed."""
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )
        assert response.status_code == 200
        # Origin should be reflected in allow-origin header
        allow_origin = response.headers.get("Access-Control-Allow-Origin")
        assert allow_origin == "http://localhost:3000"

    def test_cors_credentials_allowed(self, client: TestClient):
        """Test that credentials are properly allowed."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )
        assert response.headers.get("Access-Control-Allow-Credentials") == "true"

    def test_cors_allowed_methods_preflight(self, client: TestClient):
        """Test CORS preflight returns allowed methods."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST"
            }
        )
        allowed_methods = response.headers.get("Access-Control-Allow-Methods", "")

        # These should be allowed
        assert "GET" in allowed_methods
        assert "POST" in allowed_methods
        assert "PUT" in allowed_methods
        assert "DELETE" in allowed_methods

    def test_cors_allowed_headers_preflight(self, client: TestClient):
        """Test CORS preflight returns allowed headers."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type"
            }
        )
        allowed_headers = response.headers.get("Access-Control-Allow-Headers", "").lower()

        # These should be allowed
        assert "authorization" in allowed_headers
        assert "content-type" in allowed_headers


class TestSecurityHeadersComprehensive:
    """Comprehensive security header tests across different endpoint types."""

    def test_all_headers_on_root(self, client: TestClient):
        """Test all security headers on root endpoint."""
        response = client.get("/")
        assert response.status_code == 200

        expected_headers = [
            "X-Frame-Options",
            "X-Content-Type-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
            "Content-Security-Policy",
            "Referrer-Policy",
            "Permissions-Policy"
        ]

        for header in expected_headers:
            assert response.headers.get(header) is not None, f"Missing header: {header}"

    def test_headers_on_json_response(self, client: TestClient):
        """Test security headers on JSON API response."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/json"

        # Security headers should be present
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_headers_on_unauthorized_request(self, client: TestClient):
        """Test security headers on 401 unauthorized response."""
        response = client.get("/api/me")  # No auth header
        assert response.status_code == 401

        # Security headers should still be present
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("Content-Security-Policy") is not None
