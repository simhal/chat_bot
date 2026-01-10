"""Unit tests for editor_node.py status validation."""

import pytest
from unittest.mock import patch, MagicMock
from agents.nodes.editor_node import _handle_publish


class TestHandlePublishStatusValidation:
    """Test that _handle_publish correctly blocks non-editor status articles."""

    @pytest.fixture
    def admin_user_context(self):
        """User context for a global admin."""
        return {
            "user_id": 1,
            "email": "admin@test.com",
            "name": "Admin User",
            "scopes": ["global:admin"],
            "topic_roles": {}
        }

    @pytest.fixture
    def editor_user_context(self):
        """User context for a topic editor."""
        return {
            "user_id": 2,
            "email": "editor@test.com",
            "name": "Editor User",
            "scopes": ["fixed_income:editor"],
            "topic_roles": {"fixed_income": "editor"}
        }

    def test_draft_article_blocked_for_admin(self, admin_user_context):
        """Admin trying to publish a draft article should be blocked."""
        # Mock validate_article_access to return success with draft status
        mock_article_info = {
            "id": 29,
            "topic": "fixed_income",
            "status": "draft",  # Already normalized
            "headline": "Test Draft Article"
        }

        with patch('database.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            # Mock at the location where it's imported
            with patch('agents.nodes.editor_node.validate_article_access') as mock_validate:
                mock_validate.return_value = (True, None, mock_article_info)

                result = _handle_publish(29, "fixed_income", admin_user_context)

        print(f"Result: {result}")
        # Should NOT have confirmation, should have draft error message
        assert "confirmation" not in result or result.get("confirmation") is None
        assert "draft" in result.get("response_text", "").lower()
        assert "submitted for review" in result.get("response_text", "").lower()

    def test_editor_status_article_shows_confirmation(self, admin_user_context):
        """Article in editor status should show confirmation dialog."""
        mock_article_info = {
            "id": 20,
            "topic": "macro",
            "status": "editor",  # Correct status for publishing
            "headline": "Test Editor Article"
        }

        with patch('database.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            with patch('agents.nodes.editor_node.validate_article_access') as mock_validate:
                mock_validate.return_value = (True, None, mock_article_info)

                result = _handle_publish(20, "macro", admin_user_context)

        print(f"Result: {result}")
        # Should have confirmation for editor status article
        assert "confirmation" in result
        assert result["confirmation"]["type"] == "publish_approval"

    def test_published_article_blocked(self, admin_user_context):
        """Already published article should be blocked."""
        mock_article_info = {
            "id": 18,
            "topic": "technical",
            "status": "published",
            "headline": "Already Published Article"
        }

        with patch('database.SessionLocal') as mock_session:
            mock_db = MagicMock()
            mock_session.return_value = mock_db

            with patch('agents.nodes.editor_node.validate_article_access') as mock_validate:
                mock_validate.return_value = (True, None, mock_article_info)

                result = _handle_publish(18, "technical", admin_user_context)

        print(f"Result: {result}")
        # Should NOT have confirmation
        assert "confirmation" not in result or result.get("confirmation") is None
        assert "already" in result.get("response_text", "").lower()
        assert "published" in result.get("response_text", "").lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
