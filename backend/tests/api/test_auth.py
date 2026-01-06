"""
Authentication endpoint tests.

Tests for:
- POST /api/auth/token (LinkedIn OAuth exchange)
- POST /api/auth/refresh (Token refresh)
- POST /api/auth/logout (Logout)

Note: LinkedIn OAuth tests require mocking external API calls.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from models import User, Group


class TestAuthTokenExchange:
    """Test POST /api/auth/token endpoint."""

    @pytest.mark.integration
    def test_token_exchange_invalid_code(self, client: TestClient):
        """Test token exchange with invalid authorization code."""
        response = client.post(
            "/api/auth/token",
            json={
                "code": "invalid_code",
                "redirect_uri": "http://localhost:3000/auth/callback"
            }
        )
        # Should fail because LinkedIn will reject the code
        assert response.status_code in [400, 500]

    def test_token_exchange_missing_code(self, client: TestClient):
        """Test token exchange without authorization code."""
        response = client.post(
            "/api/auth/token",
            json={
                "redirect_uri": "http://localhost:3000/auth/callback"
            }
        )
        assert response.status_code == 422  # Validation error


class TestAuthRefresh:
    """Test POST /api/auth/refresh endpoint."""

    def test_refresh_invalid_token(self, client: TestClient, mock_redis):
        """Test refresh with invalid token."""
        response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid_token"}
        )
        assert response.status_code == 401
        assert "Invalid or expired" in response.json()["detail"]

    def test_refresh_missing_token(self, client: TestClient):
        """Test refresh without token."""
        response = client.post(
            "/api/auth/refresh",
            json={}
        )
        assert response.status_code == 422  # Validation error


class TestAuthLogout:
    """Test POST /api/auth/logout endpoint."""

    def test_logout_no_auth(self, client: TestClient):
        """Test logout without authorization header."""
        response = client.post("/api/auth/logout", json={})
        assert response.status_code == 401  # No auth header returns 401

    def test_logout_invalid_token(self, client: TestClient, mock_redis):
        """Test logout with invalid token."""
        response = client.post(
            "/api/auth/logout",
            json={},
            headers={"Authorization": "Bearer invalid_token"}
        )
        # Invalid tokens still allow logout (fail gracefully)
        # The API accepts invalid tokens for logout to ensure cleanup
        assert response.status_code in [200, 401]

    def test_logout_valid_token(self, client: TestClient, auth_headers, mock_redis):
        """Test logout with valid token."""
        response = client.post(
            "/api/auth/logout",
            json={},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert "Successfully logged out" in response.json()["message"]

    def test_logout_with_refresh_token(self, client: TestClient, auth_headers, mock_redis):
        """Test logout with both access and refresh tokens."""
        response = client.post(
            "/api/auth/logout",
            json={"refresh_token": "some_refresh_token"},
            headers=auth_headers
        )
        assert response.status_code == 200


class TestAuthenticatedAccess:
    """Test that protected endpoints require authentication."""

    def test_me_endpoint_no_auth(self, client: TestClient):
        """Test /api/me without authentication."""
        response = client.get("/api/me")
        assert response.status_code == 401  # HTTPBearer returns 401 for missing auth

    def test_me_endpoint_with_auth(self, client: TestClient, auth_headers, mock_redis):
        """Test /api/me with valid authentication."""
        response = client.get("/api/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "email" in data
        assert "scopes" in data

    def test_invalid_bearer_token(self, client: TestClient):
        """Test with malformed bearer token."""
        response = client.get(
            "/api/me",
            headers={"Authorization": "Bearer malformed.token.here"}
        )
        assert response.status_code == 401


class TestUserInfoEndpoint:
    """Test GET /api/me endpoint."""

    def test_user_info_returns_correct_fields(
        self, client: TestClient, auth_headers, test_user, mock_redis
    ):
        """Test that user info contains expected fields."""
        response = client.get("/api/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "id" in data
        assert "name" in data
        assert "surname" in data
        assert "email" in data
        assert "picture" in data
        assert "scopes" in data

        # Scopes should be a list
        assert isinstance(data["scopes"], list)
