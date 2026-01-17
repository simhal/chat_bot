"""
Navigation node for the main chat graph.

This node handles navigation intents - requests to navigate to different
sections/pages in the application. It uses the unified 'goto' action with
a section parameter matching shared/sections.json.

KEY DESIGN PRINCIPLE:
- Users can ALWAYS try to navigate via chat from ANY page
- Permission check is on the TARGET section, NOT the current section
- This allows users to say "go home" from analyst_editor and it works

The frontend expects:
  ui_action: { type: "goto", params: { section: "section_name", topic?: string, article_id?: number } }
"""

from typing import Dict, Any, Optional
import logging

from agents.builds.v2.state import AgentState, SECTION_CONFIG

logger = logging.getLogger(__name__)


# Internal navigation types and their permission requirements
# "roles" = list of roles that can perform the action (user must have at least one)
# "any_topic" = requires the role on ANY topic (for navigation)
# "global_only" = requires global:admin scope
# "section" = target section name from shared/sections.json
# "special" = special handling required (e.g., goto_back)
NAVIGATION_PERMISSIONS = {
    "goto_back": {
        "roles": ["reader", "analyst", "editor", "admin"],
        "special": "back"  # Frontend handles navigation history
    },
    "goto_home": {
        "roles": ["reader", "analyst", "editor", "admin"],
        "section": "home"
    },
    "goto_search": {
        "roles": ["reader", "analyst", "editor", "admin"],
        "section": "reader_search"
    },
    "goto_reader_topic": {
        "roles": ["reader", "analyst", "editor", "admin"],
        "any_topic": True,
        "section": "reader_topic"
    },
    "goto_analyst_topic": {
        "roles": ["analyst"],
        "any_topic": True,
        "section": "analyst_dashboard"
    },
    "goto_editor_topic": {
        "roles": ["editor"],
        "any_topic": True,
        "section": "editor_dashboard"
    },
    "goto_admin_topic": {
        "roles": ["admin"],
        "any_topic": True,
        "section": "admin_articles"
    },
    "goto_root": {
        "roles": ["admin"],
        "global_only": True,
        "section": "root_users"
    },
    "goto_user_profile": {
        "roles": ["reader", "analyst", "editor", "admin"],
        "section": "user_profile"
    },
    "goto_user_settings": {
        "roles": ["reader", "analyst", "editor", "admin"],
        "section": "user_settings"
    },
}


