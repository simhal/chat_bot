"""
Tests for the v2 agent build navigation node.

Tests for:
- Navigation permission checking (TARGET-based, not current section)
- Navigation response building
- Parameter extraction
- Action type inference from messages

CRITICAL DESIGN PRINCIPLE:
Permission check is on the TARGET section, NOT the current section.
Users can ALWAYS try to navigate via chat from ANY page.
"""
import pytest
from langchain_core.messages import HumanMessage

from agents.builds.v2.nodes.navigation_node import (
    navigation_node,
    _infer_navigation_from_message,
    _check_navigation_permission,
    _extract_navigation_params,
    _build_navigation_response,
    NAVIGATION_PERMISSIONS,
)


# =============================================================================
# NAVIGATION PERMISSIONS CONFIGURATION TESTS
# =============================================================================

class TestNavigationPermissionsConfig:
    """Test navigation permissions configuration."""

    def test_home_accessible_by_all_roles(self):
        """Test that home is accessible by all roles."""
        config = NAVIGATION_PERMISSIONS.get("goto_home")
        assert config is not None
        assert "reader" in config["roles"]
        assert "analyst" in config["roles"]
        assert "editor" in config["roles"]
        assert "admin" in config["roles"]

    def test_analyst_requires_analyst_role(self):
        """Test that analyst navigation requires analyst role."""
        config = NAVIGATION_PERMISSIONS.get("goto_analyst_topic")
        assert config is not None
        assert "analyst" in config["roles"]
        assert config.get("any_topic") is True

    def test_editor_requires_editor_role(self):
        """Test that editor navigation requires editor role."""
        config = NAVIGATION_PERMISSIONS.get("goto_editor_topic")
        assert config is not None
        assert "editor" in config["roles"]
        assert config.get("any_topic") is True

    def test_admin_requires_admin_role(self):
        """Test that admin navigation requires admin role."""
        config = NAVIGATION_PERMISSIONS.get("goto_admin_topic")
        assert config is not None
        assert "admin" in config["roles"]
        assert config.get("any_topic") is True

    def test_root_requires_global_admin(self):
        """Test that root navigation requires global admin."""
        config = NAVIGATION_PERMISSIONS.get("goto_root")
        assert config is not None
        assert config.get("global_only") is True


# =============================================================================
# PERMISSION CHECKING TESTS - THE CRITICAL TESTS
# =============================================================================

class TestNavigationPermissionChecking:
    """Test navigation permission checking - these are the critical security tests."""

    def test_global_admin_can_access_everything(self):
        """Test that global admin can access all navigation targets."""
        user_context = {
            "topic_roles": {},
            "scopes": ["global:admin"]
        }

        targets = [
            "goto_home", "goto_search", "goto_reader_topic",
            "goto_analyst_topic", "goto_editor_topic", "goto_admin_topic",
            "goto_root", "goto_user_profile", "goto_user_settings"
        ]

        for target in targets:
            result = _check_navigation_permission(target, user_context)
            assert result["allowed"] is True, f"Global admin should access {target}"

    def test_reader_can_access_reader_pages(self):
        """Test that reader can access reader-level pages."""
        user_context = {
            "topic_roles": {"macro": "reader"},
            "scopes": ["macro:reader"]
        }

        allowed_targets = ["goto_home", "goto_search", "goto_reader_topic", "goto_user_profile"]
        for target in allowed_targets:
            result = _check_navigation_permission(target, user_context)
            assert result["allowed"] is True, f"Reader should access {target}"

    def test_reader_cannot_access_analyst_pages(self):
        """Test that reader cannot access analyst pages."""
        user_context = {
            "topic_roles": {"macro": "reader"},
            "scopes": ["macro:reader"]
        }

        result = _check_navigation_permission("goto_analyst_topic", user_context)
        assert result["allowed"] is False
        assert "analyst" in result["message"].lower()

    def test_reader_cannot_access_editor_pages(self):
        """Test that reader cannot access editor pages."""
        user_context = {
            "topic_roles": {"macro": "reader"},
            "scopes": ["macro:reader"]
        }

        result = _check_navigation_permission("goto_editor_topic", user_context)
        assert result["allowed"] is False
        assert "editor" in result["message"].lower()

    def test_reader_cannot_access_admin_pages(self):
        """Test that reader cannot access admin pages."""
        user_context = {
            "topic_roles": {"macro": "reader"},
            "scopes": ["macro:reader"]
        }

        result = _check_navigation_permission("goto_admin_topic", user_context)
        assert result["allowed"] is False

    def test_reader_cannot_access_root_pages(self):
        """Test that reader cannot access root admin pages."""
        user_context = {
            "topic_roles": {"macro": "reader"},
            "scopes": ["macro:reader"]
        }

        result = _check_navigation_permission("goto_root", user_context)
        assert result["allowed"] is False
        assert "global admin" in result["message"].lower()

    def test_analyst_can_access_analyst_pages(self):
        """Test that analyst can access analyst pages."""
        user_context = {
            "topic_roles": {"macro": "analyst"},
            "scopes": ["macro:analyst"]
        }

        result = _check_navigation_permission("goto_analyst_topic", user_context)
        assert result["allowed"] is True

    def test_topic_admin_cannot_access_root(self):
        """Test that topic admin cannot access root admin pages."""
        user_context = {
            "topic_roles": {"macro": "admin"},
            "scopes": ["macro:admin"]  # No global:admin
        }

        result = _check_navigation_permission("goto_root", user_context)
        assert result["allowed"] is False
        assert "global admin" in result["message"].lower()

    def test_topic_specific_permission_check(self):
        """Test permission check for specific topic."""
        user_context = {
            "topic_roles": {"macro": "analyst"},  # Only analyst on macro
            "scopes": ["macro:analyst"]
        }

        # Can access analyst on macro
        result = _check_navigation_permission("goto_analyst_topic", user_context, "macro")
        assert result["allowed"] is True

        # Cannot access analyst on equity (no permission)
        result = _check_navigation_permission("goto_analyst_topic", user_context, "equity")
        assert result["allowed"] is False


