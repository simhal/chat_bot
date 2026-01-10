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
from agents.permission_utils import check_topic_permission, get_topics_for_role, validate_article_access

logger = logging.getLogger("uvicorn")


def editor_workflow_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle article workflow requests.

    This node handles both analyst and editor workflow actions:
    - Analyst: "submit" (DRAFT → EDITOR) - requires analyst permission
    - Editor: "review", "publish", "reject", "list_pending" - requires editor permission

    Args:
        state: Current agent state with messages and context

    Returns:
        Updated state with response_text and appropriate workflow state
    """
    print(f">>> editor_workflow_node CALLED")
    intent = state.get("intent", {})
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})
    messages = state.get("messages", [])

    print(f">>> editor_workflow_node: intent={intent}, action from details={details.get('action')}")
    logger.info(f"editor_workflow_node: ENTRY - intent={intent}, nav_context={nav_context}")

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

    # Check role context for proper workflow routing
    current_role = nav_context.get("role", "reader")

    # Reader context - guide to appropriate dashboard
    if current_role == "reader":
        topic_roles = user_context.get("topic_roles", {})
        highest_role = user_context.get("highest_role", "reader")

        if action == "submit":
            # Reader wants to submit - check if they have analyst access
            has_analyst_access = highest_role in ["analyst", "editor", "admin"] or \
                                any(r in ["analyst", "editor", "admin"] for r in topic_roles.values())
            if has_analyst_access:
                return {
                    "response_text": "I'll take you to the analyst dashboard first, where you can manage your articles and submit them for review.",
                    "navigation": {
                        "action": "navigate",
                        "target": f"/analyst/{topic}" if topic else "/analyst",
                        "params": {"section": "analyst", "topic": topic}
                    },
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }
            else:
                return {
                    "response_text": "You don't have permission to submit articles. Please contact an administrator.",
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }

        if action in ["publish", "approve", "reject", "review", "list_pending"]:
            # Reader wants to do editor actions
            has_editor_access = highest_role in ["editor", "admin"] or \
                               any(r in ["editor", "admin"] for r in topic_roles.values())
            if has_editor_access:
                return {
                    "response_text": "I'll take you to the editor dashboard first, where you can review and publish articles.",
                    "navigation": {
                        "action": "navigate",
                        "target": f"/editor/{topic}" if topic else "/editor",
                        "params": {"section": "editor", "topic": topic}
                    },
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }
            else:
                return {
                    "response_text": "You don't have permission to perform editorial actions. Please contact an administrator.",
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }

    # Analyst context - can submit but cannot publish directly
    if current_role == "analyst" and action in ["publish", "approve"]:
        return {
            "response_text": "The article needs to be reviewed first. I'll take you to the editor dashboard where you can review and publish it.",
            "navigation": {
                "action": "navigate",
                "target": f"/editor/{topic}" if topic else "/editor",
                "params": {"section": "editor", "topic": topic, "article_id": article_id}
            },
            "selected_agent": "editor_workflow",
            "is_final": True
        }

    # Route to appropriate handler with role-appropriate permission checks
    # "submit" action is for analyst (DRAFT→EDITOR)
    if action == "submit":
        # Permission checked inside based on article status
        return _handle_submit(article_id, topic, user_context)

    # All other actions require editor permission
    if topic:
        allowed, error_msg = check_topic_permission(topic, "editor", user_context)
        if not allowed:
            return {
                "response_text": error_msg,
                "selected_agent": "editor_workflow",
                "is_final": True
            }

    logger.info(f"editor_workflow_node: Routing action='{action}' for article_id={article_id}, topic={topic}, current_role={current_role}")
    if action == "list_pending":
        return _handle_list_pending(topic, user_context)
    elif action == "review":
        return _handle_review(article_id, topic, user_context, nav_context, messages)
    elif action in ["approve", "publish"]:
        logger.info(f"editor_workflow_node: Calling _handle_publish for article_id={article_id}")
        return _handle_publish(article_id, topic, user_context)
    elif action == "reject":
        rejection_notes = _extract_rejection_notes(messages[-1].content if messages else "")
        return _handle_reject(article_id, topic, user_context, rejection_notes)
    else:
        return {
            "response_text": f"Unknown action: {action}. Try 'submit for review', 'publish', or 'reject'.",
            "selected_agent": "editor_workflow",
            "is_final": True
        }


def _infer_editor_action(message: str) -> str:
    """Infer the workflow action from the user's message."""
    message_lower = message.lower()

    # Analyst action: submit draft for review
    if any(w in message_lower for w in ["submit for review", "submit it", "submit the article", "ready for review"]):
        return "submit"

    # Editor action: publish article
    if any(w in message_lower for w in ["publish", "approve", "accept", "go live"]):
        return "publish"

    # Editor action: reject/request changes
    if any(w in message_lower for w in ["reject", "decline", "send back", "request changes"]):
        return "reject"

    # Editor action: list pending articles
    if any(w in message_lower for w in ["pending", "queue", "list", "waiting", "for review"]):
        return "list_pending"

    # Generic "submit" without "for review" - check context later
    if "submit" in message_lower:
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
    nav_context: Dict[str, Any],
    messages: Optional[list] = None
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

    # Convert messages to conversation history format
    conversation_history = []
    if messages:
        for msg in messages[-10:]:  # Last 10 messages
            role = "assistant" if hasattr(msg, 'type') and msg.type == "ai" else "user"
            content = msg.content if hasattr(msg, 'content') else str(msg)
            conversation_history.append({"role": role, "content": content})

    try:
        from agents.editor_sub_agent import EditorSubAgent
        from database import SessionLocal

        # Validate article access before proceeding
        db = SessionLocal()
        try:
            allowed, error_msg, article_info = validate_article_access(
                article_id, user_context, db, topic
            )
            if not allowed:
                return {
                    "response_text": error_msg,
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }
        finally:
            db.close()

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
                user_context=user_context,
                conversation_history=conversation_history
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


