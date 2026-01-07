"""
UI Action node for the main chat graph.

This node handles UI action intents - requests to trigger specific actions
in the frontend like clicking buttons, switching tabs, saving drafts, etc.
It performs permission checks and returns UI action metadata for the frontend.
"""

from typing import Dict, Any, Optional, List
import logging

from agents.state import AgentState

logger = logging.getLogger(__name__)


# UI Actions that require confirmation before execution
DESTRUCTIVE_ACTIONS = {
    "delete_article",
    "deactivate_article",
    "purge_article",
    "recall_article",
    "delete_resource",
    "delete_account"
}

# UI Actions and their permission requirements
UI_ACTION_PERMISSIONS = {
    # Analyst editor actions
    "save_draft": {"section": "analyst", "min_role": "analyst"},
    "submit_for_review": {"section": "analyst", "min_role": "analyst"},
    "switch_view_editor": {"section": "analyst", "min_role": "analyst"},
    "switch_view_preview": {"section": "analyst", "min_role": "analyst"},
    "switch_view_resources": {"section": "analyst", "min_role": "analyst"},
    "browse_resources": {"section": "analyst", "min_role": "analyst"},
    "add_resource": {"section": "analyst", "min_role": "analyst"},
    "remove_resource": {"section": "analyst", "min_role": "analyst"},

    # Editor actions
    "publish_article": {"section": "editor", "min_role": "editor"},
    "reject_article": {"section": "editor", "min_role": "editor"},
    "download_pdf": {"section": ["editor", "home"], "min_role": "reader"},

    # Admin actions
    "delete_article": {"section": "admin", "min_role": "admin"},
    "deactivate_article": {"section": "admin", "min_role": "admin"},
    "reactivate_article": {"section": "admin", "min_role": "admin"},
    "recall_article": {"section": "admin", "min_role": "admin"},
    "purge_article": {"section": "admin", "min_role": "admin"},
    "delete_resource": {"section": "admin", "min_role": "admin"},

    # Home page actions
    "select_topic_tab": {"section": "home", "min_role": "reader"},
    "open_article": {"section": "home", "min_role": "reader"},
    "rate_article": {"section": "home", "min_role": "reader"},
    "search_articles": {"section": ["home", "search"], "min_role": "reader"},
    "close_modal": {"section": "*", "min_role": "reader"},

    # Profile actions
    "switch_profile_tab": {"section": "profile", "min_role": "reader"},
    "save_tonality": {"section": "profile", "min_role": "reader"},
    "delete_account": {"section": "profile", "min_role": "reader"},
}

# Role hierarchy for permission checking
ROLE_HIERARCHY = {
    "reader": 1,
    "editor": 2,
    "analyst": 3,
    "admin": 4
}