def navigation_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle navigation intent by validating permissions and building navigation response.

    This node:
    1. Extracts the requested navigation action from intent
    2. Checks if user has permission for the navigation
    3. Returns the navigation action for frontend execution

    Args:
        state: Current agent state with messages and context

    Returns:
        Updated state with response_text, ui_action, and is_final=True
    """
    intent = state.get("intent", {})
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})

    # Get the action type from intent
    # LLM returns action_type: "goto" with target: "reader_topic"
    # We need to combine them to get action_type: "goto_reader_topic"
    action_type = details.get("action_type", "unknown_action")
    target = details.get("target")

    # If action is "goto" with a target, combine them
    if action_type == "goto" and target:
        # Map target to internal goto action type
        target_to_action = {
            "home": "goto_home",
            "reader_search": "goto_search",
            "reader_topic": "goto_reader_topic",
            "analyst_dashboard": "goto_analyst_topic",
            "editor_dashboard": "goto_editor_topic",
            "admin_articles": "goto_admin_topic",
            "root_users": "goto_root",
            "root_groups": "goto_root",
            "root_topics": "goto_root",
            "root_prompts": "goto_root",
            "root_tonalities": "goto_root",
            "root_resources": "goto_root",
            "user_profile": "goto_user_profile",
            "user_settings": "goto_user_settings",
        }
        action_type = target_to_action.get(target, f"goto_{target}")
        logger.info(f"Navigation: mapped goto target '{target}' to action_type '{action_type}'")

    # Infer navigation action from message if not clear
    if action_type == "unknown_action" or action_type == "goto":
        messages = state.get("messages", [])
        if messages:
            action_type = _infer_navigation_from_message(
                messages[-1].content,
                user_context
            )

    # Check permissions
    permission_result = _check_navigation_permission(
        action_type,
        user_context,
        details.get("topic")
    )

    if not permission_result["allowed"]:
        return {
            "response_text": permission_result["message"],
            "selected_agent": "navigation",
            "is_final": True
        }

    # Get the navigation config
    nav_config = NAVIGATION_PERMISSIONS.get(action_type, {})

    # Handle special navigation types (e.g., goto_back)
    if nav_config.get("special") == "back":
        return {
            "response_text": "Going back to the previous page.",
            "ui_action": {
                "type": "goto_back",  # Special action for frontend to handle
                "params": {}
            },
            "selected_agent": "navigation",
            "routing_reason": "Navigation: go back",
            "is_final": True
        }

    # Get the target section from permissions config
    target_section = nav_config.get("section", "home")

    # Extract navigation parameters
    params = _extract_navigation_params(action_type, target_section, nav_context, details)

    # Build success response
    response_text = _build_navigation_response(action_type, params)

    return {
        "response_text": response_text,
        "ui_action": {
            "type": "goto",  # Unified goto action
            "params": params  # Contains section, topic, article_id
        },
        "selected_agent": "navigation",
        "routing_reason": f"Navigation: goto {target_section}",
        "is_final": True
    }


def _infer_navigation_from_message(message: str, user_context: Dict[str, Any]) -> str:
    """Infer the navigation action type from the user's message."""
    message_lower = message.lower()

    topic_roles = user_context.get("topic_roles", {})
    scopes = user_context.get("scopes", [])
    is_global_admin = "global:admin" in scopes

    # Check for "go back" first (before other keywords that might match)
    if any(phrase in message_lower for phrase in ["go back", "back", "previous", "return to previous", "previous page"]):
        return "goto_back"

    # Check for specific navigation keywords
    if any(word in message_lower for word in ["home", "main page", "landing"]):
        return "goto_home"

    if any(word in message_lower for word in ["search", "find articles", "look for"]):
        return "goto_search"

    if any(word in message_lower for word in ["profile", "my profile", "account"]):
        return "goto_user_profile"

    if any(word in message_lower for word in ["settings", "preferences", "my settings"]):
        return "goto_user_settings"

    # Role-based navigation
    if any(word in message_lower for word in ["global admin", "system admin", "root admin"]):
        if is_global_admin:
            return "goto_root"

    if any(word in message_lower for word in ["admin", "manage", "administration"]):
        if any(role == "admin" for role in topic_roles.values()) or is_global_admin:
            return "goto_admin_topic"

    if any(word in message_lower for word in ["editor", "review", "editorial"]):
        if any(role == "editor" for role in topic_roles.values()):
            return "goto_editor_topic"

    if any(word in message_lower for word in ["analyst", "write", "create article", "my articles"]):
        if any(role == "analyst" for role in topic_roles.values()):
            return "goto_analyst_topic"

    if any(word in message_lower for word in ["read", "reader", "browse", "view articles"]):
        return "goto_reader_topic"

    # Default to home if no specific match
    return "goto_home"


