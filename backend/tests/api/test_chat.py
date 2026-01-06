"""
Chat endpoint tests.

Tests for:
- POST /api/chat
- GET /api/chat/history
- DELETE /api/chat/history
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestChatEndpoint:
    """Test POST /api/chat endpoint."""

    def test_chat_no_auth(self, client: TestClient):
        """Test chat without authentication."""
        response = client.post(
            "/api/chat",
            json={"message": "Hello"}
        )
        assert response.status_code == 401  # HTTPBearer returns 401 for missing auth

    @pytest.mark.integration
    def test_chat_basic_message(
        self, client: TestClient, auth_headers, mock_redis, mock_openai, mock_chromadb
    ):
        """Test basic chat message."""
        with patch("services.agent_service.AgentService") as mock_service:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "response": "Hello! How can I help you today?",
                "agent_type": "router",
                "routing_reason": "General greeting",
                "articles": []
            }
            mock_service.return_value = mock_instance

            response = client.post(
                "/api/chat",
                json={"message": "Hello"},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "response" in data
            assert "Hello" in data["response"]

    @pytest.mark.integration
    def test_chat_with_navigation_context(
        self, client: TestClient, auth_headers, mock_redis, mock_openai, mock_chromadb
    ):
        """Test chat with navigation context."""
        with patch("services.agent_service.AgentService") as mock_service:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "response": "I can help with macro analysis.",
                "agent_type": "content_agent",
                "routing_reason": "Topic-specific query",
                "articles": []
            }
            mock_service.return_value = mock_instance

            response = client.post(
                "/api/chat",
                json={
                    "message": "Tell me about GDP trends",
                    "navigation_context": {
                        "section": "reader",
                        "topic": "macro",
                        "role": "reader"
                    }
                },
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "response" in data

    @pytest.mark.integration
    def test_chat_response_with_articles(
        self, client: TestClient, auth_headers, mock_redis, mock_openai, mock_chromadb
    ):
        """Test chat response includes article references."""
        with patch("services.agent_service.AgentService") as mock_service:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "response": "Here's what I found about inflation.",
                "agent_type": "content_agent",
                "routing_reason": "Research query",
                "articles": [
                    {"id": 1, "topic": "macro", "headline": "Inflation Analysis 2024"}
                ]
            }
            mock_service.return_value = mock_instance

            response = client.post(
                "/api/chat",
                json={"message": "Tell me about inflation"},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "articles" in data
            assert len(data["articles"]) == 1
            assert data["articles"][0]["headline"] == "Inflation Analysis 2024"

    @pytest.mark.integration
    def test_chat_response_with_navigation_command(
        self, client: TestClient, auth_headers, mock_redis, mock_openai, mock_chromadb
    ):
        """Test chat response includes navigation command."""
        with patch("services.agent_service.AgentService") as mock_service:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "response": "Navigating to macro topic.",
                "agent_type": "router",
                "routing_reason": "Navigation request",
                "articles": [],
                "navigation": {
                    "action": "navigate",
                    "target": "/",
                    "params": {"topic": "macro"}
                }
            }
            mock_service.return_value = mock_instance

            response = client.post(
                "/api/chat",
                json={"message": "Show me macro articles"},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "navigation" in data
            assert data["navigation"]["action"] == "navigate"

    @pytest.mark.integration
    def test_chat_response_with_ui_action(
        self, client: TestClient, auth_headers, mock_redis, mock_openai, mock_chromadb
    ):
        """Test chat response includes UI action."""
        with patch("services.agent_service.AgentService") as mock_service:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = {
                "response": "I'll submit your article for review.",
                "agent_type": "analyst_agent",
                "routing_reason": "Analyst workflow",
                "articles": [],
                "ui_action": {
                    "type": "submit_for_review",
                    "params": {"article_id": 123}
                }
            }
            mock_service.return_value = mock_instance

            response = client.post(
                "/api/chat",
                json={"message": "Submit my article for review"},
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert "ui_action" in data
            assert data["ui_action"]["type"] == "submit_for_review"


class TestChatHistory:
    """Test chat history endpoints."""

    def test_get_history_no_auth(self, client: TestClient):
        """Test GET /api/chat/history without authentication."""
        response = client.get("/api/chat/history")
        assert response.status_code == 401  # HTTPBearer returns 401 for missing auth

    @pytest.mark.integration
    def test_get_history_empty(
        self, client: TestClient, auth_headers, mock_redis
    ):
        """Test GET /api/chat/history with no history."""
        with patch("conversation_memory.create_conversation_memory") as mock_memory:
            mock_memory.return_value = MagicMock(messages=[])

            response = client.get("/api/chat/history", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert "history" in data
            assert isinstance(data["history"], list)

    def test_clear_history_no_auth(self, client: TestClient):
        """Test DELETE /api/chat/history without authentication."""
        response = client.delete("/api/chat/history")
        assert response.status_code == 401  # HTTPBearer returns 401 for missing auth

    @pytest.mark.integration
    def test_clear_history(
        self, client: TestClient, auth_headers, mock_redis
    ):
        """Test DELETE /api/chat/history clears history."""
        with patch("conversation_memory.clear_conversation_history") as mock_clear:
            response = client.delete("/api/chat/history", headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert "cleared" in data["message"].lower() or "success" in data["message"].lower()
            mock_clear.assert_called_once()
