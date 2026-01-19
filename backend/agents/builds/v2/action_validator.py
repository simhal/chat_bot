"""
Centralized action validation for the v2 agent build.

Uses shared/sections.json and shared/ui_actions.json as source of truth.
Validates that UI actions are allowed in the current context based on:
- Section configuration (what actions are available in each section)
- User role (permission to access the section)
- Global action bypass rules (navigation always allowed)
"""

from typing import Dict, Any, List, Tuple, Optional
import logging

from agents.builds.v2.state import (
    SECTION_CONFIG,
    GLOBAL_ACTION_NAMES,
    get_section_action_names,
    get_section_config,
    UserContext,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Actions that ALWAYS bypass section/role checks (available everywhere)
ALWAYS_ALLOWED_ACTIONS = ["goto", "select_topic", "select_article", "logout"]

# Role hierarchy - higher level = more permissions
ROLE_HIERARCHY = {
    "admin": 4,
    "analyst": 3,
    "editor": 2,
    "reader": 1,
}

# Mapping from section prefix to role
SECTION_PREFIX_TO_ROLE = {
    "reader": "reader",
    "analyst": "analyst",
    "editor": "editor",
    "admin": "admin",
    "root": "admin",
    "user": "user",
    "home": "reader",
}


# =============================================================================
# Action Validation
# =============================================================================

def validate_action(
    action_type: str,
    section: str,
    user_context: Optional[Dict[str, Any]] = None,
    topic: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Validate if an action is allowed in the current context.

    Args:
        action_type: The UI action being requested (e.g., "save_draft", "publish_article")
        section: Current section from nav_context (e.g., "analyst_editor", "reader_topic")
        user_context: User context with scopes and roles
        topic: Current topic (for topic-scoped permission checks)

    Returns:
        Tuple of (allowed: bool, error_message: str)
        If allowed, error_message is empty string.
        If not allowed, error_message contains helpful guidance.

    Examples:
        >>> validate_action("goto", "analyst_editor")
        (True, "")  # goto is always allowed

        >>> validate_action("save_draft", "analyst_editor")
        (True, "")  # save_draft is in analyst_editor's ui_actions

        >>> validate_action("publish_article", "analyst_editor")
        (False, "'publish_article' is available in: editor_dashboard, editor_article. Navigate there first.")
    """
    # Global actions always allowed for authenticated users
    if action_type in ALWAYS_ALLOWED_ACTIONS:
        logger.debug(f"Action '{action_type}' is globally allowed")
        return True, ""

    # Get allowed actions for current section
    allowed_actions = get_section_action_names(section)

    if action_type in allowed_actions:
        logger.debug(f"Action '{action_type}' is allowed in section '{section}'")
        return True, ""

    # Action not available in current section - provide guidance
    available_sections = find_sections_with_action(action_type)

    if available_sections:
        sections_str = ", ".join(available_sections[:5])  # Limit to 5 for readability
        if len(available_sections) > 5:
            sections_str += f" (+{len(available_sections) - 5} more)"
        return False, f"'{action_type}' is available in: {sections_str}. Navigate there first."

    return False, f"Unknown action: '{action_type}'"


def validate_action_for_role(
    action_type: str,
    section: str,
    user_role: str,
    topic: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Validate if an action is allowed for a specific role in the current section.

    This is a convenience wrapper that checks both action availability
    and role permissions.

    Args:
        action_type: The UI action being requested
        section: Current section name
        user_role: User's role for the current context (e.g., "analyst", "reader")
        topic: Current topic (optional)

    Returns:
        Tuple of (allowed: bool, error_message: str)
    """
    # First check if action is allowed in section
    allowed, error = validate_action(action_type, section, topic=topic)

    if not allowed:
        return allowed, error

    # Check if section requires a role the user doesn't have
    section_config = get_section_config(section)
    if section_config:
        required_role = section_config.get("required_role", "any")

        if required_role != "any" and not _has_required_role(user_role, required_role):
            role_name = required_role.split(":")[-1] if ":" in required_role else required_role
            return False, f"This action requires {role_name} access."

    return True, ""


def is_action_allowed_globally(action_type: str) -> bool:
    """Check if an action is in the global always-allowed list."""
    return action_type in ALWAYS_ALLOWED_ACTIONS


def is_navigation_action(action_type: str) -> bool:
    """Check if an action is a navigation action."""
    return action_type == "goto" or action_type.startswith("goto_")


# =============================================================================
# Section & Role Helpers
# =============================================================================

def find_sections_with_action(action_type: str) -> List[str]:
    """
    Find all sections where an action is available.

    Args:
        action_type: The action to search for

    Returns:
        List of section names that have this action
    """
    sections = []
    for section_name, config in SECTION_CONFIG.items():
        if action_type in config.get("ui_actions", []):
            sections.append(section_name)
    return sections


def get_role_from_section(section: str) -> str:
    """
    Extract the implied role from a section name prefix.

    Args:
        section: Section name (e.g., "analyst_editor", "reader_topic")

    Returns:
        Role string (e.g., "analyst", "reader")

    Examples:
        >>> get_role_from_section("analyst_editor")
        "analyst"
        >>> get_role_from_section("reader_topic")
        "reader"
        >>> get_role_from_section("root_users")
        "admin"
        >>> get_role_from_section("home")
        "reader"
    """
    if not section:
        return "reader"

    prefix = section.split("_")[0] if "_" in section else section
    return SECTION_PREFIX_TO_ROLE.get(prefix, "reader")


def get_allowed_actions_for_role(role: str) -> List[str]:
    """
    Get all UI actions available for a role across all their accessible sections.

    This aggregates actions from all sections the role can access,
    including inherited permissions from lower roles.

    Args:
        role: The role to get actions for (admin, analyst, editor, reader)

    Returns:
        List of unique action names
    """
    allowed = set(ALWAYS_ALLOWED_ACTIONS)
    role_level = ROLE_HIERARCHY.get(role, 1)

    for section_name, section_config in SECTION_CONFIG.items():
        required_role = section_config.get("required_role", "any")

        # Check if this role can access this section
        if required_role == "any":
            allowed.update(section_config.get("ui_actions", []))
        elif "{topic}:" in required_role:
            section_role = required_role.split(":")[1]
            section_role_level = ROLE_HIERARCHY.get(section_role, 0)
            if role_level >= section_role_level:
                allowed.update(section_config.get("ui_actions", []))
        elif "global:" in required_role:
            # Only global admin can access global sections
            if role == "admin":
                allowed.update(section_config.get("ui_actions", []))

    # Add global actions
    allowed.update(GLOBAL_ACTION_NAMES)

    return list(allowed)


def _has_required_role(user_role: str, required_role: str) -> bool:
    """
    Check if user has the required role (considering role hierarchy).

    Args:
        user_role: User's role (admin, analyst, editor, reader)
        required_role: Required role string (may include {topic}: prefix)

    Returns:
        True if user's role meets or exceeds requirement
    """
    # Extract role name from format like "{topic}:analyst" or "global:admin"
    if ":" in required_role:
        required_role_name = required_role.split(":")[1]
    else:
        required_role_name = required_role

    user_level = ROLE_HIERARCHY.get(user_role, 1)
    required_level = ROLE_HIERARCHY.get(required_role_name, 1)

    return user_level >= required_level


# =============================================================================
# Content Action Detection (for analyst_editor context)
# =============================================================================

# Keywords for detecting different content actions
HEADLINE_KEYWORDS = [
    "headline", "title", "new headline", "better headline",
    "rephrase the headline", "catchier headline", "change title"
]

KEYWORDS_KEYWORDS = [
    "keyword", "tags", "new keywords", "better keywords",
    "suggest keywords", "seo", "search terms"
]

FULL_REWRITE_KEYWORDS = [
    "rewrite the article", "regenerate content", "start over",
    "write it again", "completely rewrite", "rewrite everything"
]

SECTION_NAMES = [
    "introduction", "intro", "summary", "executive summary",
    "conclusion", "analysis", "findings", "methodology",
    "section", "paragraph", "part", "opening", "closing"
]

EDIT_VERBS = [
    "rewrite", "expand", "shorten", "fix", "improve",
    "edit", "change", "update", "revise", "enhance"
]

REFINEMENT_PHRASES = [
    "more concise", "shorter", "longer", "more detail",
    "more professional", "simpler", "clearer", "formal",
    "informal", "add data", "add examples", "less technical",
    "more technical", "tone", "style", "polish", "tighten"
]

CREATE_KEYWORDS = [
    "write", "generate", "draft", "create", "compose", "produce"
]


def detect_content_action(message: str, intent_details: Optional[Dict[str, Any]] = None) -> str:
    """
    Detect the specific content action from user message.

    Used when user is in analyst_editor section to determine
    which content operation to perform.

    Args:
        message: User's message text
        intent_details: Optional intent classification details that may contain action

    Returns:
        One of: "create", "regenerate_headline", "regenerate_keywords",
                "regenerate_content", "edit_section", "refine_content"

    Examples:
        >>> detect_content_action("give me a better headline")
        "regenerate_headline"
        >>> detect_content_action("rewrite the introduction")
        "edit_section"
        >>> detect_content_action("make it more concise")
        "refine_content"
    """
    details = intent_details or {}
    msg_lower = message.lower()

    # Check for explicit action from intent classification
    explicit_action = details.get("action", "")
    if explicit_action in [
        "regenerate_headline", "regenerate_keywords", "regenerate_content",
        "edit_section", "refine_content", "create"
    ]:
        return explicit_action

    # Headline regeneration
    if any(phrase in msg_lower for phrase in HEADLINE_KEYWORDS):
        return "regenerate_headline"

    # Keywords regeneration
    if any(phrase in msg_lower for phrase in KEYWORDS_KEYWORDS):
        return "regenerate_keywords"

    # Full content rewrite
    if any(phrase in msg_lower for phrase in FULL_REWRITE_KEYWORDS):
        return "regenerate_content"

    # Section-specific editing (requires both section name and edit verb)
    has_section = any(section in msg_lower for section in SECTION_NAMES)
    has_edit_verb = any(verb in msg_lower for verb in EDIT_VERBS)
    if has_section and has_edit_verb:
        return "edit_section"

    # Style/tone refinement
    if any(phrase in msg_lower for phrase in REFINEMENT_PHRASES):
        return "refine_content"

    # New content creation
    if any(phrase in msg_lower for phrase in CREATE_KEYWORDS):
        return "create"

    # Default: if in editor with existing content, assume refinement intent
    # This will be handled by the caller based on context
    return "refine_content"


def is_content_request(message: str) -> bool:
    """
    Check if a message appears to be requesting content operations.

    Used to determine if a message should be routed to the
    content generation sub-graph when in analyst_editor section.

    Args:
        message: User's message text

    Returns:
        True if message appears to be a content request
    """
    msg_lower = message.lower()

    # Check all content-related keyword lists
    all_content_keywords = (
        HEADLINE_KEYWORDS +
        KEYWORDS_KEYWORDS +
        FULL_REWRITE_KEYWORDS +
        REFINEMENT_PHRASES +
        CREATE_KEYWORDS +
        EDIT_VERBS
    )

    return any(kw in msg_lower for kw in all_content_keywords)


def is_resource_request(message: str, intent_details: Optional[Dict[str, Any]] = None) -> bool:
    """
    Check if a message is about resource management.

    Args:
        message: User's message text
        intent_details: Optional intent classification details

    Returns:
        True if message is about resources
    """
    details = intent_details or {}
    action = details.get("action_type", "")

    # Check explicit resource actions
    if action in ["browse_resources", "link_resource", "unlink_resource", "add_resource"]:
        return True

    # Check keywords
    msg_lower = message.lower()
    resource_keywords = [
        "resource", "chart", "image", "attach", "link",
        "add data", "include figure", "reference", "file",
        "document", "pdf", "upload", "graph", "table"
    ]

    return any(kw in msg_lower for kw in resource_keywords)
