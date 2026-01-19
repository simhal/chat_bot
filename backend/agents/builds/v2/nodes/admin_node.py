"""
Admin node for the main chat graph.

This node handles admin role context:
- Article management (delete, deactivate, reactivate, recall, purge)
- Resource management
- Admin view switching
- System administration

Routes based on nav_context.role == 'admin'
"""

from typing import Dict, Any, Optional
import logging
import uuid

from agents.builds.v2.state import AgentState
from agents.shared.permission_utils import check_topic_permission, validate_article_access

logger = logging.getLogger(__name__)


# Admin UI actions - destructive actions require confirmation
ADMIN_UI_ACTIONS = {
    # Article management (destructive)
    "delete_article": {"destructive": True, "requires_article": True},
    "deactivate_article": {"destructive": True, "requires_article": True},
    "reactivate_article": {"requires_article": True},
    "recall_article": {"destructive": True, "requires_article": True},
    "purge_article": {"destructive": True, "requires_article": True, "global_only": True},
    # Resource management
    "delete_resource": {"destructive": True, "requires_resource": True},
    # View switching
    "switch_admin_view": {},
    "switch_admin_topic": {},
    "switch_admin_subview": {},
    # Global admin
    "switch_global_view": {"global_only": True},
}

# Confirmation messages for destructive actions
CONFIRMATION_MESSAGES = {
    "delete_article": {
        "title": "Delete Article",
        "message": "Are you sure you want to delete article #{article_id}? This action cannot be undone.",
        "confirm_label": "Delete",
        "endpoint": "/api/admin/{topic}/article/{article_id}",
        "method": "DELETE"
    },
    "deactivate_article": {
        "title": "Deactivate Article",
        "message": "Deactivate article #{article_id}? It will be hidden from users but can be reactivated.",
        "confirm_label": "Deactivate",
        "endpoint": "/api/admin/{topic}/article/{article_id}",
        "method": "DELETE"
    },
    "recall_article": {
        "title": "Recall Article",
        "message": "Recall article #{article_id}? It will be unpublished and returned to draft status.",
        "confirm_label": "Recall",
        "endpoint": "/api/admin/{topic}/article/{article_id}/recall",
        "method": "POST"
    },
    "purge_article": {
        "title": "Permanently Delete Article",
        "message": "PERMANENTLY delete article #{article_id}? This cannot be undone!",
        "confirm_label": "Permanently Delete",
        "endpoint": "/api/admin/global/article/{article_id}/purge",
        "method": "DELETE"
    },
    "delete_resource": {
        "title": "Delete Resource",
        "message": "Delete resource #{resource_id}? This action cannot be undone.",
        "confirm_label": "Delete",
        "endpoint": "/api/resources/{resource_id}",
        "method": "DELETE"
    },
}


