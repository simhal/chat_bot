"""
Editor Sub-Graph for article review and publishing with HITL.

This module implements a proper LangGraph StateGraph for the editor workflow,
showcasing LangGraph's Human-in-the-Loop (HITL) features including:
- interrupt_before: Pauses workflow before destructive actions
- Checkpointing: Persists state during HITL wait via Redis
- Resume: Continues workflow after human decision
- Conditional edges: Routes based on action type

The graph structure:
                    START
                      │
                      ▼
               ┌─────────────┐
               │Action Parser│
               └──────┬──────┘
                      │
                      ▼
               ┌─────────────┐
               │ Permission  │
               │   Check     │
               └──────┬──────┘
                      │
    ┌─────────────────┼─────────────────┐
    │                 │                 │
    ▼                 ▼                 ▼
┌────────┐     ┌───────────┐     ┌──────────┐
│ Review │     │  Reject   │     │ Approve  │
│ Article│     │  Article  │     │ (HITL)   │
└────┬───┘     └─────┬─────┘     └────┬─────┘
    │                 │                │
    │                 │         [interrupt_before]
    │                 │                │
    │                 │                ▼
    │                 │         ┌──────────┐
    │                 │         │  Publish │
    │                 │         │ Execute  │
    │                 │         └────┬─────┘
    │                 │                │
    └─────────────────┼────────────────┘
                      │
                      ▼
               ┌─────────────┐
               │  Response   │
               │   Builder   │
               └──────┬──────┘
                      │
                      ▼
                     END
"""

import os
import logging
import uuid
from typing import Dict, Any, Optional, List, Literal, TypedDict
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)


# ============================================================================
# Editor-specific State Schema
# ============================================================================

class EditorState(TypedDict, total=False):
    """State schema for the editor workflow."""
    # Input
    article_id: int
    topic: Optional[str]
    action: Literal["review", "approve", "reject", "list_pending"]
    rejection_notes: Optional[str]
    editor_notes: Optional[str]
    user_context: Dict[str, Any]
    conversation_history: List[Dict[str, str]]  # Previous messages for context

    # Permission check
    permission_granted: bool
    permission_error: Optional[str]

    # Article data
    article_data: Optional[Dict[str, Any]]
    ai_review: Optional[str]

    # HITL state
    requires_confirmation: bool
    confirmation_id: Optional[str]
    hitl_decision: Optional[Literal["approve", "reject"]]

    # Output
    response_text: Optional[str]
    new_status: Optional[str]
    ui_action: Optional[Dict[str, Any]]

    # Control flow
    error: Optional[str]
    is_complete: bool


