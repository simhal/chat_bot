"""
Tests for the v2 agent build router node.

Tests for:
- Role extraction from section
- Navigation intent priority routing
- Role-based routing
- Fallback routing logic
"""
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage

from agents.builds.v2.nodes.router_node import (
    router_node,
    route_by_intent,
    _extract_role_from_section,
    _determine_target_node,
)


# =============================================================================
# ROLE EXTRACTION TESTS
# =============================================================================

class TestRoleExtraction:
    """Test role extraction from section names."""

    def test_reader_sections(self):
        """Test role extraction from reader sections."""
        assert _extract_role_from_section("reader_topic") == "reader"
        assert _extract_role_from_section("reader_search") == "reader"

    def test_analyst_sections(self):
        """Test role extraction from analyst sections."""
        assert _extract_role_from_section("analyst_dashboard") == "analyst"
        assert _extract_role_from_section("analyst_editor") == "analyst"

    def test_editor_sections(self):
        """Test role extraction from editor sections."""
        assert _extract_role_from_section("editor_dashboard") == "editor"

    def test_admin_sections(self):
        """Test role extraction from admin sections."""
        assert _extract_role_from_section("admin_articles") == "admin"
        assert _extract_role_from_section("admin_resources") == "admin"

    def test_root_sections_map_to_admin(self):
        """Test that root sections map to admin."""
        assert _extract_role_from_section("root_users") == "admin"
        assert _extract_role_from_section("root_topics") == "admin"

    def test_user_sections(self):
        """Test role extraction from user sections."""
        assert _extract_role_from_section("user_profile") == "user"
        assert _extract_role_from_section("user_settings") == "user"

    def test_home_defaults_to_reader(self):
        """Test that home section defaults to reader."""
        assert _extract_role_from_section("home") == "reader"


# =============================================================================
# NAVIGATION PRIORITY TESTS
# =============================================================================

class TestNavigationPriority:
    """Test that navigation intent has highest priority."""

    def test_navigation_always_routes_to_navigation_node(self):
        """Test that navigation intent routes to navigation node regardless of role."""
        roles = ["reader", "analyst", "editor", "admin"]
        for role in roles:
            target = _determine_target_node("navigation", role, {})
            assert target == "navigation", f"Navigation from {role} should go to navigation node"

    def test_navigation_from_analyst_editor_goes_to_navigation(self):
        """Test that navigation from analyst_editor routes to navigation."""
        # This is the critical case: user in editor says "go home"
        target = _determine_target_node("navigation", "analyst", {})
        assert target == "navigation"


# =============================================================================
# TARGET NODE DETERMINATION TESTS
# =============================================================================

class TestTargetNodeDetermination:
    """Test target node determination logic."""

    def test_entitlements_routes_to_user(self):
        """Test that entitlements intent routes to user node."""
        target = _determine_target_node("entitlements", "reader", {})
        assert target == "user"

    def test_user_role_routes_to_user(self):
        """Test that user role context routes to user node."""
        target = _determine_target_node("general_chat", "user", {})
        assert target == "user"

    def test_profile_role_routes_to_user(self):
        """Test that profile role context routes to user node."""
        target = _determine_target_node("general_chat", "profile", {})
        assert target == "user"

    def test_reader_role_routes_to_reader(self):
        """Test that reader role routes to reader node."""
        target = _determine_target_node("general_chat", "reader", {})
        assert target == "reader"

    def test_analyst_role_routes_to_analyst(self):
        """Test that analyst role routes to analyst node."""
        target = _determine_target_node("general_chat", "analyst", {})
        assert target == "analyst"

    def test_editor_role_routes_to_editor(self):
        """Test that editor role routes to editor node."""
        target = _determine_target_node("general_chat", "editor", {})
        assert target == "editor"

    def test_admin_role_routes_to_admin(self):
        """Test that admin role routes to admin node."""
        target = _determine_target_node("general_chat", "admin", {})
        assert target == "admin"

    def test_unknown_role_fallback_to_general_chat(self):
        """Test that unknown role falls back to general_chat."""
        target = _determine_target_node("general_chat", "unknown_role", {})
        assert target == "general_chat"


# =============================================================================
# INTENT-BASED FALLBACK TESTS
# =============================================================================