def _check_navigation_permission(
    action_type: str,
    user_context: Dict[str, Any],
    requested_topic: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check if user has permission to perform the navigation action.

    Permission model:
    - "roles": list of roles that can perform the action
    - "any_topic": requires the role on ANY topic
    - "global_only": requires global:admin scope
    """
    requirements = NAVIGATION_PERMISSIONS.get(action_type)

    if not requirements:
        logger.warning(f"Unknown navigation action type: {action_type}")
        return {"allowed": True}

    # Get user's role info
    topic_roles = user_context.get("topic_roles", {})  # {topic: role}
    scopes = user_context.get("scopes", [])

    # Global admin has access to everything
    is_global_admin = "global:admin" in scopes
    if is_global_admin:
        return {"allowed": True}

    # Get required roles
    required_roles = requirements.get("roles", [])

    # Check global_only (e.g., goto_root)
    if requirements.get("global_only"):
        return {
            "allowed": False,
            "message": "You need global admin access for this area."
        }

    # Check any_topic (e.g., goto_analyst_topic - need analyst role on ANY topic)
    if requirements.get("any_topic"):
        # If a specific topic is requested, check that topic
        if requested_topic:
            user_role_for_topic = topic_roles.get(requested_topic)
            if user_role_for_topic in required_roles:
                return {"allowed": True}
            else:
                role_name = required_roles[0] if required_roles else "required"
                return {
                    "allowed": False,
                    "message": f"You need {role_name} access for {requested_topic}."
                }

        # Otherwise, check if they have the role on any topic
        has_role_on_any_topic = any(
            role in required_roles for role in topic_roles.values()
        )
        if has_role_on_any_topic:
            return {"allowed": True}
        else:
            role_name = required_roles[0] if required_roles else "required"
            return {
                "allowed": False,
                "message": f"You need {role_name} access on at least one topic."
            }

    # Default: check if user has any of the required roles on any topic
    all_user_roles = set(topic_roles.values())
    if any(role in required_roles for role in all_user_roles):
        return {"allowed": True}

    # If roles include "reader", allow (everyone is at least a reader)
    if "reader" in required_roles:
        return {"allowed": True}

    return {
        "allowed": False,
        "message": "You don't have permission to access this area."
    }


def _extract_navigation_params(
    action_type: str,
    target_section: str,
    nav_context: Dict[str, Any],
    intent_details: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract parameters for the unified goto action.

    Returns params matching shared/ui_actions.json goto action:
    - section: required - target section from shared/sections.json
    - topic: optional - topic slug for sections requiring topic
    - article_id: optional - article ID for article-specific sections
    """
    params = {
        "section": target_section  # Always include section
    }

    # Include topic - prefer intent_details (explicit from message) over nav_context
    if intent_details.get("topic"):
        params["topic"] = intent_details["topic"]
    elif action_type != "goto_home" and nav_context.get("topic"):
        # For goto_home, only include topic if explicitly mentioned
        params["topic"] = nav_context["topic"]

    # Include article_id if navigating to view an article
    if intent_details.get("article_id"):
        params["article_id"] = intent_details["article_id"]

    return params


def _build_navigation_response(action_type: str, params: Dict[str, Any]) -> str:
    """Build a user-friendly response message for the navigation action."""
    # Format topic for display
    topic = params.get('topic')
    section = params.get('section', 'home')
    topic_display = topic.replace("_", " ").title() if topic else None

    # Get section display name from config
    section_config = SECTION_CONFIG.get(section, {})
    section_name = section_config.get("name", section.replace("_", " ").title())

    # Build contextual message
    navigation_messages = {
        "goto_home": f"Taking you to {topic_display + ' articles' if topic_display else 'home'}.",
        "goto_search": f"Opening search{' for ' + topic_display if topic_display else ''}.",
        "goto_reader_topic": f"Opening {section_name}{' for ' + topic_display if topic_display else ''}.",
        "goto_analyst_topic": f"Opening {section_name}{' for ' + topic_display if topic_display else ''}.",
        "goto_editor_topic": f"Opening {section_name}{' for ' + topic_display if topic_display else ''}.",
        "goto_admin_topic": f"Opening {section_name}{' for ' + topic_display if topic_display else ''}.",
        "goto_root": f"Opening {section_name}.",
        "goto_user_profile": f"Opening {section_name}.",
        "goto_user_settings": f"Opening {section_name}.",
    }

    return navigation_messages.get(action_type, f"Navigating to {section_name}...")
