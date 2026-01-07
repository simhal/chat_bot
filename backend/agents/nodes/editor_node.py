"""
Editor Workflow node for the main chat graph.

This node handles editor workflow actions - reviewing articles, approving
for publication, rejecting with feedback, and managing the editorial queue.
It supports HITL (human-in-the-loop) via LangGraph's interrupt_before mechanism.

LangGraph Features Used:
- interrupt_before: Pauses workflow before destructive publish action
- Checkpointing: Persists state during HITL wait
- Conditional edges: Routes based on action type
"""

from typing import Dict, Any, Optional, List
import logging
import os

from langchain_openai import ChatOpenAI

from agents.state import AgentState
from agents.permission_utils import check_topic_permission, get_topics_for_role

logger = logging.getLogger(__name__)


def editor_workflow_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle editor workflow requests.

    This node:
    1. Determines the editor action (review, approve, reject, list_pending)
    2. Checks editor permissions for the topic
    3. For publish actions, triggers HITL via LangGraph interrupt
    4. Delegates to EditorSubAgent for actual operations

    Args:
        state: Current agent state with messages and context

    Returns:
        Updated state with response_text and appropriate workflow state
    """
    intent = state.get("intent", {})
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})
    messages = state.get("messages", [])

    # Check if this is an HITL resume
    hitl_decision = state.get("hitl_decision")
    if hitl_decision:
        return _handle_hitl_resume(hitl_decision, state, user_context)

    # Determine the action
    action = details.get("action", "review")
    if action == "review":
        # May need to infer from message
        action = _infer_editor_action(messages[-1].content if messages else "")

    # Get topic and article context
    topic = details.get("topic") or nav_context.get("topic")
    article_id = details.get("article_id") or nav_context.get("article_id")

    # Check editor permission for topic
    if topic:
        allowed, error_msg = check_topic_permission(topic, "editor", user_context)
        if not allowed:
            return {
                "response_text": error_msg,
                "selected_agent": "editor_workflow",
                "is_final": True
            }

    # Route to appropriate handler
    if action == "list_pending":
        return _handle_list_pending(topic, user_context)
    elif action == "review":
        return _handle_review(article_id, topic, user_context, nav_context)
    elif action == "approve":
        return _handle_approve(article_id, topic, user_context)
    elif action == "reject":
        rejection_notes = _extract_rejection_notes(messages[-1].content if messages else "")
        return _handle_reject(article_id, topic, user_context, rejection_notes)
    elif action == "submit":
        editor_notes = details.get("editor_notes", "")
        return _handle_submit_for_approval(article_id, topic, user_context, editor_notes)
    else:
        return {
            "response_text": f"Unknown editor action: {action}",
            "selected_agent": "editor_workflow",
            "is_final": True
        }


def _infer_editor_action(message: str) -> str:
    """Infer the editor action from the user's message."""
    message_lower = message.lower()

    if any(w in message_lower for w in ["approve", "publish", "accept"]):
        return "approve"
    if any(w in message_lower for w in ["reject", "decline", "send back", "request changes"]):
        return "reject"
    if any(w in message_lower for w in ["pending", "queue", "list", "waiting"]):
        return "list_pending"
    if any(w in message_lower for w in ["submit for", "ready for review"]):
        return "submit"

    return "review"


