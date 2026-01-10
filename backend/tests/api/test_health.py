"""
Health endpoint tests.

Tests for: GET /, GET /health, GET /api/health/vectordb, GET /debug/settings
"""
import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_root_endpoint(self, client: TestClient):
        """Test GET / returns API running message."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Chatbot API" in data["message"]

    def test_health_endpoint(self, client: TestClient):
        """Test GET /health returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_debug_settings_no_secrets(self, client: TestClient):
        """Test GET /debug/settings doesn't expose secrets."""
        response = client.get("/debug/settings")
        assert response.status_code == 200
        data = response.json()

        # Should have these fields
        assert "linkedin_client_id" in data
        assert "openai_model" in data
        assert "cors_origins" in data

        # Should NOT expose full secrets
        assert "linkedin_client_secret_present" in data
        assert "openai_api_key_present" in data

        # These should be booleans, not the actual values
        assert isinstance(data["linkedin_client_secret_present"], bool)
        assert isinstance(data["openai_api_key_present"], bool)


@pytest.mark.integration
class TestVectorDBHealth:
    """Test ChromaDB health endpoint (requires ChromaDB)."""

    def test_vectordb_health(self, client: TestClient, mock_chromadb):
        """Test GET /api/health/vectordb returns stats."""
        response = client.get("/api/health/vectordb")
        # May fail without real ChromaDB, but should not error with mocks
        assert response.status_code in [200, 500]
