"""
User profile endpoint tests.

Tests for:
- GET /api/profile/me
- GET /api/profile/custom-prompt
- PUT /api/profile/custom-prompt
- DELETE /api/profile/custom-prompt
- DELETE /api/profile/me
"""
import pytest
from fastapi.testclient import TestClient

from models import User


class TestProfileEndpoints:
    """Test user profile endpoints."""

    def test_get_profile_no_auth(self, client: TestClient):
        """Test GET /api/profile/me without authentication."""
        response = client.get("/api/profile/me")
        assert response.status_code == 401  # HTTPBearer returns 401 for missing auth

    def test_get_profile_with_auth(
        self, client: TestClient, auth_headers, test_user, mock_redis
    ):
        """Test GET /api/profile/me with valid authentication."""
        response = client.get("/api/profile/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()

        # Check profile fields
        assert "email" in data
        assert "name" in data
        assert "surname" in data
        assert "groups" in data


class TestCustomPromptEndpoints:
    """Test custom prompt management endpoints."""

    def test_get_custom_prompt_empty(
        self, client: TestClient, auth_headers, test_user, mock_redis
    ):
        """Test GET /api/profile/custom-prompt when no prompt is set."""
        response = client.get("/api/profile/custom-prompt", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should return empty or null custom_prompt
        assert "custom_prompt" in data

    def test_set_custom_prompt(
        self, client: TestClient, auth_headers, test_user, db_session, mock_redis
    ):
        """Test PUT /api/profile/custom-prompt to set a custom prompt."""
        custom_prompt = "Please respond in a casual, friendly manner."
        response = client.put(
            "/api/profile/custom-prompt",
            json={"custom_prompt": custom_prompt},
            headers=auth_headers
        )
        assert response.status_code == 200

        # Verify it was saved
        response = client.get("/api/profile/custom-prompt", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("custom_prompt") == custom_prompt

    def test_clear_custom_prompt(
        self, client: TestClient, auth_headers, test_user, db_session, mock_redis
    ):
        """Test DELETE /api/profile/custom-prompt to clear the prompt."""
        # First set a prompt
        client.put(
            "/api/profile/custom-prompt",
            json={"custom_prompt": "Test prompt"},
            headers=auth_headers
        )

        # Then clear it
        response = client.delete("/api/profile/custom-prompt", headers=auth_headers)
        assert response.status_code == 200

        # Verify it was cleared
        response = client.get("/api/profile/custom-prompt", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("custom_prompt") is None or data.get("custom_prompt") == ""


class TestDeleteAccount:
    """Test account deletion endpoint."""

    def test_delete_account_no_auth(self, client: TestClient):
        """Test DELETE /api/profile/me without authentication."""
        response = client.delete("/api/profile/me")
        assert response.status_code == 401  # HTTPBearer returns 401 for missing auth

    @pytest.mark.integration
    def test_delete_account(
        self, client: TestClient, auth_headers, test_user, db_session, mock_redis
    ):
        """Test DELETE /api/profile/me to delete own account."""
        response = client.delete("/api/profile/me", headers=auth_headers)
        assert response.status_code == 200

        # Verify user was deleted
        user = db_session.query(User).filter(User.id == test_user.id).first()
        assert user is None
