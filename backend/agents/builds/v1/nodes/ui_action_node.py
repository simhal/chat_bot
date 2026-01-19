"""
UI Action node for the main chat graph.

This node handles UI action intents - requests to trigger specific actions
in the frontend like clicking buttons, switching tabs, saving drafts, etc.
It performs permission checks and returns UI action metadata for the frontend.
"""

from typing import Dict, Any, Optional, List
import logging

from agents.builds.v1.state import AgentState
from agents.shared.permission_utils import validate_article_access

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
# "roles" = list of roles that can perform the action (user must have at least one)
# "section" = required section context (* = any section)
# "topic_scoped" = True if the action requires the role for the CURRENT topic
UI_ACTION_PERMISSIONS = {
    # Analyst editor actions (topic-scoped: need analyst role for current topic)
    "save_draft": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},
    "submit_for_review": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},
    "switch_view_editor": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},
    "switch_view_preview": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},
    "switch_view_resources": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},
    "browse_resources": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},
    "add_resource": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},
    "remove_resource": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},
    "link_resource": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},
    "unlink_resource": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},
    "open_resource_modal": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},

    # Analyst hub actions (can be triggered from analyst hub)
    "create_new_article": {"section": "*", "roles": ["analyst"], "any_topic": True},
    "edit_article": {"section": "*", "roles": ["analyst"], "any_topic": True},
    "view_article": {"section": "*", "roles": ["reader", "analyst", "editor", "admin"]},
    "submit_article": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},

    # Editor actions (topic-scoped: need editor role for current topic)
    "publish_article": {"section": "editor", "roles": ["editor"], "topic_scoped": True},
    "reject_article": {"section": "editor", "roles": ["editor"], "topic_scoped": True},
    "download_pdf": {"section": ["editor", "home", "reader"], "roles": ["reader", "analyst", "editor", "admin"]},

    # Admin actions (topic-scoped: need admin role for current topic)
    "delete_article": {"section": "admin", "roles": ["admin"], "topic_scoped": True},
    "deactivate_article": {"section": "admin", "roles": ["admin"], "topic_scoped": True},
    "reactivate_article": {"section": "admin", "roles": ["admin"], "topic_scoped": True},
    "recall_article": {"section": "admin", "roles": ["admin"], "topic_scoped": True},
    "purge_article": {"section": "admin", "roles": ["admin"], "topic_scoped": True},
    "delete_resource": {"section": "admin", "roles": ["admin"], "topic_scoped": True},

    # Admin view switching
    "switch_admin_view": {"section": "admin", "roles": ["admin"], "topic_scoped": True},
    "switch_admin_topic": {"section": "admin", "roles": ["admin"], "any_topic": True},
    "switch_admin_subview": {"section": "admin", "roles": ["admin"], "topic_scoped": True},

    # Home page actions (any authenticated user)
    "select_topic_tab": {"section": "home", "roles": ["reader", "analyst", "editor", "admin"]},
    "open_article": {"section": ["home", "reader", "search"], "roles": ["reader", "analyst", "editor", "admin"]},
    "rate_article": {"section": ["home", "reader"], "roles": ["reader", "analyst", "editor", "admin"]},
    "search_articles": {"section": ["home", "search"], "roles": ["reader", "analyst", "editor", "admin"]},
    "clear_search": {"section": ["home", "search"], "roles": ["reader", "analyst", "editor", "admin"]},

    # Topic selection (any authenticated user in relevant sections)
    "select_topic": {"section": ["analyst", "editor", "admin", "home", "reader"], "roles": ["reader", "analyst", "editor", "admin"]},

    # Common modal/dialog actions
    "close_modal": {"section": "*", "roles": ["reader", "analyst", "editor", "admin"]},
    "confirm_action": {"section": "*", "roles": ["reader", "analyst", "editor", "admin"]},
    "cancel_action": {"section": "*", "roles": ["reader", "analyst", "editor", "admin"]},

    # Context update actions (triggered by chat to request article/resource info)
    "select_article": {"section": "*", "roles": ["reader", "analyst", "editor", "admin"]},
    "select_resource": {"section": "analyst", "roles": ["analyst"], "topic_scoped": True},
    "focus_article": {"section": "*", "roles": ["reader", "analyst", "editor", "admin"]},

    # Profile actions (any authenticated user)
    "switch_profile_tab": {"section": "profile", "roles": ["reader", "analyst", "editor", "admin"]},
    "save_tonality": {"section": "profile", "roles": ["reader", "analyst", "editor", "admin"]},
    "delete_account": {"section": "profile", "roles": ["reader", "analyst", "editor", "admin"]},

    # Navigation actions (check if user has ANY matching role on ANY topic)
    "goto_home": {"section": "*", "roles": ["reader", "analyst", "editor", "admin"]},
    "goto_search": {"section": "*", "roles": ["reader", "analyst", "editor", "admin"]},
    "goto_reader_topic": {"section": "*", "roles": ["reader", "analyst", "editor", "admin"], "any_topic": True},
    "goto_analyst_topic": {"section": "*", "roles": ["analyst"], "any_topic": True},
    "goto_editor_topic": {"section": "*", "roles": ["editor"], "any_topic": True},
    "goto_admin_topic": {"section": "*", "roles": ["admin"], "any_topic": True},
    "goto_root": {"section": "*", "roles": ["admin"], "global_only": True},
    "goto_user_profile": {"section": "*", "roles": ["reader", "analyst", "editor", "admin"]},
    "goto_user_settings": {"section": "*", "roles": ["reader", "analyst", "editor", "admin"]},

    # Global admin actions
    "switch_global_view": {"section": "root", "roles": ["admin"], "global_only": True},
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

    # Check role context and provide helpful navigation guidance
    current_role = nav_context.get("role", "reader")
    topic = details.get("topic") or nav_context.get("topic")

    # Check if user needs to switch to a different role context
    role_guidance = _check_role_context_for_action(action_type, current_role, user_context, topic)
    if role_guidance:
        return role_guidance

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

    # Validate article access if article_id is involved
    article_info = None
    article_actions = ["edit_article", "view_article", "open_article", "publish_article",
                       "reject_article", "delete_article", "deactivate_article",
                       "reactivate_article", "recall_article", "purge_article", "download_pdf"]

    if action_type in article_actions and params.get("article_id"):
        try:
            from database import SessionLocal
            db = SessionLocal()
            try:
                allowed, error_msg, article_info = validate_article_access(
                    params["article_id"], user_context, db, topic
                )
                if not allowed:
                    return {
                        "response_text": error_msg,
                        "selected_agent": "ui_action",
                        "is_final": True
                    }
                # Update params with article's topic if not set
                if article_info and not params.get("topic"):
                    params["topic"] = article_info.get("topic")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Article access validation failed: {e}")

    # Check if action requires confirmation
    if action_type in DESTRUCTIVE_ACTIONS:
        return _build_confirmation_response(action_type, params, nav_context)

    # Build success response
    response_text = _build_action_response(action_type, params)

    result = {
        "response_text": response_text,
        "ui_action": {
            "type": action_type,
            "params": params
        },
        "selected_agent": "ui_action",
        "routing_reason": f"UI action: {action_type}",
        "is_final": True
    }

    # Include article context for frontend context update
    if article_info:
        result["article_context"] = {
            "article_id": article_info.get("id"),
            "topic": article_info.get("topic"),
            "status": article_info.get("status"),
            "headline": article_info.get("headline"),
            "keywords": article_info.get("keywords")
        }

    return result


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
    """
    Check if user has permission to perform the action.

    Permission model:
    - "roles": list of roles that can perform the action
    - "section": required section context (* = any)
    - "topic_scoped": requires the role for the CURRENT topic
    - "any_topic": requires the role on ANY topic (for navigation)
    - "global_only": requires global:admin scope
    """
    requirements = UI_ACTION_PERMISSIONS.get(action_type)

    if not requirements:
        logger.warning(f"Unknown UI action type: {action_type}")
        return {"allowed": True}

    # Get user's role info
    topic_roles = user_context.get("topic_roles", {})  # {topic: role}
    scopes = user_context.get("scopes", [])
    current_section = nav_context.get("section", "home")
    current_topic = nav_context.get("topic")

    # Global admin has access to everything
    is_global_admin = "global:admin" in scopes
    if is_global_admin:
        return {"allowed": True}

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

    # Get required roles
    required_roles = requirements.get("roles", [])

    # Check global_only (e.g., goto_admin_global)
    if requirements.get("global_only"):
        return {
            "allowed": False,
            "message": "You need global admin access for this action."
        }

    # Check any_topic (e.g., goto_analyst - need analyst role on ANY topic)
    if requirements.get("any_topic"):
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

    # Check topic_scoped (e.g., save_draft - need analyst role for CURRENT topic)
    if requirements.get("topic_scoped"):
        if not current_topic:
            return {
                "allowed": False,
                "message": "No topic selected. Please select a topic first."
            }
        user_role_for_topic = topic_roles.get(current_topic)
        if user_role_for_topic in required_roles:
            return {"allowed": True}
        else:
            role_name = required_roles[0] if required_roles else "required"
            return {
                "allowed": False,
                "message": f"You need {role_name} access for {current_topic}."
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
        "message": f"You don't have permission for this action."
    }


def _extract_action_params(
    action_type: str,
    nav_context: Dict[str, Any],
    intent_details: Dict[str, Any]
) -> Dict[str, Any]:
    """Extract parameters for the UI action from context."""
    params = {}

    # Include article_id - prefer intent_details (explicit from message) over nav_context
    if intent_details.get("article_id"):
        params["article_id"] = intent_details["article_id"]
    elif nav_context.get("article_id"):
        params["article_id"] = nav_context["article_id"]

    # Include topic - handling depends on action type
    # For goto_home: only include topic if explicitly mentioned (from intent_details)
    # For other actions: fallback to nav_context topic
    if intent_details.get("topic"):
        params["topic"] = intent_details["topic"]
    elif action_type != "goto_home" and nav_context.get("topic"):
        # Only fallback to nav_context topic for non-home navigation
        params["topic"] = nav_context["topic"]

    # Include resource_id if relevant
    if intent_details.get("resource_id"):
        params["resource_id"] = intent_details["resource_id"]
    elif nav_context.get("resource_id"):
        params["resource_id"] = nav_context["resource_id"]

    # Copy extra params from intent details (matching frontend UIAction params)
    extra_params = [
        "target_tab", "search_query", "rating", "view_mode",
        # Tab/view switching params
        "tab", "view", "subview",
        # Scope for filtering
        "scope", "action",
        # Confirmation params (for destructive actions)
        "requires_confirmation", "confirmation_message", "confirmed"
    ]
    for key in extra_params:
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
    topic = nav_context.get("topic", "general")  # Get topic from nav_context

    # Build confirmation messages based on action
    # Use role-based API endpoints: /api/admin/{topic}/... for admin actions
    confirmations = {
        "delete_article": {
            "title": "Delete Article",
            "message": f"Are you sure you want to delete article #{article_id}? This action cannot be undone.",
            "confirm_label": "Delete",
            "confirm_endpoint": f"/api/admin/{topic}/article/{article_id}",
            "confirm_method": "DELETE"
        },
        "deactivate_article": {
            "title": "Deactivate Article",
            "message": f"Deactivate article #{article_id}? It will be hidden from users but can be reactivated.",
            "confirm_label": "Deactivate",
            "confirm_endpoint": f"/api/admin/{topic}/article/{article_id}",  # Soft delete = deactivate
            "confirm_method": "DELETE"
        },
        "reactivate_article": {
            "title": "Reactivate Article",
            "message": f"Reactivate article #{article_id}? It will become visible again.",
            "confirm_label": "Reactivate",
            "confirm_endpoint": f"/api/admin/{topic}/article/{article_id}/reactivate",
            "confirm_method": "POST"
        },
        "recall_article": {
            "title": "Recall Article",
            "message": f"Recall article #{article_id}? It will be unpublished and returned to draft status.",
            "confirm_label": "Recall",
            "confirm_endpoint": f"/api/admin/{topic}/article/{article_id}/recall",
            "confirm_method": "POST"
        },
        "purge_article": {
            "title": "Permanently Delete Article",
            "message": f"PERMANENTLY delete article #{article_id}? This cannot be undone!",
            "confirm_label": "Permanently Delete",
            "confirm_endpoint": f"/api/admin/global/article/{article_id}/purge",
            "confirm_method": "DELETE"
        },
        "delete_resource": {
            "title": "Delete Resource",
            "message": f"Delete resource #{params.get('resource_id')}? This action cannot be undone.",
            "confirm_label": "Delete",
            "confirm_endpoint": f"/api/resources/{params.get('resource_id')}",
            "confirm_method": "DELETE"
        },
        "delete_account": {
            "title": "Delete Account",
            "message": "Delete your account? All your data will be permanently removed.",
            "confirm_label": "Delete My Account",
            "confirm_endpoint": "/api/user/account",
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
    # Format topic for display
    topic = params.get('topic')
    topic_display = topic.replace("_", " ").title() if topic else None

    action_messages = {
        # Analyst editor actions
        "save_draft": "Saving your draft...",
        "submit_for_review": "Submitting article for editorial review...",
        "switch_view_editor": "Switching to editor view.",
        "switch_view_preview": "Switching to preview mode.",
        "switch_view_resources": "Showing resources panel.",
        "browse_resources": "Opening resource browser...",
        "add_resource": "Adding resource to article...",
        "remove_resource": "Removing resource from article...",
        "link_resource": "Linking resource to article...",
        "unlink_resource": "Removing resource link from article...",
        "open_resource_modal": "Opening resource selection...",
        # Analyst hub actions
        "create_new_article": f"Creating new article{' for ' + topic_display if topic_display else ''}...",
        "edit_article": f"Opening article #{params.get('article_id', '')} in the editor...",
        "view_article": f"Opening article #{params.get('article_id', '')}...",
        "submit_article": "Submitting article for review...",
        # Editor actions
        "publish_article": "Publishing article...",
        "reject_article": "Sending article back for revisions...",
        "download_pdf": "Generating PDF download...",
        # Admin view switching
        "switch_admin_view": f"Switching admin view to {params.get('view', 'selected view')}.",
        "switch_admin_topic": f"Switching to {topic_display or 'selected'} topic.",
        "switch_admin_subview": f"Switching to {params.get('subview', 'selected')} subview.",
        # Home/reader actions
        "select_topic_tab": f"Switching to {topic_display or 'selected'} topic.",
        "select_topic": f"Selecting {topic_display or 'topic'} in the topic dropdown.",
        "open_article": f"Opening article{' #' + str(params.get('article_id')) if params.get('article_id') else ''}...",
        "rate_article": "Opening rating dialog...",
        "search_articles": f"Searching articles{' for ' + params.get('search_query', '') if params.get('search_query') else ''}...",
        "clear_search": "Clearing search.",
        # Common modal/dialog actions
        "close_modal": "Closing dialog.",
        "confirm_action": "Confirming action...",
        "cancel_action": "Cancelling action.",
        # Context update actions
        "select_article": f"Selecting article #{params.get('article_id', '')}.",
        "select_resource": f"Selecting resource #{params.get('resource_id', '')}.",
        "focus_article": f"Focusing on article #{params.get('article_id', '')}.",
        # Profile actions
        "switch_profile_tab": f"Switching to {params.get('tab', 'selected')} tab.",
        "save_tonality": "Saving your preferences...",
        # Navigation actions (goto_*)
        "goto_home": f"Taking you to {topic_display + ' articles' if topic_display else 'home'}.",
        "goto_search": f"Opening search{' for ' + topic_display if topic_display else ''}.",
        "goto_reader_topic": f"Opening reader{' for ' + topic_display if topic_display else ''}.",
        "goto_analyst_topic": f"Opening analyst hub{' for ' + topic_display if topic_display else ''}.",
        "goto_editor_topic": f"Opening editor hub{' for ' + topic_display if topic_display else ''}.",
        "goto_admin_topic": f"Opening topic admin{' for ' + topic_display if topic_display else ''}.",
        "goto_root": "Opening global admin settings.",
        "goto_user_profile": "Opening your profile.",
        "goto_user_settings": "Opening your settings.",
        # Global admin actions
        "switch_global_view": f"Switching to {params.get('view', 'selected')} view.",
    }

    return action_messages.get(action_type, f"Executing {action_type}...")


def _check_role_context_for_action(
    action_type: str,
    current_role: str,
    user_context: Dict[str, Any],
    topic: Optional[str]
) -> Optional[Dict[str, Any]]:
    """
    Check if user is in the right role context for the action.
    Returns guidance navigation if they need to switch contexts, None if OK.
    """
    highest_role = user_context.get("highest_role", "reader")
    topic_roles = user_context.get("topic_roles", {})
    scopes = user_context.get("scopes", [])

    # Check for global admin
    is_global_admin = "global:admin" in scopes

    # Check if user has admin access for current topic
    has_admin_access = highest_role == "admin" or is_global_admin or \
                      (topic and topic_roles.get(topic) == "admin")

    # Admin actions from non-admin context
    admin_actions = [
        "delete_article", "deactivate_article", "reactivate_article",
        "recall_article", "purge_article", "delete_resource"
    ]

    if action_type in admin_actions and current_role != "admin":
        if has_admin_access:
            return {
                "response_text": f"I'll take you to the admin dashboard first, where you can manage articles.",
                "navigation": {
                    "action": "navigate",
                    "target": f"/admin/content{'?topic=' + topic if topic else ''}",
                    "params": {"section": "admin", "topic": topic}
                },
                "selected_agent": "ui_action",
                "is_final": True
            }
        else:
            return {
                "response_text": "You need admin access to perform this action.",
                "selected_agent": "ui_action",
                "is_final": True
            }

    # Admin navigation actions - guide if no permission
    if action_type == "goto_topic_admin":
        if not has_admin_access:
            return {
                "response_text": "You don't have admin access. Please contact an administrator if you need this permission.",
                "selected_agent": "ui_action",
                "is_final": True
            }

    if action_type == "goto_root":
        if not is_global_admin:
            if has_admin_access:
                return {
                    "response_text": "You have topic admin access but not global admin access. "
                                   "I'll take you to content management instead.",
                    "navigation": {
                        "action": "navigate",
                        "target": f"/admin/content{'?topic=' + topic if topic else ''}",
                        "params": {"section": "admin", "topic": topic}
                    },
                    "selected_agent": "ui_action",
                    "is_final": True
                }
            else:
                return {
                    "response_text": "You need global admin access for system management.",
                    "selected_agent": "ui_action",
                    "is_final": True
                }

    return None
