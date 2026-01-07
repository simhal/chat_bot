"""
Response Builder node for the main chat graph.

This node assembles the final response from the state, ensuring the
response object matches the expected frontend contract.
"""

from typing import Dict, Any, Optional, List
import logging

from agents.state import AgentState

logger = logging.getLogger(__name__)


def response_builder_node(state: AgentState) -> Dict[str, Any]:
    """
    Assemble the final response from state.

    This is the final node before returning to the user. It:
    1. Extracts response components from state
    2. Builds the response object matching frontend contract
    3. Handles any final formatting or validation

    Args:
        state: Current agent state with response components

    Returns:
        Updated state with final_response object
    """
    # Build the response object
    response = _build_response_object(state)

    # Log response for debugging
    logger.info(f"Response built: agent={response.get('agent_type')}, "
               f"has_ui_action={bool(response.get('ui_action'))}, "
               f"has_navigation={bool(response.get('navigation'))}, "
               f"has_confirmation={bool(response.get('confirmation'))}")

    return {
        "final_response": response,
        "is_final": True
    }


def _build_response_object(state: AgentState) -> Dict[str, Any]:
    """
    Build the response object matching the frontend contract.

    Expected response structure:
    {
        response: str,          # Required - text to display
        agent_type: str,        # Which agent handled this
        routing_reason: str,    # Why this routing was chosen
        articles: List[dict],   # Referenced articles
        ui_action: dict,        # UI action to trigger (optional)
        navigation: dict,       # Navigation command (optional)
        editor_content: dict,   # Content for editor (optional)
        confirmation: dict      # HITL confirmation (optional)
    }
    """
    # Required field - response text
    response_text = state.get("response_text", "")
    if not response_text:
        # Try to extract from messages as fallback
        messages = state.get("messages", [])
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, 'content'):
                response_text = last_message.content
            else:
                response_text = str(last_message)

    if not response_text:
        response_text = "I processed your request but have nothing to report."

    # Build response dict
    response: Dict[str, Any] = {
        "response": response_text,
        "agent_type": _get_agent_type(state),
        "routing_reason": state.get("routing_reason", ""),
        "articles": _format_articles(state.get("referenced_articles", []))
    }

    # Add optional fields if present
    ui_action = state.get("ui_action")
    if ui_action:
        response["ui_action"] = _format_ui_action(ui_action)

    navigation = state.get("navigation")
    if navigation:
        response["navigation"] = _format_navigation(navigation)

    editor_content = state.get("editor_content")
    if editor_content:
        response["editor_content"] = _format_editor_content(editor_content)

    confirmation = state.get("confirmation")
    if confirmation:
        response["confirmation"] = _format_confirmation(confirmation)

    return response


def _get_agent_type(state: AgentState) -> str:
    """Get the agent type that handled this request."""
    # Try selected_agent first
    agent_type = state.get("selected_agent")
    if agent_type:
        return agent_type

    # Fall back to intent type
    intent = state.get("intent", {})
    intent_type = intent.get("intent_type")
    if intent_type:
        return intent_type

    return "general"


def _format_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format articles for response."""
    formatted = []
    for article in articles:
        formatted.append({
            "id": article.get("id"),
            "topic": article.get("topic"),
            "headline": article.get("headline"),
            "status": article.get("status"),
            "created_at": article.get("created_at"),
            "author": article.get("author")
        })
    return formatted


def _format_ui_action(ui_action: Dict[str, Any]) -> Dict[str, Any]:
    """Format UI action for response."""
    return {
        "type": ui_action.get("type", "unknown"),
        "params": ui_action.get("params", {})
    }


def _format_navigation(navigation: Dict[str, Any]) -> Dict[str, Any]:
    """Format navigation for response."""
    return {
        "action": navigation.get("action", "navigate"),
        "target": navigation.get("target", "/"),
        "params": navigation.get("params", {})
    }


def _format_editor_content(editor_content: Dict[str, Any]) -> Dict[str, Any]:
    """Format editor content for response."""
    return {
        "headline": editor_content.get("headline", ""),
        "content": editor_content.get("content", ""),
        "keywords": editor_content.get("keywords", ""),
        "article_id": editor_content.get("article_id"),
        "linked_resources": editor_content.get("linked_resources", []),
        "action": editor_content.get("action", "fill"),
        "timestamp": editor_content.get("timestamp", "")
    }


def _format_confirmation(confirmation: Dict[str, Any]) -> Dict[str, Any]:
    """Format HITL confirmation for response."""
    return {
        "id": confirmation.get("id", ""),
        "type": confirmation.get("type", ""),
        "title": confirmation.get("title", "Confirm Action"),
        "message": confirmation.get("message", "Are you sure?"),
        "article_id": confirmation.get("article_id"),
        "confirm_label": confirmation.get("confirm_label", "Confirm"),
        "cancel_label": confirmation.get("cancel_label", "Cancel"),
        "confirm_endpoint": confirmation.get("confirm_endpoint", ""),
        "confirm_method": confirmation.get("confirm_method", "POST"),
        "confirm_body": confirmation.get("confirm_body", {})
    }


def check_hitl_required(state: AgentState) -> str:
    """
    Conditional edge function to check if HITL is required.

    Used by the graph to determine if we should checkpoint for HITL
    or proceed to END.

    Args:
        state: Current agent state

    Returns:
        "hitl" if HITL required, "end" otherwise
    """
    if state.get("requires_hitl"):
        logger.info("HITL required - checkpointing workflow")
        return "hitl"
    return "end"