def admin_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle admin context requests.

    This node handles:
    1. Admin UI actions (delete, deactivate, recall, etc.)
    2. Admin view navigation
    3. System administration queries

    Args:
        state: Current agent state with messages and context

    Returns:
        Updated state with response and optional confirmation dialogs
    """
    intent = state.get("intent", {})
    intent_type = intent.get("intent_type", "")
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})
    messages = state.get("messages", [])

    # Check admin permission
    scopes = user_context.get("scopes", [])
    topic = details.get("topic") or nav_context.get("topic")
    is_global_admin = "global:admin" in scopes

    # Check for UI action
    action_type = details.get("action_type", "")
    if not action_type and intent_type == "ui_action":
        # Infer from message
        user_query = messages[-1].content if messages else ""
        action_type = _infer_admin_action(user_query)

    if action_type in ADMIN_UI_ACTIONS:
        return _handle_admin_ui_action(
            action_type, details, user_context, nav_context, is_global_admin, topic
        )

    # Handle general admin queries
    return _handle_admin_query(messages, user_context, nav_context)


def _handle_admin_ui_action(
    action_type: str,
    details: Dict[str, Any],
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any],
    is_global_admin: bool,
    topic: Optional[str]
) -> Dict[str, Any]:
    """Handle admin-specific UI actions."""

    action_config = ADMIN_UI_ACTIONS.get(action_type, {})

    # Check global_only permission
    if action_config.get("global_only") and not is_global_admin:
        return {
            "response_text": "You need global admin access for this action.",
            "selected_agent": "admin",
            "is_final": True
        }

    # Check topic permission for non-global actions
    if topic and not is_global_admin and not action_config.get("global_only"):
        allowed, error_msg = check_topic_permission(topic, "admin", user_context)
        if not allowed:
            return {
                "response_text": error_msg,
                "selected_agent": "admin",
                "is_final": True
            }

    # Extract parameters
    params = _extract_params(details, nav_context)

    # Validate article access if required
    if action_config.get("requires_article"):
        article_id = params.get("article_id")
        if not article_id:
            return {
                "response_text": "Please specify an article ID for this action.",
                "selected_agent": "admin",
                "is_final": True
            }

        try:
            from database import SessionLocal
            db = SessionLocal()
            try:
                allowed, error_msg, article_info = validate_article_access(
                    article_id, user_context, db, topic
                )
                if not allowed:
                    return {
                        "response_text": error_msg,
                        "selected_agent": "admin",
                        "is_final": True
                    }
                if article_info and not params.get("topic"):
                    params["topic"] = article_info.get("topic")
                    topic = params["topic"]
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Article access validation failed: {e}")

    # Handle destructive actions with confirmation
    if action_config.get("destructive"):
        return _build_confirmation_response(action_type, params, topic)

    # Handle non-destructive admin actions
    response_text = _build_admin_action_response(action_type, params)

    return {
        "response_text": response_text,
        "ui_action": {
            "type": action_type,
            "params": params
        },
        "selected_agent": "admin",
        "routing_reason": f"Admin action: {action_type}",
        "is_final": True
    }


def _build_confirmation_response(
    action_type: str,
    params: Dict[str, Any],
    topic: Optional[str]
) -> Dict[str, Any]:
    """Build confirmation dialog for destructive actions."""
    article_id = params.get("article_id")
    resource_id = params.get("resource_id")
    topic = topic or params.get("topic", "general")

    conf_template = CONFIRMATION_MESSAGES.get(action_type, {
        "title": f"Confirm {action_type}",
        "message": "Are you sure you want to perform this action?",
        "confirm_label": "Confirm",
        "endpoint": "/api/action",
        "method": "POST"
    })

    # Format message and endpoint with parameters
    message = conf_template["message"].format(
        article_id=article_id,
        resource_id=resource_id
    )
    endpoint = conf_template["endpoint"].format(
        topic=topic,
        article_id=article_id,
        resource_id=resource_id
    )

    confirmation_id = str(uuid.uuid4())

    return {
        "response_text": message,
        "confirmation": {
            "id": confirmation_id,
            "type": action_type,
            "title": conf_template["title"],
            "message": message,
            "article_id": article_id,
            "resource_id": resource_id,
            "confirm_label": conf_template["confirm_label"],
            "cancel_label": "Cancel",
            "confirm_endpoint": endpoint,
            "confirm_method": conf_template["method"],
            "confirm_body": params
        },
        "requires_hitl": True,
        "selected_agent": "admin",
        "is_final": True
    }


def _handle_admin_query(
    messages: list,
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle general admin queries."""
    if not messages:
        topic = nav_context.get("topic")
        if topic:
            return {
                "response_text": f"You're in the admin panel for {topic.replace('_', ' ').title()}. "
                               "You can manage articles, resources, and permissions here.\n\n"
                               "What would you like to do?",
                "selected_agent": "admin",
                "is_final": True
            }
        return {
            "response_text": "You're in the admin panel. Select a topic to manage its content, "
                           "or access global admin settings for system-wide configuration.\n\n"
                           "What would you like to do?",
            "selected_agent": "admin",
            "is_final": True
        }

    user_query = messages[-1].content.lower()

    # Provide contextual help
    if "help" in user_query or "what can" in user_query:
        return {
            "response_text": """**Admin Actions Available:**

**Article Management:**
- Delete article - Remove an article permanently
- Deactivate article - Hide an article (can be reactivated)
- Reactivate article - Restore a deactivated article
- Recall article - Unpublish and return to draft

**Resource Management:**
- Delete resource - Remove a resource file

**Navigation:**
- Switch admin view - Change the admin dashboard view
- Switch topic - Manage a different topic

What would you like to do?""",
            "selected_agent": "admin",
            "is_final": True
        }

    return {
        "response_text": "I can help you manage content as an admin. "
                       "What would you like to do? (delete, deactivate, recall, etc.)",
        "selected_agent": "admin",
        "is_final": True
    }


def _infer_admin_action(message: str) -> Optional[str]:
    """Infer admin action from message."""
    message_lower = message.lower()

    if "delete" in message_lower and "resource" in message_lower:
        return "delete_resource"
    if "delete" in message_lower:
        return "delete_article"
    if "deactivate" in message_lower:
        return "deactivate_article"
    if "reactivate" in message_lower or "restore" in message_lower:
        return "reactivate_article"
    if "recall" in message_lower or "unpublish" in message_lower:
        return "recall_article"
    if "purge" in message_lower or "permanent" in message_lower:
        return "purge_article"
    if "switch" in message_lower and "view" in message_lower:
        return "switch_admin_view"
    if "switch" in message_lower and "topic" in message_lower:
        return "switch_admin_topic"

    return None


def _extract_params(details: Dict[str, Any], nav_context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract parameters from details and nav_context."""
    params = {}

    # Article ID
    if details.get("article_id"):
        params["article_id"] = details["article_id"]
    elif nav_context.get("article_id"):
        params["article_id"] = nav_context["article_id"]

    # Resource ID
    if details.get("resource_id"):
        params["resource_id"] = details["resource_id"]
    elif nav_context.get("resource_id"):
        params["resource_id"] = nav_context["resource_id"]

    # Topic
    if details.get("topic"):
        params["topic"] = details["topic"]
    elif nav_context.get("topic"):
        params["topic"] = nav_context["topic"]

    # View parameters
    for key in ["view", "subview", "tab"]:
        if details.get(key):
            params[key] = details[key]

    return params


def _build_admin_action_response(action_type: str, params: Dict[str, Any]) -> str:
    """Build response message for non-destructive admin actions."""
    topic = params.get("topic")
    topic_display = topic.replace("_", " ").title() if topic else None

    responses = {
        "reactivate_article": f"Reactivating article #{params.get('article_id')}...",
        "switch_admin_view": f"Switching admin view to {params.get('view', 'selected view')}.",
        "switch_admin_topic": f"Switching to {topic_display or 'selected'} topic.",
        "switch_admin_subview": f"Switching to {params.get('subview', 'selected')} subview.",
        "switch_global_view": f"Switching to {params.get('view', 'selected')} view.",
    }

    return responses.get(action_type, f"Executing {action_type}...")