def _handle_list_pending(topic: Optional[str], user_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle request to list pending articles using EditorSubAgent.

    Delegates to EditorSubAgent.get_pending_approvals() for database query.
    """
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
            result = agent.get_pending_approvals(
                user_context=user_context,
                topic=topic
            )

            if not result.get("success"):
                return {
                    "response_text": f"Error listing pending articles: {result.get('error')}",
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }

            pending = result.get("pending_approvals", [])
            if not pending:
                return {
                    "response_text": f"No pending articles found{f' for {topic}' if topic else ''}.",
                    "navigation": {
                        "action": "navigate",
                        "target": f"/editor/{topic}" if topic else "/editor",
                        "params": {"topic": topic, "section": "editor"}
                    } if topic else None,
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }

            # Format pending articles
            articles_list = "\n".join([
                f"- **#{a['article_id']}**: {a['article_headline']} ({a['topic']}) - by {a['requested_by']}"
                for a in pending[:10]
            ])

            return {
                "response_text": f"**Pending Approval ({len(pending)} articles):**\n\n{articles_list}",
                "referenced_articles": [
                    {"id": a["article_id"], "headline": a["article_headline"]}
                    for a in pending
                ],
                "navigation": {
                    "action": "navigate",
                    "target": f"/editor/{topic}" if topic else "/editor",
                    "params": {"topic": topic, "section": "editor"}
                } if topic else None,
                "selected_agent": "editor_workflow",
                "routing_reason": "List pending articles",
                "is_final": True
            }

        finally:
            db.close()

    except ImportError as e:
        logger.warning(f"EditorSubAgent not available: {e}")
        # Fallback response
        if topic:
            response = (f"To see pending articles for {topic}, "
                       f"navigate to the editor hub: [Go to Editor](/editor/{topic})")
        else:
            response = ("To see pending articles, select a topic and navigate to its editor hub. "
                       "Which topic would you like to review?")

        return {
            "response_text": response,
            "navigation": {
                "action": "navigate",
                "target": f"/editor/{topic}" if topic else "/editor",
                "params": {"topic": topic, "section": "editor"}
            } if topic else None,
            "selected_agent": "editor_workflow",
            "routing_reason": "List pending articles",
            "is_final": True
        }


def _handle_review(
    article_id: Optional[int],
    topic: Optional[str],
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle article review request using EditorSubAgent.

    Delegates to EditorSubAgent.review_article() for AI-powered review.
    """
    if not article_id:
        return {
            "response_text": "Which article would you like to review? "
                           "Please specify an article ID or select one from the editor queue.",
            "selected_agent": "editor_workflow",
            "is_final": True
        }

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
                    "response_text": f"Unable to review article #{article_id}: {result.get('error')}",
                    "selected_agent": "editor_workflow",
                    "error": result.get("error"),
                    "is_final": True
                }

            # Build review response
            article_info = result.get("article", {})
            ai_review = result.get("ai_review", {})
            review_text = ai_review.get("review", "No AI review available.")

            response = f"""**Editorial Review - Article #{article_id}**

**Headline:** {article_info.get('headline', 'Unknown')}
**Topic:** {article_info.get('topic', 'Unknown')}
**Status:** {article_info.get('status', 'Unknown')}
**Author:** {article_info.get('author', 'Unknown')}

---

{review_text}

---

Use **approve** to publish or **reject** to send back with feedback."""

            return {
                "response_text": response,
                "referenced_articles": [{
                    "id": article_id,
                    "headline": article_info.get("headline"),
                    "topic": article_info.get("topic"),
                    "status": article_info.get("status")
                }],
                "ui_action": {
                    "type": "view_article",
                    "params": {"article_id": article_id}
                },
                "selected_agent": "editor_workflow",
                "routing_reason": f"Review article #{article_id}",
                "is_final": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Review generation failed: {e}")
        return {
            "response_text": f"Unable to generate review for article #{article_id}: {str(e)}",
            "selected_agent": "editor_workflow",
            "error": str(e),
            "is_final": True
        }


def _handle_submit_for_approval(
    article_id: Optional[int],
    topic: Optional[str],
    user_context: Dict[str, Any],
    editor_notes: str = "",
    use_celery: bool = False
) -> Dict[str, Any]:
    """
    Submit an article for HITL approval using EditorSubAgent.

    This transitions the article to PENDING_APPROVAL status and creates
    an ApprovalRequest. The workflow pauses here for human review.

    Args:
        article_id: ID of the article
        topic: Topic slug
        user_context: User context for permissions
        editor_notes: Optional notes from the editor
        use_celery: If True, queue on Celery worker
    """
    if not article_id:
        return {
            "response_text": "Which article would you like to submit for approval? "
                           "Please specify an article ID.",
            "selected_agent": "editor_workflow",
            "is_final": True
        }

    try:
        if use_celery:
            # Queue on Celery worker
            from tasks.agent_tasks import editor_publish_task

            user_id = user_context.get("user_id", 0)
            task = editor_publish_task.delay(
                user_id=user_id,
                article_id=article_id,
                editor_notes=editor_notes
            )

            return {
                "response_text": f"Article #{article_id} submission queued. "
                               f"You'll be notified when it requires approval.\n\n"
                               f"**Task ID:** `{task.id}`",
                "async_task": {
                    "task_id": task.id,
                    "task_type": "editor_publish"
                },
                "selected_agent": "editor_workflow",
                "is_final": True
            }

        # Synchronous execution using EditorSubAgent
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
            result = agent.submit_for_approval(
                article_id=article_id,
                user_context=user_context,
                editor_notes=editor_notes
            )

            if not result.get("success"):
                return {
                    "response_text": f"Submission failed: {result.get('error')}",
                    "selected_agent": "editor_workflow",
                    "error": result.get("error"),
                    "is_final": True
                }

            # Article is now awaiting approval
            return {
                "response_text": f"""Article #{article_id} submitted for approval.

**Approval Request ID:** {result.get('approval_request_id')}
**Thread ID:** `{result.get('thread_id')}`
**Expires:** {result.get('expires_at')}

The article is now awaiting human review. Reviewers will be notified.""",
                "confirmation": {
                    "id": result.get("thread_id"),
                    "type": "awaiting_approval",
                    "title": "Article Submitted",
                    "message": f"Article #{article_id} is awaiting human approval.",
                    "article_id": article_id,
                    "topic": topic,
                    "thread_id": result.get("thread_id"),
                    "approval_endpoint": f"/api/approvals/{result.get('approval_request_id')}"
                },
                "selected_agent": "editor_workflow",
                "is_final": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Submit for approval failed: {e}")
        return {
            "response_text": f"Submission failed: {str(e)}",
            "selected_agent": "editor_workflow",
            "error": str(e),
            "is_final": True
        }


def _handle_approve(
    article_id: Optional[int],
    topic: Optional[str],
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle article approval request.

    For LangGraph HITL workflow:
    - Sets requires_hitl=True to trigger interrupt_before
    - Returns confirmation object for frontend display
    - Actual publish happens after HITL resume with hitl_decision="approve"
    """
    if not article_id:
        return {
            "response_text": "Which article would you like to approve? "
                           "Please specify an article ID.",
            "selected_agent": "editor_workflow",
            "is_final": True
        }

    # Build HITL confirmation - this triggers LangGraph interrupt
    import uuid
    confirmation_id = str(uuid.uuid4())

    return {
        "response_text": f"Ready to publish article #{article_id}?\n\n"
                        f"This will make the article visible to all readers. "
                        f"Please confirm to proceed.",
        "confirmation": {
            "id": confirmation_id,
            "type": "publish_approval",
            "title": "Publish Article",
            "message": f"Publish article #{article_id}? "
                      f"This will make it visible to all readers.",
            "article_id": article_id,
            "topic": topic,
            "confirm_label": "Publish Now",
            "cancel_label": "Cancel",
            "confirm_action": "approve",
            "cancel_action": "reject"
        },
        "requires_hitl": True,  # Triggers LangGraph interrupt_before
        "selected_agent": "editor_workflow",
        "routing_reason": f"Approval request for article #{article_id}",
        "is_final": False  # NOT final - waiting for HITL decision
    }


def _handle_reject(
    article_id: Optional[int],
    topic: Optional[str],
    user_context: Dict[str, Any],
    notes: str
) -> Dict[str, Any]:
    """
    Handle article rejection using EditorSubAgent.

    Delegates to EditorSubAgent.request_changes() to transition
    article back to DRAFT status with feedback.
    """
    if not article_id:
        return {
            "response_text": "Which article would you like to send back for revisions? "
                           "Please specify an article ID.",
            "selected_agent": "editor_workflow",
            "is_final": True
        }

    if not notes:
        return {
            "response_text": f"Sending article #{article_id} back for revisions. "
                           f"Please provide feedback for the author. "
                           f"What changes should they make?",
            "selected_agent": "editor_workflow",
            "is_final": True
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
                notes=notes
            )

            if not result.get("success"):
                return {
                    "response_text": f"Rejection failed: {result.get('error')}",
                    "selected_agent": "editor_workflow",
                    "error": result.get("error"),
                    "is_final": True
                }

            return {
                "response_text": f"""Article #{article_id} has been sent back to the author for revisions.

**Status:** {result.get('new_status', 'draft')}

**Your feedback:**
{notes}

The author will be notified of the requested changes.""",
                "ui_action": {
                    "type": "article_rejected",
                    "params": {
                        "article_id": article_id,
                        "new_status": result.get("new_status"),
                        "notes": notes
                    }
                },
                "selected_agent": "editor_workflow",
                "routing_reason": f"Rejected article #{article_id}",
                "is_final": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Rejection failed: {e}")
        return {
            "response_text": f"Rejection failed: {str(e)}",
            "selected_agent": "editor_workflow",
            "error": str(e),
            "is_final": True
        }


def _extract_rejection_notes(message: str) -> str:
    """Extract rejection notes from the user's message."""
    # Remove common prefixes
    prefixes = [
        "reject", "send back", "request changes", "decline",
        "article", "please", "because", "the", "this"
    ]

    words = message.lower().split()
    filtered_words = []
    skip_next = False

    for word in message.split():
        if skip_next:
            skip_next = False
            continue
        if word.lower() in prefixes:
            continue
        if word.startswith("#") or word.isdigit():
            continue
        filtered_words.append(word)

    notes = " ".join(filtered_words).strip()

    # If nothing left, return empty (will prompt for feedback)
    if len(notes) < 10:
        return ""

    return notes


def _handle_hitl_resume(
    decision: str,
    state: AgentState,
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle resume from HITL checkpoint.

    Called when the LangGraph workflow is resumed after human approval/rejection.
    This executes the actual publish or rejection using EditorSubAgent.
    """
    nav_context = state.get("navigation_context", {})
    article_id = nav_context.get("article_id")

    # Also check confirmation object for article_id
    confirmation = state.get("confirmation", {})
    if not article_id and confirmation:
        article_id = confirmation.get("article_id")

    if not article_id:
        return {
            "response_text": "Cannot complete action: Article ID not found in state.",
            "selected_agent": "editor_workflow",
            "error": "article_id_missing",
            "is_final": True
        }

    if decision == "approve":
        # Execute publish using EditorSubAgent
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
                        "response_text": f"Publication failed: {result.get('error')}",
                        "selected_agent": "editor_workflow",
                        "error": result.get("error"),
                        "is_final": True
                    }

                return {
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
                    "selected_agent": "editor_workflow",
                    "routing_reason": f"Published article #{article_id}",
                    "is_final": True
                }

            finally:
                db.close()

        except Exception as e:
            logger.exception(f"Publication failed: {e}")
            return {
                "response_text": f"Publication failed: {str(e)}",
                "selected_agent": "editor_workflow",
                "error": str(e),
                "is_final": True
            }

    else:
        # Rejection - return to editor status
        return {
            "response_text": f"Publication cancelled. Article #{article_id} remains in the review queue.",
            "ui_action": {
                "type": "publication_cancelled",
                "params": {"article_id": article_id}
            },
            "selected_agent": "editor_workflow",
            "routing_reason": "Publication cancelled",
            "is_final": True
        }