def _handle_submit(
    article_id: Optional[int],
    topic: Optional[str],
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle article submission based on current status.

    Routes to appropriate workflow with role-specific permission checks:
    - DRAFT → EDITOR: Analyst submits for editorial review (requires analyst permission)
    - EDITOR → PENDING_APPROVAL: Editor publishes article (requires editor permission)

    Args:
        article_id: ID of the article
        topic: Topic slug
        user_context: User context for permissions
    """
    if not article_id:
        return {
            "response_text": "Which article would you like to submit? "
                           "Please specify an article ID.",
            "selected_agent": "editor_workflow",
            "is_final": True
        }

    try:
        from database import SessionLocal
        from models import ContentArticle, ArticleStatus

        db = SessionLocal()
        try:
            # First, check the article's current status
            article = db.query(ContentArticle).filter(
                ContentArticle.id == article_id,
                ContentArticle.is_active == True
            ).first()

            if not article:
                return {
                    "response_text": f"Article #{article_id} not found.",
                    "selected_agent": "editor_workflow",
                    "error": "article_not_found",
                    "is_final": True
                }

            # Route based on current status with appropriate permission checks
            if article.status == ArticleStatus.DRAFT:
                # Analyst workflow: DRAFT → EDITOR (submit for review)
                # Check analyst permission
                if topic:
                    allowed, error_msg = check_topic_permission(topic, "analyst", user_context)
                    if not allowed:
                        return {
                            "response_text": error_msg,
                            "selected_agent": "editor_workflow",
                            "is_final": True
                        }
                return _handle_submit_for_review(article_id, topic, user_context, db)

            elif article.status == ArticleStatus.EDITOR:
                # Editor workflow: EDITOR → PUBLISHED (via HITL)
                # Check editor permission
                if topic:
                    allowed, error_msg = check_topic_permission(topic, "editor", user_context)
                    if not allowed:
                        return {
                            "response_text": error_msg,
                            "selected_agent": "editor_workflow",
                            "is_final": True
                        }
                # Redirect to publish handler
                db.close()
                return _handle_publish(article_id, topic, user_context)

            elif article.status == ArticleStatus.PENDING_APPROVAL:
                return {
                    "response_text": f"Article #{article_id} is already pending approval. "
                                   f"It's waiting for a reviewer to approve or reject it.",
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }

            elif article.status == ArticleStatus.PUBLISHED:
                return {
                    "response_text": f"Article #{article_id} is already published.",
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }

            else:
                return {
                    "response_text": f"Article #{article_id} is in an unexpected status: {article.status.value}",
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Submit failed: {e}")
        return {
            "response_text": f"Submission failed: {str(e)}",
            "selected_agent": "editor_workflow",
            "error": str(e),
            "is_final": True
        }


def _handle_submit_for_review(
    article_id: int,
    topic: Optional[str],
    user_context: Dict[str, Any],
    db
) -> Dict[str, Any]:
    """
    Handle analyst submission: DRAFT → EDITOR.

    Uses ArticleQueryAgent.submit_for_review() to transition the article.
    """
    try:
        from agents.article_query_agent import ArticleQueryAgent

        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        agent = ArticleQueryAgent(llm=llm, db=db, topic=topic)
        result = agent.submit_for_review(
            article_id=article_id,
            user_context=user_context
        )

        if not result.get("success"):
            return {
                "response_text": f"Submission failed: {result.get('error')}",
                "selected_agent": "editor_workflow",
                "error": result.get("error"),
                "is_final": True
            }

        return {
            "response_text": f"""Article #{article_id} has been submitted for editorial review.

**New Status:** Editor Queue
**Headline:** {result.get('headline', 'N/A')}

An editor will review your article and either approve it for publication or request changes.""",
            "ui_action": {
                "type": "article_submitted",
                "params": {
                    "article_id": article_id,
                    "new_status": "editor"
                }
            },
            "selected_agent": "editor_workflow",
            "routing_reason": f"Submitted article #{article_id} for review",
            "is_final": True
        }

    except Exception as e:
        logger.exception(f"Submit for review failed: {e}")
        return {
            "response_text": f"Submission failed: {str(e)}",
            "selected_agent": "editor_workflow",
            "error": str(e),
            "is_final": True
        }


def _handle_publish(
    article_id: Optional[int],
    topic: Optional[str],
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle article publish request.

    For LangGraph HITL workflow:
    - Sets requires_hitl=True to trigger interrupt_before
    - Returns confirmation object for frontend display
    - Actual publish happens after HITL resume with hitl_decision="approve"
    """
    print(f">>> _handle_publish CALLED: article_id={article_id}, topic={topic}")
    if not article_id:
        return {
            "response_text": "Which article would you like to publish? "
                           "Please specify an article ID.",
            "selected_agent": "editor_workflow",
            "is_final": True
        }

    # Validate article access and status before proceeding
    logger.info(f"_handle_publish: STARTING - article_id={article_id}, topic={topic}")
    try:
        from database import SessionLocal
        db = SessionLocal()
        try:
            allowed, error_msg, article_info = validate_article_access(
                article_id, user_context, db, topic
            )
            logger.info(f"_handle_publish: validate_article_access returned: allowed={allowed}, error_msg={error_msg}, article_info={article_info}")
            if not allowed:
                logger.info(f"_handle_publish: ACCESS DENIED - returning error: {error_msg}")
                return {
                    "response_text": error_msg,
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }
            # Update topic from article if not provided
            if not topic and article_info:
                topic = article_info.get("topic")

            # Check article is in "editor" status (required for publishing)
            article_status = article_info.get("status", "") if article_info else ""
            logger.info(f"_handle_publish: raw article_status from article_info = '{article_status}' (type: {type(article_status)})")
            # Handle enum or string
            if hasattr(article_status, 'value'):
                article_status = article_status.value
                logger.info(f"_handle_publish: after .value extraction = '{article_status}'")
            article_status = str(article_status).lower()
            logger.info(f"_handle_publish: FINAL status check - article_id={article_id}, status='{article_status}'")
            if article_status != "editor":
                logger.info(f"_handle_publish: STATUS BLOCKING - article_status '{article_status}' != 'editor'")
                if article_status == "draft":
                    logger.info(f"_handle_publish: Returning DRAFT status error for article {article_id}")
                    return {
                        "response_text": f"Article #{article_id} is still in **draft** status. "
                                        "It needs to be submitted for review first before it can be published.\n\n"
                                        "Would you like me to submit it for review?",
                        "selected_agent": "editor_workflow",
                        "is_final": True
                    }
                elif article_status == "published":
                    logger.info(f"_handle_publish: Returning PUBLISHED status error for article {article_id}")
                    return {
                        "response_text": f"Article #{article_id} is already **published**.",
                        "selected_agent": "editor_workflow",
                        "is_final": True
                    }
                else:
                    logger.info(f"_handle_publish: Returning OTHER status error for article {article_id}, status='{article_status}'")
                    return {
                        "response_text": f"Article #{article_id} has status '{article_status}' and cannot be published. "
                                        "Only articles in 'editor' status (awaiting review) can be published.",
                        "selected_agent": "editor_workflow",
                        "is_final": True
                    }
            else:
                logger.info(f"_handle_publish: STATUS OK - proceeding with confirmation dialog for article {article_id}")
        finally:
            db.close()
    except Exception as e:
        logger.exception(f"Article access validation failed: {e}")
        return {
            "response_text": f"Unable to validate article access: {str(e)}",
            "selected_agent": "editor_workflow",
            "error": str(e),
            "is_final": True
        }

    # Build confirmation dialog - shows buttons in chat for user to confirm/cancel
    # Article stays in EDITOR status until user clicks confirm and the API endpoint is called
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
            # API endpoint to call when user confirms - this publishes directly
            "confirm_endpoint": f"/api/editor/{topic}/article/{article_id}/publish",
            "confirm_method": "POST",
            "confirm_body": {}
        },
        "selected_agent": "editor_workflow",
        "routing_reason": f"Awaiting confirmation for article #{article_id}",
        "is_final": True  # Response is complete - frontend handles confirmation via API
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

        # Validate article access before proceeding
        db = SessionLocal()
        try:
            allowed, error_msg, article_info = validate_article_access(
                article_id, user_context, db, topic
            )
            if not allowed:
                return {
                    "response_text": error_msg,
                    "selected_agent": "editor_workflow",
                    "is_final": True
                }
        finally:
            db.close()

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
    Handle resume from HITL checkpoint (if using workflow resume endpoint).

    Called when the LangGraph workflow is resumed after human approval/rejection.
    This executes the actual publish directly (same logic as /api/editor/.../publish).

    Note: The primary confirmation flow uses the frontend calling the REST API directly.
    This function handles the alternative workflow resume path.
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
        # Execute publish directly (same logic as REST API endpoint)
        try:
            from database import SessionLocal
            from models import ContentArticle, ArticleStatus
            from services.content_service import ContentService
            from services.article_resource_service import ArticleResourceService
            from services.vector_service import VectorService

            db = SessionLocal()
            try:
                # Get and validate article
                article = db.query(ContentArticle).filter(
                    ContentArticle.id == article_id,
                    ContentArticle.is_active == True
                ).first()

                if not article:
                    return {
                        "response_text": f"Article #{article_id} not found.",
                        "selected_agent": "editor_workflow",
                        "error": "article_not_found",
                        "is_final": True
                    }

                # Article must be in EDITOR status (not PENDING_APPROVAL)
                if article.status != ArticleStatus.EDITOR:
                    return {
                        "response_text": f"Article #{article_id} cannot be published. Current status: {article.status.value}. "
                                        f"Only articles in 'editor' status can be published.",
                        "selected_agent": "editor_workflow",
                        "error": "invalid_status",
                        "is_final": True
                    }

                # Publish the article
                editor_email = user_context.get("email", "")
                updated = ContentService.publish_article_with_editor(db, article_id, editor_email)

                # Create publication resources (HTML, PDF)
                user_id = user_context.get("user_id")
                content = VectorService.get_article_content(article_id)
                if content and user_id:
                    ArticleResourceService.create_article_resources(
                        db=db,
                        article=article,
                        content=content,
                        editor_user_id=user_id
                    )
                    logger.info(f"Created publication resources for article {article_id}")

                return {
                    "response_text": f"""**Article #{article_id} Published Successfully!**

The article is now visible to all readers.

**New Status:** published""",
                    "ui_action": {
                        "type": "article_published",
                        "params": {
                            "article_id": article_id,
                            "new_status": "published"
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
        # Rejection/cancellation - article stays in EDITOR status
        return {
            "response_text": f"Publication cancelled. Article #{article_id} remains in editor status for further review.",
            "ui_action": {
                "type": "publication_cancelled",
                "params": {"article_id": article_id}
            },
            "selected_agent": "editor_workflow",
            "routing_reason": "Publication cancelled",
            "is_final": True
        }
