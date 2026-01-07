"""
Navigation node for the main chat graph.

This node handles navigation intents - requests to navigate to different
pages or sections of the application. It wraps the existing NavigationHandler
logic for backward compatibility while integrating with the LangGraph workflow.
"""

from typing import Dict, Any, Optional
import logging

from agents.state import AgentState

logger = logging.getLogger(__name__)


# Navigation targets with their routes and descriptions
# Routes use {topic} placeholder for topic-scoped pages
# Topic slugs must be valid URL path parameters (lowercase, hyphens, no spaces)
#
# These routes must match the actual SvelteKit frontend routes
NAVIGATION_TARGETS = {
    # === Public/Home Routes ===
    "home": {
        "route": "/",
        "description": "Main home page with topic selection",
        "requires_auth": True
    },

    # === User Routes (any authenticated user) ===
    "profile": {
        "route": "/profile",
        "description": "User profile and account settings",
        "requires_auth": True
    },

    # === Admin Routes (requires admin role) ===
    "admin": {
        "route": "/admin",
        "description": "Admin dashboard",
        "requires_role": "admin"
    },
    "admin_content": {
        "route": "/admin/content",
        "description": "Content management",
        "requires_role": "admin"
    },
    "admin_global": {
        "route": "/admin/global",
        "description": "Global admin panel for system-wide settings",
        "requires_role": "admin"
    },

    # === Analyst Routes (requires analyst role) ===
    "analyst": {
        "route": "/analyst/{topic}",
        "description": "Analyst hub for drafting articles",
        "requires_role": "analyst",
        "topic_scoped": True
    },
    "analyst_edit": {
        "route": "/analyst/edit/{article_id}",
        "description": "Edit a specific article",
        "requires_role": "analyst",
        "article_scoped": True
    },

    # === Editor Routes (requires editor role) ===
    "editor": {
        "route": "/editor/{topic}",
        "description": "Editor hub for reviewing articles",
        "requires_role": "editor",
        "topic_scoped": True
    },
}

# Topic navigation shortcuts
# Maps topic slugs to keywords that identify them in user messages
TOPIC_SHORTCUTS = {
    "macro": ["macro", "economy", "economics", "economic", "macroeconomic"],
    "equity": ["equity", "equities", "stocks", "stock", "equity-research"],
    "fixed_income": ["fixed income", "bonds", "fixed-income", "debt", "credit"],
    "esg": ["esg", "sustainability", "environmental", "governance", "climate"],
    "technical": ["technical", "tech", "technical analysis", "charts"]
}


def navigation_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle navigation intent by determining the target and building navigation response.

    This node processes navigation requests and returns:
    - A user-friendly response message
    - Navigation metadata for the frontend to execute

    Args:
        state: Current agent state with messages and navigation context

    Returns:
        Updated state with response_text, navigation, and is_final=True
    """
    intent = state.get("intent", {})
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})

    # Get the target from intent details or infer from message
    target = details.get("target", "home")
    messages = state.get("messages", [])
    last_message = messages[-1].content if messages else ""

    # Check for topic-specific navigation
    topic = _extract_topic_from_message(last_message)
    if not topic:
        topic = nav_context.get("topic")

    # Determine the navigation target
    nav_target = _resolve_navigation_target(target, topic, user_context)

    if nav_target.get("error"):
        return {
            "response_text": nav_target["error"],
            "is_final": True,
            "selected_agent": "navigation"
        }

    # Build the response
    route = nav_target["route"]
    description = nav_target.get("description", f"Navigate to {target}")

    # Format response message
    response_text = _build_navigation_response(target, topic, description)

    return {
        "response_text": response_text,
        "navigation": {
            "action": "navigate",
            "target": route,
            "params": {
                "topic": topic,
                "section": target
            }
        },
        "selected_agent": "navigation",
        "routing_reason": f"Navigation to {target}" + (f" ({topic})" if topic else ""),
        "is_final": True
    }


def _extract_topic_from_message(message: str) -> Optional[str]:
    """Extract topic from navigation message."""
    message_lower = message.lower()

    for topic, keywords in TOPIC_SHORTCUTS.items():
        if any(kw in message_lower for kw in keywords):
            return topic

    return None


def _resolve_navigation_target(
    target: str,
    topic: Optional[str],
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Resolve the navigation target to a concrete route.

    Checks permissions and handles topic-scoped navigation.
    """
    # Get user permissions
    scopes = user_context.get("scopes", [])
    highest_role = user_context.get("highest_role", "reader")
    topic_roles = user_context.get("topic_roles", {})

    # Get target config
    target_config = NAVIGATION_TARGETS.get(target)

    if not target_config:
        # Try to match partial target name
        for key, config in NAVIGATION_TARGETS.items():
            if target.lower() in key.lower():
                target_config = config
                target = key
                break

    if not target_config:
        return {
            "route": "/",
            "description": "Navigating to home (target not recognized)"
        }

    # Check role requirements
    required_role = target_config.get("requires_role")
    if required_role:
        # Check if user has required role
        has_role = False

        if required_role == "admin":
            has_role = highest_role == "admin" or "global:admin" in scopes
        elif required_role == "analyst":
            if topic:
                has_role = (
                    topic_roles.get(topic) in ["analyst", "admin"] or
                    highest_role in ["analyst", "admin"] or
                    f"{topic}:analyst" in scopes or
                    "global:admin" in scopes
                )
            else:
                has_role = highest_role in ["analyst", "admin"]
        elif required_role == "editor":
            if topic:
                has_role = (
                    topic_roles.get(topic) in ["editor", "admin"] or
                    highest_role in ["editor", "admin"] or
                    f"{topic}:editor" in scopes or
                    "global:admin" in scopes
                )
            else:
                has_role = highest_role in ["editor", "admin"]

        if not has_role:
            return {
                "error": f"You don't have permission to access {target}. " +
                         f"Required role: {required_role}."
            }

    # Build route with topic if needed
    route = target_config["route"]
    if target_config.get("topic_scoped") and topic:
        route = route.replace("{topic}", topic)
    elif target_config.get("topic_scoped") and not topic:
        # Need topic but none specified - use first available
        available_topics = list(topic_roles.keys())
        if available_topics:
            topic = available_topics[0]
            route = route.replace("{topic}", topic)
        else:
            return {
                "error": f"Please specify a topic to navigate to {target}. " +
                         "For example: 'Go to macro analyst hub'"
            }

    return {
        "route": route,
        "description": target_config["description"],
        "topic": topic
    }


def _build_navigation_response(target: str, topic: Optional[str], description: str) -> str:
    """Build a user-friendly navigation response message."""
    if topic:
        return f"Navigating to {target} for {topic}. {description}"
    return f"Navigating to {target}. {description}"