# =============================================================================
# MESSAGE INFERENCE TESTS
# =============================================================================

class TestNavigationInference:
    """Test navigation action inference from messages."""

    def test_infer_home_navigation(self):
        """Test inferring home navigation."""
        user_context = {"topic_roles": {}, "scopes": []}
        messages = ["go home", "take me home", "main page", "landing page"]
        for msg in messages:
            action = _infer_navigation_from_message(msg, user_context)
            assert action == "goto_home", f"'{msg}' should infer goto_home"

    def test_infer_search_navigation(self):
        """Test inferring search navigation."""
        user_context = {"topic_roles": {}, "scopes": []}
        messages = ["go to search", "find articles", "search for"]
        for msg in messages:
            action = _infer_navigation_from_message(msg, user_context)
            assert action == "goto_search", f"'{msg}' should infer goto_search"

    def test_infer_profile_navigation(self):
        """Test inferring profile navigation."""
        user_context = {"topic_roles": {}, "scopes": []}
        messages = ["my profile", "show profile", "account"]
        for msg in messages:
            action = _infer_navigation_from_message(msg, user_context)
            assert action == "goto_user_profile", f"'{msg}' should infer goto_user_profile"

    def test_infer_settings_navigation(self):
        """Test inferring settings navigation."""
        user_context = {"topic_roles": {}, "scopes": []}
        messages = ["go to settings", "preferences", "my settings"]
        for msg in messages:
            action = _infer_navigation_from_message(msg, user_context)
            assert action == "goto_user_settings", f"'{msg}' should infer goto_user_settings"

    def test_infer_analyst_navigation_with_role(self):
        """Test inferring analyst navigation when user has analyst role."""
        user_context = {
            "topic_roles": {"macro": "analyst"},
            "scopes": ["macro:analyst"]
        }
        messages = ["go to analyst", "my articles", "write articles"]
        for msg in messages:
            action = _infer_navigation_from_message(msg, user_context)
            assert action == "goto_analyst_topic", f"'{msg}' should infer goto_analyst_topic"

    def test_infer_admin_navigation_with_role(self):
        """Test inferring admin navigation when user has admin role."""
        user_context = {
            "topic_roles": {"macro": "admin"},
            "scopes": ["macro:admin"]
        }
        action = _infer_navigation_from_message("go to admin", user_context)
        assert action == "goto_admin_topic"

    def test_infer_global_admin_navigation(self):
        """Test inferring global admin navigation when user has global admin."""
        user_context = {
            "topic_roles": {},
            "scopes": ["global:admin"]
        }
        messages = ["global admin", "system admin", "root admin"]
        for msg in messages:
            action = _infer_navigation_from_message(msg, user_context)
            assert action == "goto_root", f"'{msg}' should infer goto_root"


# =============================================================================
# PARAMETER EXTRACTION TESTS
# =============================================================================