def ui_action_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle UI action intent by validating permissions and building action response.

    This node:
    1. Extracts the requested action from intent
    2. Checks if user has permission for the action
    3. For destructive actions, returns a confirmation request
    4. Otherwise, returns the UI action for frontend execution

    Args:
        state: Current agent state with messages and context

    Returns:
        Updated state with response_text, ui_action or confirmation, and is_final=True
    """
    intent = state.get("intent", {})
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})

    # Get the action type from intent
    action_type = details.get("action_type", "unknown_action")

    # Infer action from message if not clear
    if action_type == "unknown_action":
        messages = state.get("messages", [])
        if messages:
            action_type = _infer_action_from_message(
                messages[-1].content,
                nav_context.get("section", "home")
            )

    # Check permissions
    permission_result = _check_action_permission(
        action_type,
        user_context,
        nav_context
    )

    if not permission_result["allowed"]:
        return {
            "response_text": permission_result["message"],
            "selected_agent": "ui_action",
            "is_final": True
        }

    # Extract action parameters
    params = _extract_action_params(action_type, nav_context, details)

    # Check if action requires confirmation
    if action_type in DESTRUCTIVE_ACTIONS:
        return _build_confirmation_response(action_type, params, nav_context)

    # Build success response
    response_text = _build_action_response(action_type, params)

    return {
        "response_text": response_text,
        "ui_action": {
            "type": action_type,
            "params": params
        },
        "selected_agent": "ui_action",
        "routing_reason": f"UI action: {action_type}",
        "is_final": True
    }


def _infer_action_from_message(message: str, section: str) -> str:
    """Infer the UI action type from the user's message."""
    message_lower = message.lower()

    # Section-specific action inference
    if section == "analyst":
        if "save" in message_lower:
            return "save_draft"
        if "submit" in message_lower or "review" in message_lower:
            return "submit_for_review"
        if "preview" in message_lower:
            return "switch_view_preview"
        if "resource" in message_lower and "view" in message_lower:
            return "switch_view_resources"
        if "resource" in message_lower and ("add" in message_lower or "browse" in message_lower):
            return "browse_resources"

    elif section == "editor":
        if "publish" in message_lower:
            return "publish_article"
        if "reject" in message_lower or "send back" in message_lower:
            return "reject_article"
        if "pdf" in message_lower or "download" in message_lower:
            return "download_pdf"

    elif section == "admin":
        if "delete" in message_lower:
            return "delete_article"
        if "deactivate" in message_lower:
            return "deactivate_article"
        if "reactivate" in message_lower:
            return "reactivate_article"
        if "recall" in message_lower:
            return "recall_article"
        if "purge" in message_lower:
            return "purge_article"

    elif section == "home":
        if "search" in message_lower:
            return "search_articles"
        if "rate" in message_lower:
            return "rate_article"
        if "open" in message_lower or "view" in message_lower:
            return "open_article"

    return "unknown_action"


