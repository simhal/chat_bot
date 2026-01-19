"""
Router node for the main chat graph.

This node classifies user intent using LLM-based classification and determines
which handler node should process the request. Routes messages to:
- ui_action: Navigation and UI interactions
- content_generation: Article creation/editing
- editor_workflow: Editorial actions (approve, reject, review)
- entitlements: Permission queries
- general_chat: General Q&A and conversation

The LLM classifier uses:
- Few-shot examples for consistent classification
- Context awareness (section, topic, user roles)
- OpenAI structured outputs for reliable responses
- Rule-based fallback if LLM fails
"""

from typing import Dict, Any, Optional
import logging

from agents.builds.v1.state import AgentState, IntentClassification, IntentType
from agents.builds.v1.intent_classifier import classify_intent

logger = logging.getLogger(__name__)


def router_node(state: AgentState) -> Dict[str, Any]:
    """
    Classify user intent using LLM and route to appropriate handler node.

    Uses the intent_classifier module for sophisticated LLM-based classification
    with few-shot examples and context awareness.

    Returns:
        Dict with 'intent' (IntentClassification) and 'routing_reason' (str)
    """
    messages = state.get("messages", [])
    if not messages:
        return {
            "intent": IntentClassification(
                intent_type="general_chat",
                confidence=0.0,
                details={"reason": "No messages provided"}
            ),
            "routing_reason": "No messages to process"
        }

    # Get the last user message
    last_message = messages[-1]
    user_message = last_message.content if hasattr(last_message, 'content') else str(last_message)

    # Get context for classification
    nav_context = state.get("navigation_context") or {}
    user_context = state.get("user_context") or {}
    user_scopes = user_context.get("scopes", [])

    # Use LLM-based classification
    intent = classify_intent(
        message=user_message,
        navigation_context=nav_context,
        user_scopes=user_scopes
    )

    logger.info(f"Router: Classified as {intent['intent_type']} "
                f"(confidence: {intent['confidence']:.2f}) - {intent['details'].get('reason', 'N/A')}")

    return {
        "intent": intent,
        "routing_reason": intent["details"].get("reason", "LLM classification"),
        "selected_agent": intent["intent_type"]
    }


def route_by_intent(state: AgentState) -> str:
    """
    Conditional edge function for LangGraph routing.

    Returns the name of the node to route to based on intent classification.
    """
    intent = state.get("intent")

    if not intent:
        logger.warning("Router: No intent in state, defaulting to general_chat")
        return "general_chat"

    intent_type = intent.get("intent_type", "general_chat")

    # Map intent types to node names
    # Note: Navigation is now handled via ui_action for better UX
    route_map: Dict[IntentType, str] = {
        "navigation": "ui_action",  # Redirect to ui_action for navigation
        "ui_action": "ui_action",
        "content_generation": "content_generation",
        "editor_workflow": "editor_workflow",
        "general_chat": "general_chat",
        "entitlements": "entitlements",
    }

    node_name = route_map.get(intent_type, "general_chat")
    logger.info(f"Router: Routing to node '{node_name}' for intent '{intent_type}'")

    return node_name
