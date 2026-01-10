"""
Unit tests for topic_manager module.

Tests for:
- get_visible_topics() - returns topics visible in reader section
- get_ai_accessible_topics() - returns topics accessible by AI agents
- get_ai_accessible_topic_slugs() - returns list of AI-accessible topic slugs
- infer_topic() - topic inference with ai_only parameter
- TopicConfig dataclass fields
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from agents.topic_manager import (
    TopicConfig,
    get_visible_topics,
    get_ai_accessible_topics,
    get_ai_accessible_topic_slugs,
    infer_topic,
    is_valid_topic,
    refresh_cache,
    RESERVED_KEYWORDS,
    _topics_cache,
)


class TestTopicConfig:
    """Test TopicConfig dataclass."""

    def test_topic_config_default_values(self):
        """Test TopicConfig has correct default values."""
        config = TopicConfig(
            slug="test",
            name="Test Topic",
            description="Test description"
        )
        assert config.slug == "test"
        assert config.name == "Test Topic"
        assert config.description == "Test description"
        assert config.active is True
        assert config.visible is True
        assert config.access_mainchat is True
        assert config.order == 0

    def test_topic_config_custom_values(self):
        """Test TopicConfig with custom values."""
        config = TopicConfig(
            slug="hidden",
            name="Hidden Topic",
            description="A hidden topic",
            active=True,
            visible=False,
            access_mainchat=False,
            order=5
        )
        assert config.visible is False
        assert config.access_mainchat is False
        assert config.order == 5


class TestReservedKeywords:
    """Test reserved keywords configuration."""

    def test_global_not_reserved(self):
        """Test that 'global' is NOT in reserved keywords."""
        assert "global" not in RESERVED_KEYWORDS

    def test_navigation_keywords_reserved(self):
        """Test that navigation keywords are reserved."""
        expected_reserved = {"home", "search", "analyst", "editor", "admin", "profile"}
        assert expected_reserved.issubset(RESERVED_KEYWORDS)


class TestGetVisibleTopics:
    """Test get_visible_topics function."""

    @patch("agents.topic_manager._load_topics_from_db")
    def test_returns_only_visible_topics(self, mock_load):
        """Test that only visible topics are returned."""
        mock_load.return_value = {
            "visible_topic": TopicConfig(
                slug="visible_topic",
                name="Visible",
                description="",
                active=True,
                visible=True,
                access_mainchat=True,
                order=1
            ),
            "hidden_topic": TopicConfig(
                slug="hidden_topic",
                name="Hidden",
                description="",
                active=True,
                visible=False,
                access_mainchat=True,
                order=2
            ),
            "inactive_topic": TopicConfig(
                slug="inactive_topic",
                name="Inactive",
                description="",
                active=False,
                visible=True,
                access_mainchat=True,
                order=3
            ),
        }

        result = get_visible_topics()

        assert len(result) == 1
        assert result[0].slug == "visible_topic"

    @patch("agents.topic_manager._load_topics_from_db")
    def test_returns_sorted_by_order(self, mock_load):
        """Test that visible topics are sorted by order."""
        mock_load.return_value = {
            "topic_c": TopicConfig(
                slug="topic_c", name="C", description="",
                active=True, visible=True, order=3
            ),
            "topic_a": TopicConfig(
                slug="topic_a", name="A", description="",
                active=True, visible=True, order=1
            ),
            "topic_b": TopicConfig(
                slug="topic_b", name="B", description="",
                active=True, visible=True, order=2
            ),
        }

        result = get_visible_topics()

        assert len(result) == 3
        assert result[0].slug == "topic_a"
        assert result[1].slug == "topic_b"
        assert result[2].slug == "topic_c"


class TestGetAIAccessibleTopics:
    """Test get_ai_accessible_topics function."""

    @patch("agents.topic_manager._load_topics_from_db")
    def test_returns_only_ai_accessible_topics(self, mock_load):
        """Test that only AI-accessible topics are returned."""
        mock_load.return_value = {
            "ai_topic": TopicConfig(
                slug="ai_topic",
                name="AI Accessible",
                description="",
                active=True,
                visible=True,
                access_mainchat=True,
                order=1
            ),
            "no_ai_topic": TopicConfig(
                slug="no_ai_topic",
                name="No AI",
                description="",
                active=True,
                visible=True,
                access_mainchat=False,
                order=2
            ),
            "inactive_ai_topic": TopicConfig(
                slug="inactive_ai_topic",
                name="Inactive AI",
                description="",
                active=False,
                visible=True,
                access_mainchat=True,
                order=3
            ),
        }

        result = get_ai_accessible_topics()

        assert len(result) == 1
        assert result[0].slug == "ai_topic"

    @patch("agents.topic_manager._load_topics_from_db")
    def test_returns_sorted_by_order(self, mock_load):
        """Test that AI-accessible topics are sorted by order."""
        mock_load.return_value = {
            "topic_z": TopicConfig(
                slug="topic_z", name="Z", description="",
                active=True, access_mainchat=True, order=10
            ),
            "topic_m": TopicConfig(
                slug="topic_m", name="M", description="",
                active=True, access_mainchat=True, order=5
            ),
        }

        result = get_ai_accessible_topics()

        assert len(result) == 2
        assert result[0].slug == "topic_m"
        assert result[1].slug == "topic_z"


class TestGetAIAccessibleTopicSlugs:
    """Test get_ai_accessible_topic_slugs function."""

    @patch("agents.topic_manager._load_topics_from_db")
    def test_returns_list_of_slugs(self, mock_load):
        """Test that a list of slugs is returned."""
        mock_load.return_value = {
            "macro": TopicConfig(
                slug="macro", name="Macro", description="",
                active=True, access_mainchat=True, order=1
            ),
            "equity": TopicConfig(
                slug="equity", name="Equity", description="",
                active=True, access_mainchat=True, order=2
            ),
            "hidden": TopicConfig(
                slug="hidden", name="Hidden", description="",
                active=True, access_mainchat=False, order=3
            ),
        }

        result = get_ai_accessible_topic_slugs()

        assert isinstance(result, list)
        assert len(result) == 2
        assert "macro" in result
        assert "equity" in result
        assert "hidden" not in result


class TestInferTopic:
    """Test infer_topic function with ai_only parameter."""

    @patch("agents.topic_manager._load_topics_from_db")
    def test_infer_topic_ai_only_default(self, mock_load):
        """Test that ai_only=True is the default behavior."""
        mock_load.return_value = {
            "macro": TopicConfig(
                slug="macro", name="Macroeconomic Research", description="",
                active=True, access_mainchat=True, order=1
            ),
            "internal": TopicConfig(
                slug="internal", name="Internal Docs", description="",
                active=True, access_mainchat=False, order=2
            ),
        }

        # Should match AI-accessible topic
        result = infer_topic("Tell me about macro economics")
        assert result == "macro"

        # Should NOT match non-AI topic (ai_only=True is default)
        result = infer_topic("Tell me about internal docs")
        assert result is None

    @patch("agents.topic_manager._load_topics_from_db")
    def test_infer_topic_ai_only_false(self, mock_load):
        """Test that ai_only=False includes non-AI topics."""
        mock_load.return_value = {
            "internal": TopicConfig(
                slug="internal", name="Internal Docs", description="",
                active=True, access_mainchat=False, order=1
            ),
        }

        # Should NOT match with ai_only=True (default)
        result = infer_topic("Tell me about internal docs", ai_only=True)
        assert result is None

        # Should match with ai_only=False
        result = infer_topic("Tell me about internal docs", ai_only=False)
        assert result == "internal"

    @patch("agents.topic_manager._load_topics_from_db")
    def test_infer_topic_exact_slug_match(self, mock_load):
        """Test exact slug matching."""
        mock_load.return_value = {
            "macro": TopicConfig(
                slug="macro", name="Macro Economics", description="",
                active=True, access_mainchat=True, order=1
            ),
        }

        result = infer_topic("Show me macro articles")
        assert result == "macro"

    @patch("agents.topic_manager._load_topics_from_db")
    def test_infer_topic_title_match(self, mock_load):
        """Test title-based matching."""
        mock_load.return_value = {
            "esg": TopicConfig(
                slug="esg", name="ESG Research", description="",
                active=True, access_mainchat=True, order=1
            ),
        }

        result = infer_topic("I want to read about ESG research")
        assert result == "esg"

    @patch("agents.topic_manager._load_topics_from_db")
    def test_infer_topic_no_match(self, mock_load):
        """Test when no topic matches."""
        mock_load.return_value = {
            "macro": TopicConfig(
                slug="macro", name="Macro", description="",
                active=True, access_mainchat=True, order=1
            ),
        }

        result = infer_topic("Tell me about weather")
        assert result is None

    @patch("agents.topic_manager._load_topics_from_db")
    def test_infer_topic_inactive_skipped(self, mock_load):
        """Test that inactive topics are skipped."""
        mock_load.return_value = {
            "inactive": TopicConfig(
                slug="inactive", name="Inactive Topic", description="",
                active=False, access_mainchat=True, order=1
            ),
        }

        result = infer_topic("Tell me about inactive topic")
        assert result is None

    @patch("agents.topic_manager._load_topics_from_db")
    def test_infer_topic_reserved_keywords_excluded(self, mock_load):
        """Test that reserved keywords are excluded from results."""
        mock_load.return_value = {
            "admin": TopicConfig(
                slug="admin", name="Admin Topic", description="",
                active=True, access_mainchat=True, order=1
            ),
            "macro": TopicConfig(
                slug="macro", name="Macro", description="",
                active=True, access_mainchat=True, order=2
            ),
        }

        # "admin" is a reserved keyword and should be excluded
        result = infer_topic("Show me admin stuff")
        assert result != "admin"


class TestIsValidTopic:
    """Test is_valid_topic function."""

    @patch("agents.topic_manager._load_topics_from_db")
    def test_valid_active_topic(self, mock_load):
        """Test that valid active topics return True."""
        mock_load.return_value = {
            "macro": TopicConfig(
                slug="macro", name="Macro", description="",
                active=True, order=1
            ),
        }

        assert is_valid_topic("macro") is True

    @patch("agents.topic_manager._load_topics_from_db")
    def test_nonexistent_topic(self, mock_load):
        """Test that nonexistent topics return False."""
        mock_load.return_value = {}

        assert is_valid_topic("nonexistent") is False

    def test_reserved_keyword_invalid(self):
        """Test that reserved keywords are invalid topics."""
        assert is_valid_topic("admin") is False
        assert is_valid_topic("home") is False
        assert is_valid_topic("search") is False

    def test_global_is_valid(self):
        """Test that 'global' is NOT a reserved keyword."""
        # This test verifies that "global" is not rejected as a reserved keyword
        # The actual validity depends on whether it exists in the database
        assert "global" not in RESERVED_KEYWORDS
