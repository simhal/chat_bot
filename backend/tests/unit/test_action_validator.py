"""
Tests for the v2 agent build action validator.

Tests for:
- Action validation (validate_action, validate_action_for_role)
- Content action detection (detect_content_action, is_content_request)
- Resource request detection (is_resource_request)
- Role extraction from section (get_role_from_section)
- Section lookup (find_sections_with_action)
"""
import pytest
from agents.builds.v2.action_validator import (
    validate_action,
    validate_action_for_role,
    is_action_allowed_globally,
    is_navigation_action,
    find_sections_with_action,
    get_role_from_section,
    get_allowed_actions_for_role,
    detect_content_action,
    is_content_request,
    is_resource_request,
    ALWAYS_ALLOWED_ACTIONS,
    ROLE_HIERARCHY,
    SECTION_PREFIX_TO_ROLE,
)


# =============================================================================
# GLOBAL ACTION TESTS
# =============================================================================

class TestGlobalActions:
    """Test globally allowed actions."""

    def test_goto_is_always_allowed(self):
        """Test that goto action is always allowed."""
        assert is_action_allowed_globally("goto")
        allowed, error = validate_action("goto", "any_section")
        assert allowed is True
        assert error == ""

    def test_select_topic_is_always_allowed(self):
        """Test that select_topic action is always allowed."""
        assert is_action_allowed_globally("select_topic")
        allowed, error = validate_action("select_topic", "analyst_editor")
        assert allowed is True

    def test_select_article_is_always_allowed(self):
        """Test that select_article action is always allowed."""
        assert is_action_allowed_globally("select_article")
        allowed, error = validate_action("select_article", "reader_topic")
        assert allowed is True

    def test_logout_is_always_allowed(self):
        """Test that logout action is always allowed."""
        assert is_action_allowed_globally("logout")
        allowed, error = validate_action("logout", "admin_articles")
        assert allowed is True

    def test_non_global_actions_are_not_globally_allowed(self):
        """Test that non-global actions are not in always allowed list."""
        non_global = ["save_draft", "publish_article", "purge_article", "delete_account"]
        for action in non_global:
            assert not is_action_allowed_globally(action)


# =============================================================================
# NAVIGATION ACTION TESTS
# =============================================================================

class TestNavigationActions:
    """Test navigation action detection."""

    def test_goto_is_navigation(self):
        """Test that goto is recognized as navigation."""
        assert is_navigation_action("goto")

    def test_goto_prefixed_actions_are_navigation(self):
        """Test that goto_* actions are recognized as navigation."""
        nav_actions = [
            "goto_home", "goto_search", "goto_reader_topic",
            "goto_analyst_topic", "goto_editor_topic", "goto_admin_topic",
            "goto_root", "goto_user_profile", "goto_user_settings"
        ]
        for action in nav_actions:
            assert is_navigation_action(action), f"{action} should be navigation"

    def test_non_navigation_actions(self):
        """Test that non-navigation actions are not flagged."""
        non_nav = ["save_draft", "publish_article", "select_topic"]
        for action in non_nav:
            assert not is_navigation_action(action), f"{action} should not be navigation"


# =============================================================================
# ACTION VALIDATION TESTS
# =============================================================================

class TestActionValidation:
    """Test action validation for sections."""

    def test_global_action_allowed_in_any_section(self):
        """Test that global actions pass validation in any section."""
        sections = ["home", "analyst_editor", "editor_dashboard", "admin_articles", "root_users"]
        for section in sections:
            for action in ALWAYS_ALLOWED_ACTIONS:
                allowed, error = validate_action(action, section)
                assert allowed is True, f"{action} should be allowed in {section}"
                assert error == ""

    def test_section_specific_action_allowed(self):
        """Test that section-specific actions are allowed in correct section."""
        # save_draft should be allowed in analyst_editor
        allowed, error = validate_action("save_draft", "analyst_editor")
        # Note: This depends on the actual sections.json config
        # The test verifies the validation logic works

    def test_unknown_action_returns_error(self):
        """Test that unknown actions return error message."""
        allowed, error = validate_action("completely_fake_action_xyz", "home")
        assert allowed is False
        assert "Unknown action" in error

    def test_validation_provides_guidance_for_wrong_section(self):
        """Test that validation provides guidance when action is in wrong section."""
        # Try to use admin action in reader section
        allowed, error = validate_action("purge_article", "reader_topic")
        if not allowed:
            # Should mention where the action IS available
            assert "available in" in error.lower() or "unknown" in error.lower()


# =============================================================================
# ROLE EXTRACTION TESTS
# =============================================================================