def create_editor_state(
    article_id: int,
    action: str,
    user_context: Dict[str, Any],
    topic: Optional[str] = None,
    rejection_notes: Optional[str] = None,
    editor_notes: Optional[str] = None,
    hitl_decision: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> EditorState:
    """Create initial editor state."""
    return EditorState(
        article_id=article_id,
        topic=topic,
        action=action,
        rejection_notes=rejection_notes,
        editor_notes=editor_notes,
        user_context=user_context,
        conversation_history=conversation_history or [],
        permission_granted=False,
        permission_error=None,
        article_data=None,
        ai_review=None,
        requires_confirmation=False,
        confirmation_id=None,
        hitl_decision=hitl_decision,
        response_text=None,
        new_status=None,
        ui_action=None,
        error=None,
        is_complete=False
    )


# ============================================================================
# Node Functions
# ============================================================================

def action_parser_node(state: EditorState) -> Dict[str, Any]:
    """
    Parse and validate the editor action.
    """
    action = state.get("action", "review")
    article_id = state.get("article_id")

    if not article_id:
        return {
            "error": "Article ID is required",
            "is_complete": True
        }

    if action not in ["review", "approve", "reject", "list_pending"]:
        return {
            "error": f"Unknown action: {action}",
            "is_complete": True
        }

    logger.info(f"📋 Editor action: {action} for article #{article_id}")
    return {}


def permission_check_node(state: EditorState) -> Dict[str, Any]:
    """
    Check if user has editor permission for the topic.
    """
    user_context = state.get("user_context", {})
    article_id = state.get("article_id")

    try:
        from models import ContentArticle
        from database import SessionLocal

        db = SessionLocal()
        try:
            article = db.query(ContentArticle).filter(
                ContentArticle.id == article_id
            ).first()

            if not article:
                return {
                    "error": f"Article #{article_id} not found",
                    "is_complete": True
                }

            topic = article.topic_slug

            from agents.permission_utils import check_topic_permission
            allowed, error_msg = check_topic_permission(topic, "editor", user_context)

            if not allowed:
                logger.warning(f"🚫 Editor permission denied for topic {topic}")
                return {
                    "permission_granted": False,
                    "permission_error": error_msg,
                    "is_complete": True
                }

            # Store article data for later use
            logger.info(f"✅ Editor permission granted for topic {topic}")
            return {
                "permission_granted": True,
                "topic": topic,
                "article_data": {
                    "id": article.id,
                    "headline": article.headline,
                    "topic": topic,
                    "status": article.status.value if article.status else "unknown",
                    "author": article.author,
                }
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Permission check failed: {e}")
        return {
            "error": str(e),
            "is_complete": True
        }


def review_article_node(state: EditorState) -> Dict[str, Any]:
    """
    Generate AI-powered review of the article.
    """
    article_id = state.get("article_id")
    user_context = state.get("user_context", {})
    article_data = state.get("article_data", {})

    try:
        from agents.editor_sub_agent import EditorSubAgent
        from database import SessionLocal

        db = SessionLocal()
        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0.3,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            agent = EditorSubAgent(llm=llm, db=db)
            result = agent.review_article(
                article_id=article_id,
                user_context=user_context
            )

            if not result.get("success"):
                return {
                    "error": result.get("error"),
                    "is_complete": True
                }

            ai_review = result.get("ai_review", {})
            review_text = ai_review.get("review", "No AI review available.")

            response = f"""**Editorial Review - Article #{article_id}**

**Headline:** {article_data.get('headline', 'Unknown')}
**Topic:** {article_data.get('topic', 'Unknown')}
**Status:** {article_data.get('status', 'Unknown')}
**Author:** {article_data.get('author', 'Unknown')}

---

{review_text}

---

Use **approve** to publish or **reject** to send back with feedback."""

            logger.info(f"📝 Generated review for article #{article_id}")

            return {
                "ai_review": review_text,
                "response_text": response,
                "ui_action": {
                    "type": "view_article",
                    "params": {"article_id": article_id}
                },
                "is_complete": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Review failed: {e}")
        return {
            "error": str(e),
            "is_complete": True
        }


def reject_article_node(state: EditorState) -> Dict[str, Any]:
    """
    Reject article and return to draft status.
    """
    article_id = state.get("article_id")
    user_context = state.get("user_context", {})
    rejection_notes = state.get("rejection_notes", "")

    if not rejection_notes:
        return {
            "response_text": f"Please provide feedback for rejecting article #{article_id}. "
                           "What changes should the author make?",
            "is_complete": True
        }

    try:
        from agents.editor_sub_agent import EditorSubAgent
        from database import SessionLocal

        db = SessionLocal()
        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            agent = EditorSubAgent(llm=llm, db=db)
            result = agent.request_changes(
                article_id=article_id,
                user_context=user_context,
                notes=rejection_notes
            )

            if not result.get("success"):
                return {
                    "error": result.get("error"),
                    "is_complete": True
                }

            logger.info(f"❌ Article #{article_id} rejected")

            return {
                "new_status": result.get("new_status", "draft"),
                "response_text": f"""Article #{article_id} has been sent back to the author for revisions.

**Status:** {result.get('new_status', 'draft')}

**Your feedback:**
{rejection_notes}

The author will be notified of the requested changes.""",
                "ui_action": {
                    "type": "article_rejected",
                    "params": {
                        "article_id": article_id,
                        "new_status": result.get("new_status"),
                        "notes": rejection_notes
                    }
                },
                "is_complete": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Rejection failed: {e}")
        return {
            "error": str(e),
            "is_complete": True
        }


def approve_prepare_node(state: EditorState) -> Dict[str, Any]:
    """
    Prepare for approval - this triggers HITL interrupt.

    This node sets up the confirmation and triggers LangGraph's
    interrupt_before mechanism.
    """
    article_id = state.get("article_id")
    topic = state.get("topic")
    article_data = state.get("article_data", {})

    confirmation_id = str(uuid.uuid4())

    logger.info(f"⏸️ HITL: Awaiting approval for article #{article_id}")

    return {
        "requires_confirmation": True,
        "confirmation_id": confirmation_id,
        "response_text": f"""Ready to publish article #{article_id}?

**Headline:** {article_data.get('headline', 'Unknown')}
**Topic:** {topic}

This will make the article visible to all readers. Please confirm to proceed.""",
        # Note: is_complete stays False - workflow pauses here
    }


def publish_execute_node(state: EditorState) -> Dict[str, Any]:
    """
    Execute the publish action after HITL approval.

    This node only runs after the workflow is resumed with an approval decision.
    """
    article_id = state.get("article_id")
    user_context = state.get("user_context", {})
    hitl_decision = state.get("hitl_decision")

    if hitl_decision != "approve":
        logger.info(f"📋 Publication cancelled for article #{article_id}")
        return {
            "response_text": f"Publication cancelled. Article #{article_id} remains in the review queue.",
            "ui_action": {
                "type": "publication_cancelled",
                "params": {"article_id": article_id}
            },
            "is_complete": True
        }

    try:
        from agents.editor_sub_agent import EditorSubAgent
        from database import SessionLocal

        db = SessionLocal()
        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            agent = EditorSubAgent(llm=llm, db=db)
            result = agent.process_approval(
                article_id=article_id,
                approved=True,
                user_context=user_context,
                review_notes="Approved via chat workflow"
            )

            if not result.get("success"):
                return {
                    "error": result.get("error"),
                    "is_complete": True
                }

            logger.info(f"✅ Article #{article_id} published successfully")

            return {
                "new_status": result.get("new_status", "published"),
                "response_text": f"""✅ **Article #{article_id} Published Successfully!**

The article is now visible to all readers.

**New Status:** {result.get('new_status', 'published')}""",
                "ui_action": {
                    "type": "article_published",
                    "params": {
                        "article_id": article_id,
                        "new_status": result.get("new_status")
                    }
                },
                "is_complete": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Publication failed: {e}")
        return {
            "error": str(e),
            "is_complete": True
        }


def response_builder_node(state: EditorState) -> Dict[str, Any]:
    """
    Build final response if not already complete.
    """
    if state.get("is_complete"):
        return {}

    if state.get("error"):
        return {
            "response_text": f"Error: {state.get('error')}",
            "is_complete": True
        }

    if state.get("permission_error"):
        return {
            "response_text": state.get("permission_error"),
            "is_complete": True
        }

    # If we get here with requires_confirmation, workflow is paused
    if state.get("requires_confirmation"):
        return {}  # Keep response_text from approve_prepare_node

    return {"is_complete": True}


# ============================================================================
# Conditional Edge Functions
# ============================================================================

def check_permission_route(state: EditorState) -> Literal["continue", "end"]:
    """Route based on permission check result."""
    if state.get("permission_granted"):
        return "continue"
    return "end"


def route_by_action(state: EditorState) -> Literal["review", "reject", "approve"]:
    """Route to action-specific node."""
    action = state.get("action", "review")

    if action == "reject":
        return "reject"
    elif action == "approve":
        return "approve"
    else:
        return "review"


def should_publish(state: EditorState) -> Literal["publish", "end"]:
    """Check if we should proceed to publish after HITL."""
    # If we have an HITL decision, proceed to publish
    if state.get("hitl_decision"):
        return "publish"
    return "end"


# ============================================================================
# Graph Builder
# ============================================================================

def build_editor_subgraph(checkpointer=None):
    """
    Build the editor workflow sub-graph with HITL support.

    Args:
        checkpointer: Optional checkpointer for HITL (e.g., RedisSaver)

    Returns:
        Compiled LangGraph StateGraph for editor workflows
    """
    workflow = StateGraph(EditorState)

    # Add nodes
    workflow.add_node("action_parser", action_parser_node)
    workflow.add_node("permission_check", permission_check_node)
    workflow.add_node("review_article", review_article_node)
    workflow.add_node("reject_article", reject_article_node)
    workflow.add_node("approve_prepare", approve_prepare_node)
    workflow.add_node("publish_execute", publish_execute_node)
    workflow.add_node("response_builder", response_builder_node)

    # Set entry point
    workflow.set_entry_point("action_parser")

    # Add edges
    workflow.add_edge("action_parser", "permission_check")

    # Conditional edge after permission check
    workflow.add_conditional_edges(
        "permission_check",
        check_permission_route,
        {
            "continue": "route_action",  # Placeholder for routing
            "end": "response_builder"
        }
    )

    # Add a routing node for action dispatch
    def route_action_node(state: EditorState) -> Dict[str, Any]:
        """Route to appropriate action handler."""
        return {}

    workflow.add_node("route_action", route_action_node)

    workflow.add_conditional_edges(
        "route_action",
        route_by_action,
        {
            "review": "review_article",
            "reject": "reject_article",
            "approve": "approve_prepare"
        }
    )

    # Action nodes lead to response builder or special handling
    workflow.add_edge("review_article", "response_builder")
    workflow.add_edge("reject_article", "response_builder")

    # Approve flow - this is where HITL happens
    # The workflow pauses at approve_prepare due to interrupt_before
    workflow.add_edge("approve_prepare", "publish_execute")
    workflow.add_edge("publish_execute", "response_builder")

    workflow.add_edge("response_builder", END)

    # Compile with HITL configuration
    # interrupt_before pauses the workflow before publish_execute
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["publish_execute"]
    )


# ============================================================================
# Public Interface
# ============================================================================

def run_editor_workflow(
    article_id: int,
    action: str,
    user_context: Dict[str, Any],
    topic: Optional[str] = None,
    rejection_notes: Optional[str] = None,
    editor_notes: Optional[str] = None,
    hitl_decision: Optional[str] = None,
    thread_id: Optional[str] = None,
    checkpointer=None
) -> Dict[str, Any]:
    """
    Run the editor workflow.

    Args:
        article_id: ID of the article
        action: Action to perform (review, approve, reject)
        user_context: User context with permissions
        topic: Optional topic (will be fetched from article if not provided)
        rejection_notes: Notes for rejection
        editor_notes: Notes for submission
        hitl_decision: Decision for HITL resume (approve/reject)
        thread_id: Thread ID for HITL resume
        checkpointer: Checkpointer for HITL state persistence

    Returns:
        Dict with response, status, and any UI actions
    """
    # Use in-memory checkpointer if none provided
    if checkpointer is None:
        checkpointer = MemorySaver()

    graph = build_editor_subgraph(checkpointer=checkpointer)

    initial_state = create_editor_state(
        article_id=article_id,
        action=action,
        user_context=user_context,
        topic=topic,
        rejection_notes=rejection_notes,
        editor_notes=editor_notes,
        hitl_decision=hitl_decision
    )

    # Generate thread_id if not resuming
    if not thread_id:
        thread_id = str(uuid.uuid4())

    config = {"configurable": {"thread_id": thread_id}}

    logger.info(f"🔧 Starting editor workflow: action={action}, article={article_id}, thread={thread_id}")

    try:
        final_state = graph.invoke(initial_state, config)

        # Check if workflow is paused for HITL
        if final_state.get("requires_confirmation") and not final_state.get("is_complete"):
            return {
                "status": "awaiting_confirmation",
                "thread_id": thread_id,
                "confirmation_id": final_state.get("confirmation_id"),
                "response_text": final_state.get("response_text"),
                "requires_hitl": True,
                "article_id": article_id
            }

        if final_state.get("error"):
            return {
                "status": "error",
                "error": final_state["error"],
                "response_text": f"Error: {final_state['error']}"
            }

        if final_state.get("permission_error"):
            return {
                "status": "error",
                "error": final_state["permission_error"],
                "response_text": final_state["permission_error"]
            }

        return {
            "status": "complete",
            "response_text": final_state.get("response_text", ""),
            "new_status": final_state.get("new_status"),
            "ui_action": final_state.get("ui_action")
        }

    except Exception as e:
        logger.exception(f"Editor workflow failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "response_text": f"Workflow error: {str(e)}"
        }


def resume_editor_workflow(
    thread_id: str,
    hitl_decision: str,
    user_context: Dict[str, Any],
    checkpointer=None
) -> Dict[str, Any]:
    """
    Resume an editor workflow after HITL decision.

    Args:
        thread_id: Thread ID of the paused workflow
        hitl_decision: User's decision (approve/reject)
        user_context: User context for the resume
        checkpointer: Same checkpointer used to start the workflow

    Returns:
        Dict with final response and status
    """
    if checkpointer is None:
        return {
            "status": "error",
            "error": "Checkpointer required to resume workflow"
        }

    graph = build_editor_subgraph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id}}

    logger.info(f"▶️ Resuming editor workflow: thread={thread_id}, decision={hitl_decision}")

    try:
        # Get current state from checkpoint
        state = graph.get_state(config)

        if not state or not state.values:
            return {
                "status": "error",
                "error": f"No workflow found for thread {thread_id}"
            }

        # Update state with HITL decision
        update = {"hitl_decision": hitl_decision}

        # Resume the workflow
        final_state = graph.invoke(update, config)

        return {
            "status": "complete",
            "response_text": final_state.get("response_text", ""),
            "new_status": final_state.get("new_status"),
            "ui_action": final_state.get("ui_action")
        }

    except Exception as e:
        logger.exception(f"Workflow resume failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }
