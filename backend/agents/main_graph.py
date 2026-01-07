"""
Main Chat Graph builder using LangGraph.

This module builds the primary chat workflow as a LangGraph StateGraph.
The graph routes user messages through appropriate handler nodes based
on intent classification, with support for:

- Sub-graph delegation for complex workflows (Analyst, Editor)
- HITL (Human-in-the-Loop) via interrupt_before and checkpointing
- Dynamic topic routing from database
- Redis-based state persistence for production
- Celery integration for background processing

Graph Structure:

                        START
                          │
                          ▼
                   ┌─────────────┐
                   │ Router Node │ (Intent Classification)
                   └──────┬──────┘
                          │
        Conditional edges based on intent_type
                          │
    ┌─────────┬───────────┼───────────┬─────────┬────────────┐
    ▼         ▼           ▼           ▼         ▼            ▼
┌───────┐ ┌───────┐ ┌───────────┐ ┌───────┐ ┌───────┐ ┌──────────┐
│Navigat│ │UI     │ │Content Gen│ │Editor │ │General│ │Entitle-  │
│  ion  │ │Action │ │(Analyst   │ │Work-  │ │Chat   │ │ments     │
│ Node  │ │ Node  │ │SubGraph)  │ │flow   │ │Node   │ │Node      │
└───┬───┘ └───┬───┘ └─────┬─────┘ └───┬───┘ └───┬───┘ └────┬─────┘
    │         │           │           │         │          │
    │         │           │     [interrupt      │          │
    │         │           │      for HITL]      │          │
    │         │           │           │         │          │
    └─────────┴───────────┴─────┬─────┴─────────┴──────────┘
                                │
                                ▼
                       ┌────────────────┐
                       │Response Builder│
                       └────────┬───────┘
                                │
                  ┌─────────────┼─────────────┐
                  ▼             ▼             ▼
             ┌─────────┐ ┌──────────┐    ┌────┐
             │Checkpoint│ │Continue │    │END │
             │(HITL)   │ │(iterate)│    │    │
             └─────────┘ └──────────┘   └────┘

LangGraph Features Demonstrated:
- StateGraph with TypedDict schemas
- Conditional edges with routing functions
- Checkpointing for conversation persistence
- interrupt_before for HITL workflows
- Sub-graph composition
- State reducers for accumulating results
"""

from typing import Optional, Dict, Any, Literal, List
import logging
import os
import uuid

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agents.state import (
    AgentState,
    create_initial_state,
    UserContext,
    NavigationContext
)
from agents.nodes import (
    router_node,
    route_by_intent,
    navigation_node,
    ui_action_node,
    content_generation_node,
    editor_workflow_node,
    general_chat_node,
    entitlements_node,
    response_builder_node
)
from agents.nodes.response_builder import check_hitl_required

logger = logging.getLogger(__name__)


# ============================================================================
# Enhanced Nodes with Sub-Graph Integration
# ============================================================================