def _check_action_permission(
    action_type: str,
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Check if user has permission to perform the action."""
    # Get action requirements
    requirements = UI_ACTION_PERMISSIONS.get(action_type)

    if not requirements:
        # Unknown action - allow by default but log warning
        logger.warning(f"Unknown UI action type: {action_type}")
        return {"allowed": True}

    # Get user's role info
    highest_role = user_context.get("highest_role", "reader")
    topic_roles = user_context.get("topic_roles", {})
    scopes = user_context.get("scopes", [])
    current_section = nav_context.get("section", "home")
    current_topic = nav_context.get("topic")

    # Check section requirement
    required_section = requirements.get("section")
    if required_section and required_section != "*":
        if isinstance(required_section, list):
            if current_section not in required_section:
                return {
                    "allowed": False,
                    "message": f"This action is only available in {', '.join(required_section)} sections."
                }
        elif current_section != required_section:
            return {
                "allowed": False,
                "message": f"This action is only available in the {required_section} section."
            }

    # Check role requirement
    min_role = requirements.get("min_role", "reader")
    user_role_level = ROLE_HIERARCHY.get(highest_role, 1)
    required_level = ROLE_HIERARCHY.get(min_role, 1)

    # Also check topic-specific role
    if current_topic and current_topic in topic_roles:
        topic_role = topic_roles[current_topic]
        topic_role_level = ROLE_HIERARCHY.get(topic_role, 1)
        user_role_level = max(user_role_level, topic_role_level)

    # Global admin override
    if "global:admin" in scopes:
        user_role_level = ROLE_HIERARCHY["admin"]

    if user_role_level < required_level:
        return {
            "allowed": False,
            "message": f"You need {min_role} access to perform this action."
        }

    return {"allowed": True}


def _extract_action_params(
    action_type: str,
    nav_context: Dict[str, Any],
    intent_details: Dict[str, Any]
) -> Dict[str, Any]:
    """Extract parameters for the UI action from context."""
    params = {}

    # Include article_id if relevant
    if nav_context.get("article_id"):
        params["article_id"] = nav_context["article_id"]

    # Include topic if relevant
    if nav_context.get("topic"):
        params["topic"] = nav_context["topic"]

    # Include resource_id if relevant
    if nav_context.get("resource_id"):
        params["resource_id"] = nav_context["resource_id"]

    # Copy any extra params from intent details
    for key in ["target_tab", "search_query", "rating", "view_mode"]:
        if key in intent_details:
            params[key] = intent_details[key]

    return params


def _build_confirmation_response(
    action_type: str,
    params: Dict[str, Any],
    nav_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Build a confirmation request for destructive actions."""
    article_id = params.get("article_id")

    # Build confirmation messages based on action
    confirmations = {
        "delete_article": {
            "title": "Delete Article",
            "message": f"Are you sure you want to delete article #{article_id}? This action cannot be undone.",
            "confirm_label": "Delete",
            "confirm_endpoint": f"/api/content/article/{article_id}",
            "confirm_method": "DELETE"
        },
        "deactivate_article": {
            "title": "Deactivate Article",
            "message": f"Deactivate article #{article_id}? It will be hidden from users but can be reactivated.",
            "confirm_label": "Deactivate",
            "confirm_endpoint": f"/api/content/article/{article_id}/deactivate",
            "confirm_method": "POST"
        },
        "reactivate_article": {
            "title": "Reactivate Article",
            "message": f"Reactivate article #{article_id}? It will become visible again.",
            "confirm_label": "Reactivate",
            "confirm_endpoint": f"/api/content/article/{article_id}/reactivate",
            "confirm_method": "POST"
        },
        "recall_article": {
            "title": "Recall Article",
            "message": f"Recall article #{article_id}? It will be unpublished and returned to draft status.",
            "confirm_label": "Recall",
            "confirm_endpoint": f"/api/content/article/{article_id}/recall",
            "confirm_method": "POST"
        },
        "purge_article": {
            "title": "Permanently Delete Article",
            "message": f"PERMANENTLY delete article #{article_id}? This cannot be undone!",
            "confirm_label": "Permanently Delete",
            "confirm_endpoint": f"/api/content/article/{article_id}/purge",
            "confirm_method": "DELETE"
        },
        "delete_resource": {
            "title": "Delete Resource",
            "message": f"Delete resource #{params.get('resource_id')}? This action cannot be undone.",
            "confirm_label": "Delete",
            "confirm_endpoint": f"/api/content/resource/{params.get('resource_id')}",
            "confirm_method": "DELETE"
        },
        "delete_account": {
            "title": "Delete Account",
            "message": "Delete your account? All your data will be permanently removed.",
            "confirm_label": "Delete My Account",
            "confirm_endpoint": "/api/auth/account",
            "confirm_method": "DELETE"
        }
    }

    conf = confirmations.get(action_type, {
        "title": f"Confirm {action_type}",
        "message": "Are you sure you want to perform this action?",
        "confirm_label": "Confirm",
        "confirm_endpoint": "/api/action",
        "confirm_method": "POST"
    })

    import uuid
    confirmation_id = str(uuid.uuid4())

    return {
        "response_text": f"{conf['message']}",
        "confirmation": {
            "id": confirmation_id,
            "type": action_type,
            "title": conf["title"],
            "message": conf["message"],
            "article_id": article_id,
            "confirm_label": conf["confirm_label"],
            "cancel_label": "Cancel",
            "confirm_endpoint": conf["confirm_endpoint"],
            "confirm_method": conf["confirm_method"],
            "confirm_body": params
        },
        "requires_hitl": True,
        "selected_agent": "ui_action",
        "is_final": True
    }


def _build_action_response(action_type: str, params: Dict[str, Any]) -> str:
    """Build a user-friendly response message for the action."""
    action_messages = {
        "save_draft": "Saving your draft...",
        "submit_for_review": "Submitting article for editorial review...",
        "switch_view_editor": "Switching to editor view.",
        "switch_view_preview": "Switching to preview mode.",
        "switch_view_resources": "Showing resources panel.",
        "browse_resources": "Opening resource browser...",
        "add_resource": "Adding resource to article...",
        "remove_resource": "Removing resource from article...",
        "publish_article": "Publishing article...",
        "reject_article": "Sending article back for revisions...",
        "download_pdf": "Generating PDF download...",
        "select_topic_tab": f"Switching to {params.get('topic', 'selected')} topic.",
        "open_article": "Opening article...",
        "rate_article": "Opening rating dialog...",
        "search_articles": "Searching articles...",
        "close_modal": "Closing dialog.",
        "switch_profile_tab": "Switching tab.",
        "save_tonality": "Saving your preferences...",
    }

    return action_messages.get(action_type, f"Executing {action_type}...")