class TestIntentBasedFallback:
    """Test intent-based fallback routing."""

    def test_ui_action_defaults_to_reader(self):
        """Test that ui_action intent defaults to reader."""
        target = _determine_target_node("ui_action", "unknown", {})
        assert target == "reader"

    def test_content_generation_defaults_to_analyst(self):
        """Test that content_generation intent defaults to analyst."""
        target = _determine_target_node("content_generation", "unknown", {})
        assert target == "analyst"

    def test_editor_workflow_defaults_to_editor(self):
        """Test that editor_workflow intent defaults to editor."""
        target = _determine_target_node("editor_workflow", "unknown", {})
        assert target == "editor"

    def test_general_chat_defaults_to_general_chat(self):
        """Test that general_chat intent defaults to general_chat."""
        target = _determine_target_node("general_chat", "unknown", {})
        assert target == "general_chat"


# =============================================================================
# ROUTER NODE FUNCTION TESTS
# =============================================================================

class TestRouterNode:
    """Test the main router_node function."""

    @patch("agents.builds.v2.nodes.router_node.classify_intent")
    def test_router_with_no_messages_returns_general_chat(self, mock_classify):
        """Test router returns general_chat when no messages."""
        state = {"messages": []}
        result = router_node(state)

        assert result["selected_agent"] == "general_chat"
        assert "No messages" in result["routing_reason"]

    @patch("agents.builds.v2.nodes.router_node.classify_intent")
    def test_router_extracts_message_content(self, mock_classify):
        """Test router extracts message content correctly."""
        mock_classify.return_value = {
            "intent_type": "general_chat",
            "confidence": 0.9,
            "details": {}
        }

        message = HumanMessage(content="Hello world")
        state = {
            "messages": [message],
            "navigation_context": {"section": "home"},
            "user_context": {"scopes": []}
        }

        result = router_node(state)
        mock_classify.assert_called_once()
        call_args = mock_classify.call_args
        assert call_args[1]["message"] == "Hello world"

    @patch("agents.builds.v2.nodes.router_node.classify_intent")
    def test_router_uses_navigation_context(self, mock_classify):
        """Test router uses navigation context for routing."""
        mock_classify.return_value = {
            "intent_type": "general_chat",
            "confidence": 0.9,
            "details": {}
        }

        message = HumanMessage(content="Help me")
        state = {
            "messages": [message],
            "navigation_context": {"section": "analyst_editor"},
            "user_context": {"scopes": ["macro:analyst"]}
        }

        result = router_node(state)

        # Should route to analyst because section is analyst_editor
        assert result["selected_agent"] == "analyst"
        assert "analyst" in result["routing_reason"].lower()

    @patch("agents.builds.v2.nodes.router_node.classify_intent")
    def test_router_prioritizes_navigation_intent(self, mock_classify):
        """Test router prioritizes navigation over section-based routing."""
        mock_classify.return_value = {
            "intent_type": "navigation",
            "confidence": 0.95,
            "details": {"action_type": "goto_home"}
        }

        message = HumanMessage(content="go home")
        state = {
            "messages": [message],
            "navigation_context": {"section": "analyst_editor"},  # Deep in analyst
            "user_context": {"scopes": ["macro:analyst"]}
        }

        result = router_node(state)

        # Should route to navigation despite being in analyst section
        assert result["selected_agent"] == "navigation"


# =============================================================================
# ROUTE BY INTENT TESTS
# =============================================================================

class TestRouteByIntent:
    """Test the route_by_intent conditional edge function."""

    def test_route_uses_selected_agent(self):
        """Test that route uses selected_agent from state."""
        state = {"selected_agent": "analyst"}
        result = route_by_intent(state)
        assert result == "analyst"

    def test_route_falls_back_on_missing_agent(self):
        """Test fallback when selected_agent is missing."""
        state = {
            "intent": {"intent_type": "general_chat"},
            "navigation_context": {"section": "home"}
        }
        result = route_by_intent(state)
        assert result in ["reader", "general_chat"]

    def test_route_validates_node_names(self):
        """Test that invalid node names default to general_chat."""
        state = {"selected_agent": "invalid_node_name"}
        result = route_by_intent(state)
        assert result == "general_chat"

    def test_route_accepts_valid_nodes(self):
        """Test that valid node names are accepted."""
        valid_nodes = ["navigation", "user", "reader", "analyst", "editor", "admin", "general_chat"]
        for node in valid_nodes:
            state = {"selected_agent": node}
            result = route_by_intent(state)
            assert result == node