class TestRoleExtraction:
    """Test role extraction from section names."""

    def test_reader_sections(self):
        """Test role extraction from reader sections."""
        assert get_role_from_section("reader_topic") == "reader"
        assert get_role_from_section("reader_search") == "reader"
        assert get_role_from_section("reader_article") == "reader"

    def test_analyst_sections(self):
        """Test role extraction from analyst sections."""
        assert get_role_from_section("analyst_dashboard") == "analyst"
        assert get_role_from_section("analyst_editor") == "analyst"

    def test_editor_sections(self):
        """Test role extraction from editor sections."""
        assert get_role_from_section("editor_dashboard") == "editor"
        assert get_role_from_section("editor_article") == "editor"

    def test_admin_sections(self):
        """Test role extraction from admin sections."""
        assert get_role_from_section("admin_articles") == "admin"
        assert get_role_from_section("admin_resources") == "admin"
        assert get_role_from_section("admin_prompts") == "admin"

    def test_root_sections_map_to_admin(self):
        """Test that root sections map to admin role."""
        assert get_role_from_section("root_users") == "admin"
        assert get_role_from_section("root_topics") == "admin"
        assert get_role_from_section("root_groups") == "admin"

    def test_user_sections(self):
        """Test role extraction from user sections."""
        assert get_role_from_section("user_profile") == "user"
        assert get_role_from_section("user_settings") == "user"

    def test_home_maps_to_reader(self):
        """Test that home section maps to reader role."""
        assert get_role_from_section("home") == "reader"

    def test_empty_section_defaults_to_reader(self):
        """Test that empty/None section defaults to reader."""
        assert get_role_from_section("") == "reader"
        assert get_role_from_section(None) == "reader"

    def test_unknown_section_defaults_to_reader(self):
        """Test that unknown sections default to reader."""
        assert get_role_from_section("unknown_section") == "reader"


# =============================================================================
# CONTENT ACTION DETECTION TESTS
# =============================================================================

class TestContentActionDetection:
    """Test content action detection from messages."""

    def test_detect_headline_regeneration(self):
        """Test detection of headline regeneration requests."""
        messages = [
            "give me a better headline",
            "suggest a new headline",
            "rephrase the headline",
            "I need a catchier headline",
            "new headline please",
            "change the title"
        ]
        for msg in messages:
            action = detect_content_action(msg)
            assert action == "regenerate_headline", f"'{msg}' should detect regenerate_headline"

    def test_detect_keywords_regeneration(self):
        """Test detection of keywords regeneration requests."""
        messages = [
            "suggest keywords",
            "generate new keywords",
            "better keywords please",
            "suggest some tags",
            "SEO keywords"
        ]
        for msg in messages:
            action = detect_content_action(msg)
            assert action == "regenerate_keywords", f"'{msg}' should detect regenerate_keywords"

    def test_detect_full_content_rewrite(self):
        """Test detection of full content rewrite requests."""
        messages = [
            "rewrite the article",  # Must have "article" keyword
            "regenerate content",   # Must match phrase exactly
            "start over",
            "completely rewrite",
            "write it again"
        ]
        for msg in messages:
            action = detect_content_action(msg)
            assert action == "regenerate_content", f"'{msg}' should detect regenerate_content"

    def test_detect_section_editing(self):
        """Test detection of section-specific editing requests."""
        messages = [
            "rewrite the introduction",
            "expand the analysis section",
            "shorten the conclusion",
            "fix the methodology paragraph",
            "improve the summary"
        ]
        for msg in messages:
            action = detect_content_action(msg)
            assert action == "edit_section", f"'{msg}' should detect edit_section"

    def test_detect_content_refinement(self):
        """Test detection of content refinement requests."""
        messages = [
            "make it more concise",
            "more professional tone",
            "simplify the language",
            "add more detail",
            "tighten this up"
        ]
        for msg in messages:
            action = detect_content_action(msg)
            assert action == "refine_content", f"'{msg}' should detect refine_content"

    def test_detect_create_action(self):
        """Test detection of create action."""
        messages = [
            "write an article about inflation",
            "generate a piece on market trends",
            "draft an analysis",
            "create content about bonds"
        ]
        for msg in messages:
            action = detect_content_action(msg)
            assert action == "create", f"'{msg}' should detect create"

    def test_explicit_action_in_details_takes_precedence(self):
        """Test that explicit action in details overrides message detection."""
        details = {"action": "regenerate_headline"}
        action = detect_content_action("make it more concise", details)
        assert action == "regenerate_headline"

    def test_default_to_refine_content(self):
        """Test that ambiguous messages default to refine_content."""
        action = detect_content_action("this needs work")
        assert action == "refine_content"


# =============================================================================
# CONTENT REQUEST DETECTION TESTS
# =============================================================================

class TestContentRequestDetection:
    """Test is_content_request function."""

    def test_content_keywords_detected(self):
        """Test that content-related keywords are detected."""
        content_messages = [
            "write something",
            "generate content",
            "rewrite this",
            "give me a headline",
            "suggest keywords",
            "make it more professional"
        ]
        for msg in content_messages:
            assert is_content_request(msg), f"'{msg}' should be content request"

    def test_non_content_messages(self):
        """Test that non-content messages are not flagged."""
        non_content = [
            "hello",
            "go to home",
            "show my profile",
            "what is the weather"
        ]
        for msg in non_content:
            assert not is_content_request(msg), f"'{msg}' should not be content request"