def content_generation_with_subgraph(state: AgentState) -> Dict[str, Any]:
    """
    Content generation node that delegates to AnalystSubGraph.

    This node demonstrates sub-graph composition in LangGraph - instead of
    a simple function, it invokes a full sub-graph for the research workflow.
    """
    from agents.analyst_subgraph import run_analyst_workflow

    intent = state.get("intent", {})
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})
    messages = state.get("messages", [])

    # Get query from message
    query = messages[-1].content if messages else ""

    # Determine topic
    topic = details.get("topic") or nav_context.get("topic")
    if not topic:
        # Try to infer from query
        from agents.topic_manager import TopicManager
        from database import SessionLocal
        db = SessionLocal()
        try:
            manager = TopicManager(db)
            topic = manager.infer_topic_from_message(query)
        finally:
            db.close()

    if not topic:
        return {
            "response_text": "Which topic would you like to write about? "
                           "Please specify: macro, equity, fixed_income, or esg.",
            "selected_agent": "content_generation",
            "is_final": True
        }

    # Get article context
    article_id = details.get("article_id") or nav_context.get("article_id")

    # Check if we should use Celery for heavy research
    use_celery = os.getenv("USE_CELERY_FOR_RESEARCH", "false").lower() == "true"

    # Run the analyst sub-graph
    result = run_analyst_workflow(
        query=query,
        topic=topic,
        user_context=user_context,
        article_id=article_id,
        use_celery=use_celery
    )

    if result.get("async"):
        # Task queued on Celery
        return {
            "response_text": f"Research task queued. You'll be notified when complete.\n\n"
                           f"**Task ID:** `{result.get('task_id')}`",
            "async_task": {
                "task_id": result.get("task_id"),
                "task_type": "analyst_research"
            },
            "selected_agent": "content_generation",
            "is_final": True
        }

    if not result.get("success"):
        return {
            "response_text": f"Content generation failed: {result.get('error')}",
            "selected_agent": "content_generation",
            "error": result.get("error"),
            "is_final": True
        }

    # Build success response
    word_count = len(result.get("content", "").split())
    headline = result.get("headline", "Untitled")
    article_id = result.get("article_id")
    sources = result.get("sources", {})

    response = f"""I've generated content for {topic}.

**Headline:** {headline}
**Word count:** ~{word_count} words
**Article ID:** #{article_id}

**Sources used:**
- Existing articles: {sources.get('existing_articles', 0)}
- Resources: {sources.get('resources', 0)}
- Web results: {sources.get('web_results', 0)}
- Data sources: {sources.get('data_sources', 0)}

The content has been saved. You can review and edit it in the editor."""

    return {
        "response_text": response,
        "editor_content": {
            "headline": headline,
            "content": result.get("content", ""),
            "keywords": result.get("keywords", ""),
            "article_id": article_id,
            "linked_resources": result.get("linked_resources", []),
            "action": "fill"
        },
        "navigation": {
            "action": "navigate",
            "target": f"/analyst/{topic}",
            "params": {"topic": topic, "article_id": article_id}
        } if not article_id else None,
        "selected_agent": "content_generation",
        "routing_reason": f"Content generation for {topic}",
        "is_final": True
    }


def editor_workflow_with_subgraph(state: AgentState) -> Dict[str, Any]:
    """
    Editor workflow node that delegates to EditorSubGraph.

    This node demonstrates HITL (Human-in-the-Loop) with LangGraph -
    the workflow can be paused and resumed after human approval.
    """
    from agents.editor_subgraph import run_editor_workflow, resume_editor_workflow

    intent = state.get("intent", {})
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})
    messages = state.get("messages", [])

    # Check if this is an HITL resume
    hitl_decision = state.get("hitl_decision")
    thread_id = state.get("_editor_thread_id")

    if hitl_decision and thread_id:
        # Get checkpointer for resume (don't store in state - not serializable)
        checkpointer = get_default_checkpointer()
        result = resume_editor_workflow(
            thread_id=thread_id,
            hitl_decision=hitl_decision,
            user_context=user_context,
            checkpointer=checkpointer
        )
    else:
        # Determine action
        action = details.get("action", "review")
        message = messages[-1].content if messages else ""

        # Infer action from message if needed
        message_lower = message.lower()
        if any(w in message_lower for w in ["approve", "publish"]):
            action = "approve"
        elif any(w in message_lower for w in ["reject", "send back"]):
            action = "reject"
        elif any(w in message_lower for w in ["pending", "queue", "list"]):
            action = "list_pending"

        # Get article context
        topic = details.get("topic") or nav_context.get("topic")
        article_id = details.get("article_id") or nav_context.get("article_id")

        if not article_id and action != "list_pending":
            return {
                "response_text": f"Which article would you like to {action}? "
                               "Please specify an article ID.",
                "selected_agent": "editor_workflow",
                "is_final": True
            }

        # Extract rejection notes if rejecting
        rejection_notes = None
        if action == "reject":
            # Extract notes from message
            for prefix in ["reject ", "send back ", "because ", "the article "]:
                if prefix in message_lower:
                    idx = message_lower.index(prefix) + len(prefix)
                    rejection_notes = message[idx:].strip()
                    break

        # Run the editor sub-graph
        result = run_editor_workflow(
            article_id=article_id or 0,
            action=action,
            user_context=user_context,
            topic=topic,
            rejection_notes=rejection_notes
        )

    # Handle result
    if result.get("status") == "awaiting_confirmation":
        # HITL pause - workflow will be resumed after confirmation
        return {
            "response_text": result.get("response_text"),
            "confirmation": {
                "id": result.get("confirmation_id"),
                "type": "publish_approval",
                "thread_id": result.get("thread_id"),
                "article_id": result.get("article_id"),
                "title": "Publish Article",
                "message": result.get("response_text"),
                "confirm_label": "Publish Now",
                "cancel_label": "Cancel"
            },
            "requires_hitl": True,
            "_editor_thread_id": result.get("thread_id"),
            "selected_agent": "editor_workflow",
            "is_final": False  # NOT final - waiting for HITL
        }

    if result.get("status") == "error":
        return {
            "response_text": result.get("response_text") or f"Error: {result.get('error')}",
            "selected_agent": "editor_workflow",
            "error": result.get("error"),
            "is_final": True
        }

    # Success
    return {
        "response_text": result.get("response_text", "Action completed."),
        "ui_action": result.get("ui_action"),
        "selected_agent": "editor_workflow",
        "is_final": True
    }


