"""
Main Chat Graph - Singleton LangGraph implementation.

This module provides a single, reusable chat graph that is built once at startup
and used for all chat requests. This is the correct pattern for LangGraph -
graphs should be compiled once and reused.

Usage:
    from agents.graph import invoke_chat

    response = invoke_chat(
        message="Hello",
        user_context=user_ctx,
        navigation_context=nav_ctx
    )
"""

from typing import Optional, Dict, Any
import logging
import os
import uuid

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage

from agents.state import (
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

    Uses Redis in production (for HITL state persistence across restarts),
    falls back to MemorySaver for development.
    """
    global _CHECKPOINTER
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER

    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            from langgraph.checkpoint.redis import RedisSaver
            # Use from_conn_string factory method for proper initialization
            _CHECKPOINTER = RedisSaver.from_conn_string(redis_url)
            _CHECKPOINTER.setup()  # Initialize Redis indices
            logger.info("Using Redis checkpointer for HITL state persistence")
            return _CHECKPOINTER
        except ImportError as e:
            logger.warning(f"Redis checkpointer not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")

    logger.info("Using in-memory checkpointer")
    _CHECKPOINTER = MemorySaver()
    return _CHECKPOINTER


def _build_graph():
    """
    Build the main chat graph (called ONCE at startup).

    Graph Structure:
        START → router → [handler nodes] → response_builder → END

    Handler nodes are selected based on intent classification:
        - ui_action: Navigation and UI triggers
        - content_generation: Article writing (analyst workflow)
        - editor_workflow: Review/publish (editor workflow)
        - general_chat: Q&A and general queries
        - entitlements: Permission questions
    """
    from agents.nodes import (
        router_node,
        route_by_intent,
        ui_action_node,
        general_chat_node,
        entitlements_node,
        response_builder_node,
    )
    from agents.nodes.content_gen_node import content_generation_node
    from agents.nodes.editor_node import editor_workflow_node

    logger.info("Building main chat graph...")

    # Create graph with AgentState schema
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("router", router_node)
    workflow.add_node("ui_action", ui_action_node)
    workflow.add_node("content_generation", content_generation_node)
    workflow.add_node("editor_workflow", editor_workflow_node)
    workflow.add_node("general_chat", general_chat_node)
    workflow.add_node("entitlements", entitlements_node)
    workflow.add_node("response_builder", response_builder_node)

    # Entry point
    workflow.set_entry_point("router")

    # Conditional routing from router based on intent
    workflow.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "ui_action": "ui_action",
            "content_generation": "content_generation",
            "editor_workflow": "editor_workflow",
            "general_chat": "general_chat",
            "entitlements": "entitlements",
        }
    )

    # All handlers flow to response_builder
    for handler in ["ui_action", "content_generation", "editor_workflow",
                    "general_chat", "entitlements"]:
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