class TestParameterExtraction:
    """Test navigation parameter extraction."""

    def test_extract_section_always_included(self):
        """Test that section is always included in params."""
        params = _extract_navigation_params("goto_home", "home", {}, {})
        assert "section" in params
        assert params["section"] == "home"

    def test_extract_topic_from_intent_details(self):
        """Test topic extraction from intent details."""
        intent_details = {"topic": "macro"}
        params = _extract_navigation_params("goto_reader_topic", "reader_topic", {}, intent_details)
        assert params.get("topic") == "macro"

    def test_extract_topic_from_nav_context_fallback(self):
        """Test topic extraction falls back to nav_context."""
        nav_context = {"topic": "equity"}
        params = _extract_navigation_params("goto_analyst_topic", "analyst_dashboard", nav_context, {})
        assert params.get("topic") == "equity"

    def test_no_topic_for_home_from_nav_context(self):
        """Test that goto_home doesn't include topic from nav_context."""
        nav_context = {"topic": "macro"}
        params = _extract_navigation_params("goto_home", "home", nav_context, {})
        # Should NOT include topic from nav_context for home
        assert params.get("topic") is None

    def test_extract_article_id(self):
        """Test article_id extraction."""
        intent_details = {"article_id": 123}
        params = _extract_navigation_params("goto_analyst_editor", "analyst_editor", {}, intent_details)
        assert params.get("article_id") == 123


# =============================================================================
# RESPONSE BUILDING TESTS
# =============================================================================

class TestResponseBuilding:
    """Test navigation response message building."""

    def test_home_response(self):
        """Test home navigation response."""
        response = _build_navigation_response("goto_home", {"section": "home"})
        assert "home" in response.lower()

    def test_response_includes_topic(self):
        """Test that response includes topic when present."""
        response = _build_navigation_response(
            "goto_reader_topic",
            {"section": "reader_topic", "topic": "macro"}
        )
        assert "macro" in response.lower()

    def test_search_response(self):
        """Test search navigation response."""
        response = _build_navigation_response("goto_search", {"section": "reader_search"})
        assert "search" in response.lower()

    def test_profile_response(self):
        """Test profile navigation response."""
        response = _build_navigation_response("goto_user_profile", {"section": "user_profile"})
        assert "profile" in response.lower()


# =============================================================================
# NAVIGATION NODE INTEGRATION TESTS
# =============================================================================

class TestNavigationNodeIntegration:
    """Integration tests for the navigation_node function."""

    def test_navigation_node_successful_navigation(self):
        """Test successful navigation returns correct structure."""
        state = {
            "intent": {
                "intent_type": "navigation",
                "details": {"action_type": "goto_home"}
            },
            "user_context": {
                "topic_roles": {"macro": "reader"},
                "scopes": ["macro:reader"]
            },
            "navigation_context": {"section": "analyst_editor"},  # Current section
            "messages": [HumanMessage(content="go home")]
        }

        result = navigation_node(state)

        assert result["is_final"] is True
        assert result["selected_agent"] == "navigation"
        assert "ui_action" in result
        assert result["ui_action"]["type"] == "goto"
        assert result["ui_action"]["params"]["section"] == "home"

    def test_navigation_node_permission_denied(self):
        """Test navigation returns error when permission denied."""
        state = {
            "intent": {
                "intent_type": "navigation",
                "details": {"action_type": "goto_root"}
            },
            "user_context": {
                "topic_roles": {"macro": "reader"},
                "scopes": ["macro:reader"]  # Not global admin
            },
            "navigation_context": {"section": "home"},
            "messages": [HumanMessage(content="go to global admin")]
        }

        result = navigation_node(state)

        assert result["is_final"] is True
        assert "ui_action" not in result  # No action when denied
        assert "global admin" in result["response_text"].lower()

    def test_navigation_from_deep_page_works(self):
        """Test that navigation from deep page (analyst_editor) works."""
        state = {
            "intent": {
                "intent_type": "navigation",
                "details": {"action_type": "goto_home"}
            },
            "user_context": {
                "topic_roles": {"macro": "analyst"},
                "scopes": ["macro:analyst"]
            },
            "navigation_context": {
                "section": "analyst_editor",  # Deep in analyst
                "topic": "macro",
                "article_id": 123
            },
            "messages": [HumanMessage(content="go home")]
        }

        result = navigation_node(state)

        # Should still work - permission is on TARGET (home), not current (analyst_editor)
        assert result["is_final"] is True
        assert "ui_action" in result
        assert result["ui_action"]["type"] == "goto"
        assert result["ui_action"]["params"]["section"] == "home"