# ============================================================================
# Graph Builder
# ============================================================================

def build_main_chat_graph(
    checkpointer: Optional[Any] = None,
    interrupt_before: Optional[List[str]] = None,
    use_subgraphs: bool = True
) -> StateGraph:
    """
    Build the main chat LangGraph workflow.

    This creates a compiled StateGraph with:
    - Router node for intent classification
    - Handler nodes for each intent type
    - Sub-graph integration for complex workflows
    - Response builder for final assembly
    - Optional checkpointing for HITL workflows

    Args:
        checkpointer: Optional LangGraph checkpointer for state persistence
        interrupt_before: Optional list of nodes to interrupt before (for HITL)
        use_subgraphs: Whether to use sub-graphs for analyst/editor (True for showcase)

    Returns:
        Compiled LangGraph
    """
    logger.info("Building main chat graph...")

    # Create graph with AgentState schema
    workflow = StateGraph(AgentState)

    # === Add Nodes ===

    # Router node - classifies intent and routes
    workflow.add_node("router", router_node)

    # Handler nodes - choose implementation based on flag
    workflow.add_node("navigation", navigation_node)
    workflow.add_node("ui_action", ui_action_node)

    if use_subgraphs:
        # Use sub-graph versions for full LangGraph showcase
        workflow.add_node("content_generation", content_generation_with_subgraph)
        workflow.add_node("editor_workflow", editor_workflow_with_subgraph)
        logger.info("Using sub-graph implementations for content_generation and editor_workflow")
    else:
        # Use simpler node implementations
        workflow.add_node("content_generation", content_generation_node)
        workflow.add_node("editor_workflow", editor_workflow_node)
        logger.info("Using simple node implementations")

    workflow.add_node("general_chat", general_chat_node)
    workflow.add_node("entitlements", entitlements_node)

    # Response builder - assembles final response
    workflow.add_node("response_builder", response_builder_node)

    # === Set Entry Point ===
    workflow.set_entry_point("router")

    # === Add Conditional Routing from Router ===
    workflow.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "navigation": "navigation",
            "ui_action": "ui_action",
            "content_generation": "content_generation",
            "editor_workflow": "editor_workflow",
            "general_chat": "general_chat",
            "entitlements": "entitlements",
        }
    )

    # === Add Edges from Handlers to Response Builder ===
    for handler in ["navigation", "ui_action", "content_generation",
                    "editor_workflow", "general_chat", "entitlements"]:
        workflow.add_edge(handler, "response_builder")

    # === Add Conditional Edge from Response Builder ===
    # Check if HITL is required - if so, the graph will checkpoint
    workflow.add_conditional_edges(
        "response_builder",
        check_hitl_required,
        {
            "hitl": END,  # Will checkpoint for HITL
            "end": END,   # Normal completion
        }
    )

    # === Compile Graph ===
    compile_kwargs = {}

    if checkpointer:
        compile_kwargs["checkpointer"] = checkpointer
        logger.info("Graph compiled with checkpointer for HITL support")

    if interrupt_before:
        compile_kwargs["interrupt_before"] = interrupt_before
        logger.info(f"Graph configured to interrupt before: {interrupt_before}")

    compiled = workflow.compile(**compile_kwargs)

    logger.info("Main chat graph built successfully")
    return compiled