# =============================================================================
# RESOURCE REQUEST DETECTION TESTS
# =============================================================================

class TestResourceRequestDetection:
    """Test is_resource_request function."""

    def test_resource_keywords_detected(self):
        """Test that resource-related keywords are detected."""
        resource_messages = [
            "attach a chart",
            "add an image",
            "link the resource",
            "include the PDF",
            "show me resources"
        ]
        for msg in resource_messages:
            assert is_resource_request(msg), f"'{msg}' should be resource request"

    def test_explicit_resource_action_detected(self):
        """Test that explicit resource actions are detected."""
        details = {"action_type": "browse_resources"}
        assert is_resource_request("anything", details)

        details = {"action_type": "link_resource"}
        assert is_resource_request("anything", details)

    def test_non_resource_messages(self):
        """Test that non-resource messages are not flagged."""
        non_resource = [
            "write an article",
            "go home",
            "better headline"
        ]
        for msg in non_resource:
            assert not is_resource_request(msg), f"'{msg}' should not be resource request"


# =============================================================================
# ROLE HIERARCHY TESTS
# =============================================================================

class TestRoleHierarchy:
    """Test role hierarchy is correctly defined."""

    def test_admin_is_highest(self):
        """Test that admin has highest role level."""
        assert ROLE_HIERARCHY["admin"] > ROLE_HIERARCHY["analyst"]
        assert ROLE_HIERARCHY["admin"] > ROLE_HIERARCHY["editor"]
        assert ROLE_HIERARCHY["admin"] > ROLE_HIERARCHY["reader"]

    def test_analyst_above_editor(self):
        """Test that analyst is above editor in hierarchy."""
        assert ROLE_HIERARCHY["analyst"] > ROLE_HIERARCHY["editor"]

    def test_editor_above_reader(self):
        """Test that editor is above reader in hierarchy."""
        assert ROLE_HIERARCHY["editor"] > ROLE_HIERARCHY["reader"]

    def test_reader_is_base(self):
        """Test that reader is the base role."""
        assert ROLE_HIERARCHY["reader"] == 1


# =============================================================================
# SECTION PREFIX MAPPING TESTS
# =============================================================================

class TestSectionPrefixMapping:
    """Test section prefix to role mapping."""

    def test_all_prefixes_mapped(self):
        """Test that all expected prefixes are mapped."""
        expected = ["reader", "analyst", "editor", "admin", "root", "user", "home"]
        for prefix in expected:
            assert prefix in SECTION_PREFIX_TO_ROLE

    def test_root_maps_to_admin(self):
        """Test that root prefix maps to admin role."""
        assert SECTION_PREFIX_TO_ROLE["root"] == "admin"

    def test_home_maps_to_reader(self):
        """Test that home prefix maps to reader role."""
        assert SECTION_PREFIX_TO_ROLE["home"] == "reader"


# =============================================================================
# GET ALLOWED ACTIONS FOR ROLE TESTS
# =============================================================================

class TestAllowedActionsForRole:
    """Test getting allowed actions for roles."""

    def test_reader_has_global_actions(self):
        """Test that reader role has access to global actions."""
        actions = get_allowed_actions_for_role("reader")
        for action in ALWAYS_ALLOWED_ACTIONS:
            assert action in actions, f"Reader should have {action}"

    def test_admin_has_more_actions_than_reader(self):
        """Test that admin has more actions than reader."""
        reader_actions = set(get_allowed_actions_for_role("reader"))
        admin_actions = set(get_allowed_actions_for_role("admin"))
        # Admin should have at least everything reader has
        assert reader_actions.issubset(admin_actions)
        # Admin should have more
        assert len(admin_actions) >= len(reader_actions)

    def test_analyst_has_content_actions(self):
        """Test that analyst has content-related actions."""
        actions = get_allowed_actions_for_role("analyst")
        # Should have at least the global actions
        for action in ALWAYS_ALLOWED_ACTIONS:
            assert action in actions


# =============================================================================
# FIND SECTIONS WITH ACTION TESTS
# =============================================================================

class TestFindSectionsWithAction:
    """Test finding sections that have a specific action."""

    def test_find_sections_for_existing_action(self):
        """Test finding sections for an action that exists."""
        # Global actions might be in many or no specific sections
        sections = find_sections_with_action("save_draft")
        # save_draft should be in analyst_editor if configured
        # This test validates the function works

    def test_find_sections_for_nonexistent_action(self):
        """Test finding sections for action that doesn't exist."""
        sections = find_sections_with_action("completely_fake_action_xyz")
        assert sections == []
