"""
Prompt management endpoint tests.

Tests for:
- GET /api/prompts (list prompt modules)
- GET /api/prompts/tonalities (get tonality options)
- GET /api/prompts/{module_id} (get prompt)
- PUT /api/prompts/{module_id} (update prompt)
- POST /api/prompts/tonality (create tonality)
- DELETE /api/prompts/{module_id} (delete prompt)
- GET /api/prompts/user/tonality (get user tonality preferences)
- PUT /api/prompts/user/tonality (update user tonality preferences)
"""
import pytest
from fastapi.testclient import TestClient

from models import PromptModule, PromptType


class TestPromptListEndpoints:
    """Test prompt listing endpoints."""

    def test_list_prompts_no_auth(self, client: TestClient):
        """Test GET /api/prompts without authentication."""
        response = client.get("/api/prompts")
        assert response.status_code == 401  # HTTPBearer returns 401 for missing auth

    def test_list_prompts_with_auth(
        self, client: TestClient, auth_headers, test_prompt, mock_redis
    ):
        """Test GET /api/prompts with authentication."""
        response = client.get("/api/prompts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_tonalities(
        self, client: TestClient, auth_headers, test_tonality, mock_redis
    ):
        """Test GET /api/prompts/tonalities."""
        response = client.get("/api/prompts/tonalities", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least our test tonality
        assert len(data) >= 1


class TestPromptDetailEndpoints:
    """Test individual prompt endpoints."""

    def test_get_prompt_by_id(
        self, client: TestClient, auth_headers, test_prompt, mock_redis
    ):
        """Test GET /api/prompts/{module_id}."""
        response = client.get(
            f"/api/prompts/{test_prompt.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == test_prompt.name

    def test_get_prompt_not_found(
        self, client: TestClient, auth_headers, mock_redis
    ):
        """Test GET /api/prompts/{module_id} for non-existent prompt."""
        response = client.get("/api/prompts/99999", headers=auth_headers)
        assert response.status_code == 404


class TestPromptAdminEndpoints:
    """Test prompt admin management endpoints."""

    def test_update_prompt_no_admin(
        self, client: TestClient, auth_headers, test_prompt, mock_redis
    ):
        """Test PUT /api/prompts/{module_id} without admin permission."""
        response = client.put(
            f"/api/prompts/{test_prompt.id}",
            json={"template_text": "Hacked prompt"},
            headers=auth_headers
        )
        # Depending on implementation, may be 403 or 401
        assert response.status_code in [403, 401]

    def test_update_prompt_with_admin(
        self, client: TestClient, admin_headers, test_prompt, db_session, mock_redis
    ):
        """Test PUT /api/prompts/{module_id} with admin permission."""
        # Template must be at least 50 characters
        long_template = "This is an updated prompt text for testing purposes. It needs to be at least 50 characters long to pass validation."
        response = client.put(
            f"/api/prompts/{test_prompt.id}",
            json={
                "template_text": long_template,
                "description": "Updated description"
            },
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "updated prompt" in data["template_text"].lower()

    def test_create_tonality(
        self, client: TestClient, admin_headers, db_session, mock_redis
    ):
        """Test POST /api/prompts/tonality."""
        # Template must be at least 50 characters for validation
        response = client.post(
            "/api/prompts/tonality",
            json={
                "name": "Casual Tone",
                "template_text": "Respond in a casual, conversational manner. Be friendly and approachable in your responses. Use informal language where appropriate.",
                "description": "Casual writing style"
            },
            headers=admin_headers
        )
        assert response.status_code == 201  # Returns 201 Created
        data = response.json()
        assert data["name"] == "Casual Tone"
        assert data["prompt_type"] == "tonality"

    def test_create_content_agent_prompt(
        self, client: TestClient, admin_headers, test_topic, db_session, mock_redis
    ):
        """Test POST /api/prompts/content-agent."""
        # Template must be at least 50 characters for validation
        response = client.post(
            "/api/prompts/content-agent",
            json={
                "name": "Test Content Agent Prompt",
                "template_text": "Focus on financial analysis and market research. Provide detailed insights into market trends and economic indicators.",
                "prompt_group": test_topic.slug,  # Must be an existing topic slug
                "description": "Content agent for test topic"
            },
            headers=admin_headers
        )
        assert response.status_code == 201  # Returns 201 Created
        data = response.json()
        assert data["prompt_type"] == "content_topic"

    def test_delete_prompt(
        self, client: TestClient, admin_headers, db_session, mock_redis
    ):
        """Test DELETE /api/prompts/{module_id}."""
        # Create a prompt to delete
        prompt = PromptModule(
            name="To Delete",
            prompt_type=PromptType.TONALITY,
            template_text="Delete me",
            is_active=True
        )
        db_session.add(prompt)
        db_session.commit()
        prompt_id = prompt.id

        response = client.delete(
            f"/api/prompts/{prompt_id}",
            headers=admin_headers
        )
        assert response.status_code == 200

        # Verify it's deactivated (soft delete)
        db_session.refresh(prompt)
        assert prompt.is_active == False

    def test_set_default_tonality(
        self, client: TestClient, admin_headers, test_tonality, db_session, mock_redis
    ):
        """Test POST /api/prompts/tonality/{module_id}/set-default."""
        response = client.post(
            f"/api/prompts/tonality/{test_tonality.id}/set-default",
            headers=admin_headers
        )
        assert response.status_code == 200


class TestUserTonalityEndpoints:
    """Test user tonality preference endpoints."""

    def test_get_user_tonality(
        self, client: TestClient, auth_headers, mock_redis
    ):
        """Test GET /api/prompts/user/tonality."""
        response = client.get("/api/prompts/user/tonality", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should have chat_tonality and content_tonality fields
        assert "chat_tonality_id" in data or "chat_tonality" in data

    def test_update_user_tonality(
        self, client: TestClient, auth_headers, test_tonality, db_session, mock_redis
    ):
        """Test PUT /api/prompts/user/tonality."""
        response = client.put(
            "/api/prompts/user/tonality",
            json={
                "chat_tonality_id": test_tonality.id,
                "content_tonality_id": test_tonality.id
            },
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_admin_get_user_tonality(
        self, client: TestClient, admin_headers, test_user, mock_redis
    ):
        """Test GET /api/prompts/admin/user/{user_id}/tonality."""
        response = client.get(
            f"/api/prompts/admin/user/{test_user.id}/tonality",
            headers=admin_headers
        )
        assert response.status_code == 200

    def test_admin_set_user_tonality(
        self, client: TestClient, admin_headers, test_user, test_tonality, db_session, mock_redis
    ):
        """Test PUT /api/prompts/admin/user/{user_id}/tonality."""
        response = client.put(
            f"/api/prompts/admin/user/{test_user.id}/tonality",
            json={
                "chat_tonality_id": test_tonality.id,
                "content_tonality_id": test_tonality.id
            },
            headers=admin_headers
        )
        assert response.status_code == 200
