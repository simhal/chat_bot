"""
Router node for the main chat graph.

This node routes messages based on:
1. nav_context.section - determines primary role-based node from section name
2. Intent classification - refines routing within role context

Section-based routing (extracts role from section name):
- reader_* sections -> reader_node
- analyst_* sections -> analyst_node
- editor_* sections -> editor_node
- admin_* sections -> admin_node
- root_* sections -> admin_node (global admin)
- user_* sections -> user_node
- home -> general_chat_node (or role-specific if topic selected)

Special routing (overrides section):
- navigation intent -> navigation_node
- entitlements intent -> user_node
- general_chat (no role context) -> general_chat_node
"""

from typing import Dict, Any
import logging

from agents.builds.v2.state import AgentState, IntentClassification, IntentType, SECTION_CONFIG
from agents.builds.v2.intent_classifier import classify_intent
from agents.builds.v2.action_validator import get_role_from_section

logger = logging.getLogger(__name__)


def _extract_role_from_section(section: str) -> str:
    """
    Extract the role from a section name.

    Delegates to action_validator.get_role_from_section for consistency.

    Section names follow patterns like:
    - reader_topic, reader_article -> reader
    - analyst_dashboard, analyst_editor -> analyst
    - editor_dashboard, editor_article -> editor
    - admin_articles, admin_resources -> admin
    - root_users, root_topics -> admin (global admin)
    - user_profile, user_settings -> user
    - home -> reader (default)

    Returns:
        Role string: reader, analyst, editor, admin, or user
    """
    return get_role_from_section(section)


def router_node(state: AgentState) -> Dict[str, Any]:
    """
    Route messages based on role context and intent classification.

    Routing priority:
    1. Navigation intents -> navigation_node
    2. Entitlements intents -> user_node
    3. Role context -> appropriate role node
    4. Fallback -> general_chat

    Returns:
        Dict with 'intent', 'routing_reason', and 'selected_agent'
    """
    messages = state.get("messages", [])
    if not messages:
        return {
            "intent": IntentClassification(
                intent_type="general_chat",
                confidence=0.0,
                details={"reason": "No messages provided"}
            ),
            "routing_reason": "No messages to process",
            "selected_agent": "general_chat"
        }

    # Get the last user message
    last_message = messages[-1]
    user_message = last_message.content if hasattr(last_message, 'content') else str(last_message)

    # Get context
    nav_context = state.get("navigation_context") or {}
    user_context = state.get("user_context") or {}
    user_scopes = user_context.get("scopes", [])

    # Extract role from section name (new system uses section names like reader_topic, analyst_dashboard)
    current_section = nav_context.get("section", "home")
    current_role = _extract_role_from_section(current_section)

    # Classify intent using LLM
    intent = classify_intent(
        message=user_message,
        navigation_context=nav_context,
        user_scopes=user_scopes
    )

    intent_type = intent.get("intent_type", "general_chat")
    intent_details = intent.get("details", {})

    logger.info(f"Router: intent={intent_type}, section={current_section}, role={current_role}, "
                f"confidence={intent['confidence']:.2f}")

    # Determine target node based on intent and role
    target_node = _determine_target_node(intent_type, current_role, intent)

    logger.info(f"Router: Routing to '{target_node}' (section={current_section}, role={current_role}, intent={intent_type})")

    return {
        "intent": intent,
        "routing_reason": f"Section: {current_section}, Role: {current_role}, Intent: {intent_type}",
        "selected_agent": target_node
    }


def _determine_target_node(
    intent_type: str,
    current_role: str,
    intent: Dict[str, Any]
) -> str:
    """
    Determine target node based on intent and role.

    Priority:
    1. Navigation intent -> navigation (ALWAYS, regardless of current section)
       This ensures users can navigate via chat from ANY page.
    2. Entitlements intent -> user
    3. Role-based routing (from current section)
    4. Intent-based fallback

    Key Design: Navigation is checked FIRST before role-based routing.
    A user in analyst_editor saying "go home" should route to navigation,
    not to analyst node.
    """
    # PRIORITY 1: Navigation ALWAYS goes to navigation node
    # This is critical - users should be able to navigate via chat from anywhere
    # Check both intent_type == "navigation" AND ui_action with goto action
    if intent_type == "navigation":
        return "navigation"

    # ui_action with goto action is also navigation
    # Note: intent classifier stores action as "action_type" in details for ui_action intents
    if intent_type == "ui_action":
        details = intent.get("details", {})
        action = details.get("action_type") or details.get("action") or intent.get("action")
        if action == "goto" or (action and action.startswith("goto_")):
            return "navigation"

    # Entitlements/permissions go to user node
    if intent_type == "entitlements":
        return "user"

    # Profile section goes to user node
    if current_role == "user" or current_role == "profile":
        return "user"

    # Role-based routing
    role_node_map = {
        "reader": "reader",
        "analyst": "analyst",
        "editor": "editor",
        "admin": "admin",
    }

    if current_role in role_node_map:
        return role_node_map[current_role]

    # Intent-based fallback for unknown roles
    intent_node_map = {
        "ui_action": "reader",  # Default UI actions to reader
        "content_generation": "analyst",
        "editor_workflow": "editor",
        "general_chat": "general_chat",
    }

    return intent_node_map.get(intent_type, "general_chat")


def route_by_intent(state: AgentState) -> str:
    """
    Conditional edge function for LangGraph routing.

    Returns the name of the node to route to based on selected_agent.
    """
    selected_agent = state.get("selected_agent")

    if not selected_agent:
        # Fallback: check intent
        intent = state.get("intent", {})
        intent_type = intent.get("intent_type", "general_chat")
        nav_context = state.get("navigation_context", {})
        current_section = nav_context.get("section", "home")
        current_role = _extract_role_from_section(current_section)

        selected_agent = _determine_target_node(intent_type, current_role, intent)
        logger.warning(f"Router: No selected_agent, determined as '{selected_agent}' (section={current_section})")

    # Valid node names
    valid_nodes = {
        "navigation", "user", "reader", "analyst", "editor", "admin", "general_chat"
    }

    if selected_agent not in valid_nodes:
        logger.warning(f"Router: Unknown agent '{selected_agent}', defaulting to general_chat")
        return "general_chat"

    logger.info(f"Router: Routing to node '{selected_agent}'")
    return selected_agent
