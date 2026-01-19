"""
User node for the main chat graph.

This node handles user-related requests:
- Permission/entitlement queries (what can I do, my roles, etc.)
- Profile actions (view/edit profile, settings)
- User preferences (tonality, notifications)

Routes based on nav_context.role == 'user' or intent type == 'entitlements'
"""

from typing import Dict, Any, List
import logging

from agents.builds.v2.state import AgentState

logger = logging.getLogger(__name__)


# Role descriptions for user-friendly explanations
ROLE_DESCRIPTIONS = {
    "admin": {
        "title": "Administrator",
        "description": "Full access to all system features",
        "capabilities": [
            "View all articles across all topics",
            "Create and edit articles in all topics",
            "Review and publish articles in all topics",
            "Delete, deactivate, and recall articles",
            "Manage content and resources",
            "Access admin dashboard"
        ]
    },
    "analyst": {
        "title": "Analyst",
        "description": "Create and edit article content",
        "capabilities": [
            "Create new draft articles",
            "Edit your own drafts",
            "Submit articles for review",
            "Attach resources to articles",
            "View published articles"
        ]
    },
    "editor": {
        "title": "Editor",
        "description": "Review and publish articles",
        "capabilities": [
            "Review articles submitted for publication",
            "Approve or reject articles",
            "Publish articles",
            "Request changes from analysts",
            "View all articles in your topics"
        ]
    },
    "reader": {
        "title": "Reader",
        "description": "View published content",
        "capabilities": [
            "Browse published articles",
            "Search articles",
            "Rate and bookmark articles",
            "Download article PDFs"
        ]
    }
}

# User UI actions and their handlers
USER_UI_ACTIONS = {
    "switch_profile_tab": {"handler": "_handle_switch_profile_tab"},
    "save_tonality": {"handler": "_handle_save_tonality"},
    "delete_account": {"handler": "_handle_delete_account", "destructive": True},
}


def user_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle user-related requests including permissions and profile actions.

    This node:
    1. Determines if this is a permission query or profile action
    2. For permissions: explains user's roles and capabilities
    3. For profile actions: handles profile UI actions

    Args:
        state: Current agent state with messages and context

    Returns:
        Updated state with response explaining permissions or action result
    """
    intent = state.get("intent", {})
    intent_type = intent.get("intent_type", "")
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})
    messages = state.get("messages", [])

    user_query = messages[-1].content.lower() if messages else ""

    # Check for UI action first
    action_type = details.get("action_type", "")
    if action_type in USER_UI_ACTIONS:
        return _handle_user_ui_action(action_type, details, user_context, nav_context)

    # Handle permission/entitlement queries
    if "topic" in user_query or "section" in user_query:
        response = _explain_topic_permissions(user_context)
    elif "action" in user_query or "can i" in user_query or "am i able" in user_query:
        response = _explain_available_actions(user_context, nav_context)
    elif "role" in user_query:
        response = _explain_roles(user_context)
    else:
        # General permissions overview
        response = _explain_all_permissions(user_context)

    return {
        "response_text": response,
        "selected_agent": "user",
        "routing_reason": "User permission/profile query",
        "is_final": True
    }


def _handle_user_ui_action(
    action_type: str,
    details: Dict[str, Any],
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle user-specific UI actions."""

    if action_type == "switch_profile_tab":
        tab = details.get("tab", "profile")
        return {
            "response_text": f"Switching to {tab} tab.",
            "ui_action": {
                "type": action_type,
                "params": {"tab": tab}
            },
            "selected_agent": "user",
            "is_final": True
        }

    elif action_type == "save_tonality":
        return {
            "response_text": "Saving your writing preferences...",
            "ui_action": {
                "type": action_type,
                "params": details
            },
            "selected_agent": "user",
            "is_final": True
        }

    elif action_type == "delete_account":
        # Destructive action - requires confirmation
        import uuid
        confirmation_id = str(uuid.uuid4())
        return {
            "response_text": "Are you sure you want to delete your account? This action cannot be undone.",
            "confirmation": {
                "id": confirmation_id,
                "type": "delete_account",
                "title": "Delete Account",
                "message": "Delete your account? All your data will be permanently removed.",
                "confirm_label": "Delete My Account",
                "cancel_label": "Cancel",
                "confirm_endpoint": "/api/user/account",
                "confirm_method": "DELETE"
            },
            "selected_agent": "user",
            "is_final": True
        }

    return {
        "response_text": f"Unknown user action: {action_type}",
        "selected_agent": "user",
        "is_final": True
    }


def _explain_all_permissions(user_context: Dict[str, Any]) -> str:
    """Provide a complete overview of user's permissions."""
    name = user_context.get("name", "User")
    highest_role = user_context.get("highest_role", "reader")
    topic_roles = user_context.get("topic_roles", {})
    scopes = user_context.get("scopes", [])

    is_global_admin = "global:admin" in scopes

    response_parts = [f"**Your Permissions Overview, {name}**\n"]

    if is_global_admin:
        response_parts.append("**Role:** Global Administrator\n")
        response_parts.append("You have full access to all system features across all topics.\n")
    else:
        role_info = ROLE_DESCRIPTIONS.get(highest_role, ROLE_DESCRIPTIONS["reader"])
        response_parts.append(f"**Overall Role:** {role_info['title']}\n")
        response_parts.append(f"{role_info['description']}\n")

    # Topic-specific permissions
    if topic_roles and not is_global_admin:
        response_parts.append("\n**Topic Permissions:**\n")
        for topic, role in topic_roles.items():
            role_info = ROLE_DESCRIPTIONS.get(role, ROLE_DESCRIPTIONS["reader"])
            response_parts.append(f"- **{topic.replace('_', ' ').title()}:** {role_info['title']}\n")

    # Capabilities
    role_info = ROLE_DESCRIPTIONS.get(highest_role, ROLE_DESCRIPTIONS["reader"])
    response_parts.append("\n**What You Can Do:**\n")
    for capability in role_info["capabilities"]:
        response_parts.append(f"- {capability}\n")

    # Quick navigation suggestions
    response_parts.append("\n**Quick Links:**\n")
    response_parts.append("- Say 'go to analyst hub' to create content\n")
    if highest_role in ["editor", "admin"] or is_global_admin:
        response_parts.append("- Say 'go to editor' to review articles\n")
    if is_global_admin:
        response_parts.append("- Say 'go to admin' for system administration\n")

    return "".join(response_parts)


def _explain_topic_permissions(user_context: Dict[str, Any]) -> str:
    """Explain permissions by topic."""
    topic_roles = user_context.get("topic_roles", {})
    scopes = user_context.get("scopes", [])
    is_global_admin = "global:admin" in scopes

    if is_global_admin:
        return ("As a **Global Administrator**, you have full access to all topics:\n"
                "- Macro Economics\n"
                "- Equity Markets\n"
                "- Fixed Income\n"
                "- ESG\n\n"
                "You can create, edit, review, and publish content in any topic.")

    if not topic_roles:
        return ("You currently don't have topic-specific permissions.\n"
                "You can browse published articles as a reader.\n\n"
                "Contact an administrator if you need analyst or editor access.")

    response_parts = ["**Your Topic Permissions:**\n\n"]

    for topic, role in topic_roles.items():
        topic_name = topic.replace("_", " ").title()
        role_info = ROLE_DESCRIPTIONS.get(role, ROLE_DESCRIPTIONS["reader"])
        response_parts.append(f"**{topic_name}:** {role_info['title']}\n")
        for cap in role_info["capabilities"][:3]:
            response_parts.append(f"  - {cap}\n")
        response_parts.append("\n")

    return "".join(response_parts)


def _explain_available_actions(user_context: Dict[str, Any], nav_context: Dict[str, Any]) -> str:
    """Explain what actions are available in current context."""
    current_section = nav_context.get("section", "home")
    current_role = nav_context.get("role", "reader")
    highest_role = user_context.get("highest_role", "reader")
    is_global_admin = "global:admin" in user_context.get("scopes", [])

    effective_role = current_role
    if is_global_admin:
        effective_role = "admin"
    elif highest_role == "admin":
        effective_role = "admin"

    response_parts = [f"**Available Actions in {current_section.title()}**\n\n"]

    section_actions = {
        "home": [
            "Browse published articles",
            "Search for articles",
            "Rate articles",
            "Download PDFs"
        ],
        "analyst": [
            "Create new articles",
            "Edit draft articles",
            "Submit for review",
            "Attach resources",
            "Switch between editor/preview views"
        ],
        "editor": [
            "Review pending articles",
            "Approve and publish",
            "Reject with feedback",
            "Download PDFs"
        ],
        "admin": [
            "View all articles",
            "Delete/deactivate articles",
            "Recall published articles",
            "Manage resources"
        ],
        "profile": [
            "Update profile settings",
            "Change communication preferences",
            "View account information"
        ]
    }

    actions = section_actions.get(current_section, ["Browse content"])

    for action in actions:
        response_parts.append(f"- {action}\n")

    if effective_role == "admin" and current_section != "admin":
        response_parts.append("\n*As an admin, you can also access the admin panel for more options.*\n")

    return "".join(response_parts)


def _explain_roles(user_context: Dict[str, Any]) -> str:
    """Explain the role hierarchy and what each role means."""
    highest_role = user_context.get("highest_role", "reader")

    response_parts = ["**Role Hierarchy**\n\n"]

    for role_key in ["admin", "editor", "analyst", "reader"]:
        role_info = ROLE_DESCRIPTIONS[role_key]
        marker = " <- *Your role*" if role_key == highest_role else ""
        response_parts.append(f"**{role_info['title']}**{marker}\n")
        response_parts.append(f"{role_info['description']}\n\n")

    response_parts.append("*Higher roles inherit capabilities from lower roles.*")

    return "".join(response_parts)