def get_default_checkpointer():
    """
    Get the default checkpointer for the graph.

    Uses Redis in production, MemorySaver for development.
    """
    redis_url = os.getenv("REDIS_URL")

    if redis_url:
        try:
            # Try to use Redis checkpointer
            from langgraph.checkpoint.redis import RedisSaver
            checkpointer = RedisSaver.from_conn_string(redis_url)
            logger.info("Using Redis checkpointer for HITL state persistence")
            return checkpointer
        except ImportError:
            logger.warning("Redis checkpointer not available, using memory")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}, using memory")

    # Fallback to in-memory
    logger.info("Using in-memory checkpointer (HITL state will not persist across restarts)")
    return MemorySaver()


# ============================================================================
# Main Graph Wrapper Class
# ============================================================================

class MainChatGraph:
    """
    Wrapper class for the main chat graph.

    Provides a high-level interface for invoking the graph with
    proper state initialization and response extraction.

    LangGraph Features Demonstrated:
    - Graph compilation with configuration
    - Thread-based state management
    - Checkpointing for conversation persistence
    - HITL (Human-in-the-Loop) resume
    - Async invocation support
    """

    def __init__(
        self,
        user_context: UserContext,
        checkpointer: Optional[Any] = None,
        enable_hitl: bool = True,
        use_subgraphs: bool = True
    ):
        """
        Initialize the main chat graph.

        Args:
            user_context: User context from authentication
            checkpointer: Optional checkpointer (defaults to auto-detected)
            enable_hitl: Whether to enable HITL interrupts
            use_subgraphs: Whether to use sub-graphs for complex workflows
        """
        self.user_context = user_context
        self.checkpointer = checkpointer or get_default_checkpointer()
        self.enable_hitl = enable_hitl
        self.use_subgraphs = use_subgraphs

        # Build the graph
        interrupt_before = ["editor_workflow"] if enable_hitl else None
        self.graph = build_main_chat_graph(
            checkpointer=self.checkpointer,
            interrupt_before=interrupt_before,
            use_subgraphs=use_subgraphs
        )

        logger.info(f"MainChatGraph initialized: hitl={enable_hitl}, subgraphs={use_subgraphs}")

    def invoke(
        self,
        message: str,
        navigation_context: Optional[NavigationContext] = None,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Invoke the chat graph with a user message.

        Args:
            message: The user's message
            navigation_context: Frontend navigation context
            thread_id: Optional thread ID for conversation continuity

        Returns:
            Response dict matching frontend contract:
            {
                "response": str,
                "agent_type": str,
                "routing_reason": str,
                "articles": List[Dict],
                "ui_action": Optional[Dict],
                "navigation": Optional[Dict],
                "editor_content": Optional[Dict],
                "confirmation": Optional[Dict]
            }
        """
        from langchain_core.messages import HumanMessage

        # Create initial state
        state = create_initial_state(
            user_context=self.user_context,
            messages=[HumanMessage(content=message)],
            navigation_context=navigation_context
        )

        # Generate thread ID if not provided
        if not thread_id:
            thread_id = str(uuid.uuid4())

        # Build config with thread ID
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(f"Invoking graph: thread={thread_id}, message='{message[:50]}...'")

        # Invoke graph
        try:
            final_state = self.graph.invoke(state, config)

            # Handle None final_state (shouldn't happen but safety check)
            if final_state is None:
                logger.error("Graph invoke returned None state")
                return {
                    "response": "Graph execution returned no state",
                    "agent_type": "error",
                    "routing_reason": "Graph returned None state"
                }

            # Extract response
            response = final_state.get("final_response", {
                "response": "No response generated",
                "agent_type": "error",
                "routing_reason": "Graph completed without response"
            })

            # Add thread_id to response for HITL tracking
            if final_state.get("requires_hitl"):
                response["thread_id"] = thread_id

            return response

        except Exception as e:
            logger.exception(f"Graph invocation failed: {e}")
            return {
                "response": f"I apologize, but I encountered an error: {str(e)}",
                "agent_type": "error",
                "routing_reason": f"Error: {str(e)}"
            }

    async def ainvoke(
        self,
        message: str,
        navigation_context: Optional[NavigationContext] = None,
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Async version of invoke.

        Args:
            message: The user's message
            navigation_context: Frontend navigation context
            thread_id: Optional thread ID for conversation continuity

        Returns:
            Response dict matching frontend contract
        """
        from langchain_core.messages import HumanMessage

        # Create initial state
        state = create_initial_state(
            user_context=self.user_context,
            messages=[HumanMessage(content=message)],
            navigation_context=navigation_context
        )

        # Generate thread ID if not provided
        if not thread_id:
            thread_id = str(uuid.uuid4())

        # Build config with thread ID
        config = {"configurable": {"thread_id": thread_id}}

        # Invoke graph asynchronously
        try:
            final_state = await self.graph.ainvoke(state, config)

            # Extract response
            response = final_state.get("final_response", {
                "response": "No response generated",
                "agent_type": "error",
                "routing_reason": "Graph completed without response"
            })

            # Add thread_id to response for HITL tracking
            if final_state.get("requires_hitl"):
                response["thread_id"] = thread_id

            return response

        except Exception as e:
            logger.exception(f"Async graph invocation failed: {e}")
            return {
                "response": f"I apologize, but I encountered an error: {str(e)}",
                "agent_type": "error",
                "routing_reason": f"Error: {str(e)}"
            }

    def resume(
        self,
        thread_id: str,
        hitl_decision: str
    ) -> Dict[str, Any]:
        """
        Resume a checkpointed workflow after HITL decision.

        This is the key LangGraph feature for Human-in-the-Loop:
        1. The workflow was paused at a checkpoint (interrupt_before)
        2. The human made a decision (approve/reject)
        3. We resume the workflow with their decision

        Args:
            thread_id: Thread ID of the paused workflow
            hitl_decision: "approve" or "reject"

        Returns:
            Response dict from resumed workflow
        """
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(f"Resuming workflow: thread={thread_id}, decision={hitl_decision}")

        try:
            # Resume with HITL decision
            final_state = self.graph.invoke(
                {"hitl_decision": hitl_decision},
                config=config
            )

            return final_state.get("final_response", {
                "response": "Workflow resumed",
                "agent_type": "hitl",
                "routing_reason": f"HITL decision: {hitl_decision}"
            })

        except Exception as e:
            logger.exception(f"Workflow resume failed: {e}")
            return {
                "response": f"Failed to resume workflow: {str(e)}",
                "agent_type": "error",
                "routing_reason": f"Resume error: {str(e)}"
            }

    def get_workflow_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the current state of a workflow.

        Useful for checking if a workflow is paused for HITL.

        Args:
            thread_id: Thread ID of the workflow

        Returns:
            Current workflow state or None if not found
        """
        config = {"configurable": {"thread_id": thread_id}}

        try:
            state = self.graph.get_state(config)
            if state and state.values:
                return {
                    "status": "paused" if state.values.get("requires_hitl") else "running",
                    "agent": state.values.get("selected_agent"),
                    "confirmation": state.values.get("confirmation")
                }
            return None
        except Exception as e:
            logger.warning(f"Failed to get workflow state: {e}")
            return None


# ============================================================================
# Convenience Functions
# ============================================================================

def create_chat_graph(user_context: UserContext) -> MainChatGraph:
    """
    Create a MainChatGraph with default settings.

    This is the primary entry point for using the chat system.

    Args:
        user_context: User context from authentication

    Returns:
        Configured MainChatGraph instance
    """
    return MainChatGraph(
        user_context=user_context,
        checkpointer=get_default_checkpointer(),
        enable_hitl=True,
        use_subgraphs=True
    )
