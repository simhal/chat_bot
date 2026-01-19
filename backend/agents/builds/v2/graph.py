"""
Main Chat Graph - Singleton LangGraph implementation.

This module provides a single, reusable chat graph that is built once at startup
and used for all chat requests. This is the correct pattern for LangGraph -
graphs should be compiled once and reused.

Usage:
    from agents.builds.v2.graph import invoke_chat

    response = invoke_chat(
        message="Hello",
        user_context=user_ctx,
        navigation_context=nav_ctx
    )
"""

from typing import Optional, Dict, Any
import logging
import uuid

from config import settings

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage

from agents.builds.v2.state import (
    AgentState,
    ChatResponse,
    UserContext,
    NavigationContext,
    create_initial_state,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Singleton Instances
# =============================================================================

_GRAPH = None
_CHECKPOINTER = None


def _get_checkpointer():
    """
    Get singleton checkpointer instance.

    Uses MemorySaver for HITL state persistence. With sticky sessions enabled
    on the load balancer, users will be routed to the same backend instance,
    ensuring workflow continuity.

    Note: If the backend restarts, in-flight HITL workflows will be lost.
    This is acceptable for most use cases.
    """
    global _CHECKPOINTER
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER

    logger.info("Using in-memory checkpointer (sticky sessions required for HITL)")
    _CHECKPOINTER = MemorySaver()
    return _CHECKPOINTER


def _build_graph():
    """
    Build the main chat graph (called ONCE at startup).

    Graph Structure:
        START → router → [role nodes] → response_builder → END

    Role-based nodes (selected by nav_context.role):
        - navigation: Page navigation (goto_* actions)
        - user: User profile and permissions
        - reader: Article browsing and search
        - analyst: Content creation (has sub-graphs for article_content and resources)
        - editor: Editorial workflow
        - admin: Administration
        - general_chat: Fallback Q&A
    """
    from agents.builds.v2.nodes import (
        router_node,
        route_by_intent,
        navigation_node,
        general_chat_node,
        response_builder_node,
    )
    from agents.builds.v2.nodes.user_node import user_node
    from agents.builds.v2.nodes.reader_node import reader_node
    from agents.builds.v2.nodes.analyst_node import analyst_node
    from agents.builds.v2.nodes.editor_node import editor_node
    from agents.builds.v2.nodes.admin_node import admin_node

    logger.info("Building main chat graph (role-based)...")

    # Create graph with AgentState schema
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("router", router_node)
    workflow.add_node("navigation", navigation_node)
    workflow.add_node("user", user_node)
    workflow.add_node("reader", reader_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("editor", editor_node)
    workflow.add_node("admin", admin_node)
    workflow.add_node("general_chat", general_chat_node)
    workflow.add_node("response_builder", response_builder_node)

    # Entry point
    workflow.set_entry_point("router")

    # Conditional routing from router based on role and intent
    workflow.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "navigation": "navigation",
            "user": "user",
            "reader": "reader",
            "analyst": "analyst",
            "editor": "editor",
            "admin": "admin",
            "general_chat": "general_chat",
        }
    )

    # All role nodes flow to response_builder
    role_nodes = ["navigation", "user", "reader", "analyst", "editor", "admin", "general_chat"]
    for handler in role_nodes:
        workflow.add_edge(handler, "response_builder")

    # Response builder goes to END
    workflow.add_edge("response_builder", END)

    # Compile with checkpointer
    compiled = workflow.compile(checkpointer=_get_checkpointer())

    logger.info("Main chat graph built successfully")
    return compiled


def get_graph():
    """Get the singleton graph instance, building it if necessary."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


# =============================================================================
# Public API
# =============================================================================

def invoke_chat(
    message: str,
    user_context: UserContext,
    navigation_context: Optional[NavigationContext] = None,
    thread_id: Optional[str] = None,
) -> ChatResponse:
    """
    Invoke the chat graph with a user message.

    This is the SINGLE ENTRY POINT for all chat processing.

    Args:
        message: The user's message
        user_context: Authenticated user context (from JWT)
        navigation_context: Frontend navigation context (optional)
        thread_id: Thread ID for conversation continuity (optional)

    Returns:
        ChatResponse with validated structure

    Example:
        response = invoke_chat(
            message="go to equity",
            user_context=user_ctx,
            navigation_context={"section": "home", "role": "reader"}
        )
        print(response.response)  # "Navigating to equity..."
        print(response.ui_action)  # {"type": "goto_home", "params": {"topic": "equity"}}
    """
    graph = get_graph()

    # Create initial state
    state = create_initial_state(
        user_context=user_context,
        messages=[HumanMessage(content=message)],
        navigation_context=navigation_context,
    )

    # Generate thread ID if not provided
    if not thread_id:
        thread_id = f"chat_{user_context['user_id']}_{uuid.uuid4().hex[:8]}"

    config = {"configurable": {"thread_id": thread_id}}

    logger.info(f"Invoking chat graph: thread={thread_id}, message='{message[:50]}...'")

    try:
        # Invoke graph
        result = graph.invoke(state, config)

        # Build response from state
        response = ChatResponse(
            response=result.get("response_text") or "No response generated",
            agent_type=result.get("selected_agent") or "general",
            routing_reason=result.get("routing_reason") or "",
            articles=result.get("referenced_articles") or [],
            ui_action=result.get("ui_action"),
            navigation=result.get("navigation"),
            editor_content=result.get("editor_content"),
            confirmation=result.get("confirmation"),
        )

        logger.info(f"Chat response: agent={response.agent_type}, "
                   f"has_ui_action={response.ui_action is not None}")

        return response

    except Exception as e:
        logger.exception(f"Chat graph invocation failed: {e}")
        return ChatResponse(
            response=f"I apologize, but I encountered an error: {str(e)}",
            agent_type="error",
            routing_reason=f"Error: {str(e)}",
        )


async def ainvoke_chat(
    message: str,
    user_context: UserContext,
    navigation_context: Optional[NavigationContext] = None,
    thread_id: Optional[str] = None,
) -> ChatResponse:
    """
    Async version of invoke_chat.

    Args:
        message: The user's message
        user_context: Authenticated user context
        navigation_context: Frontend navigation context (optional)
        thread_id: Thread ID for conversation continuity (optional)

    Returns:
        ChatResponse with validated structure
    """
    graph = get_graph()

    state = create_initial_state(
        user_context=user_context,
        messages=[HumanMessage(content=message)],
        navigation_context=navigation_context,
    )

    if not thread_id:
        thread_id = f"chat_{user_context['user_id']}_{uuid.uuid4().hex[:8]}"

    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await graph.ainvoke(state, config)

        return ChatResponse(
            response=result.get("response_text") or "No response generated",
            agent_type=result.get("selected_agent") or "general",
            routing_reason=result.get("routing_reason") or "",
            articles=result.get("referenced_articles") or [],
            ui_action=result.get("ui_action"),
            navigation=result.get("navigation"),
            editor_content=result.get("editor_content"),
            confirmation=result.get("confirmation"),
        )

    except Exception as e:
        logger.exception(f"Async chat graph invocation failed: {e}")
        return ChatResponse(
            response=f"I apologize, but I encountered an error: {str(e)}",
            agent_type="error",
            routing_reason=f"Error: {str(e)}",
        )


def resume_chat(
    thread_id: str,
    hitl_decision: str,
    user_context: UserContext,
) -> ChatResponse:
    """
    Resume a checkpointed workflow after HITL decision.

    Used when a workflow was paused for human approval (e.g., publish confirmation).

    Args:
        thread_id: Thread ID of the paused workflow
        hitl_decision: "approve" or "reject"
        user_context: User context for permission verification

    Returns:
        ChatResponse from resumed workflow
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    logger.info(f"Resuming workflow: thread={thread_id}, decision={hitl_decision}")

    try:
        result = graph.invoke(
            {"hitl_decision": hitl_decision, "user_context": user_context},
            config=config
        )

        return ChatResponse(
            response=result.get("response_text") or "Workflow resumed",
            agent_type=result.get("selected_agent") or "hitl",
            routing_reason=f"HITL decision: {hitl_decision}",
            articles=result.get("referenced_articles") or [],
            ui_action=result.get("ui_action"),
            navigation=result.get("navigation"),
            editor_content=result.get("editor_content"),
            confirmation=result.get("confirmation"),
        )

    except Exception as e:
        logger.exception(f"Workflow resume failed: {e}")
        return ChatResponse(
            response=f"Failed to resume workflow: {str(e)}",
            agent_type="error",
            routing_reason=f"Resume error: {str(e)}",
        )
