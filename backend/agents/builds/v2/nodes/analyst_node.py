"""
Analyst node for the main chat graph.

This node handles analyst role context:
- Content generation (via article_content sub-graph)
- Resource management (via resource sub-graph)
- Article editing and drafts
- View switching
- Submit for review

SPECIAL HANDLING FOR analyst_editor SECTION:
When user is in the article editor (analyst_editor section), the node automatically
routes content-related requests to the article_content sub-graph:
- "better headline" → regenerate_headline
- "suggest keywords" → regenerate_keywords
- "rewrite the introduction" → edit_section
- "make it more concise" → refine_content

Routes based on nav_context.section starting with 'analyst_'
"""

from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from agents.builds.v2.state import AgentState
from agents.shared.permission_utils import check_topic_permission, validate_article_access
from agents.builds.v2.nodes.analyst import invoke_article_content, invoke_resource_action
from agents.builds.v2.action_validator import (
    detect_content_action,
    is_content_request,
    is_resource_request,
    validate_action,
    ALWAYS_ALLOWED_ACTIONS,
)

logger = logging.getLogger(__name__)


# Analyst UI actions
ANALYST_UI_ACTIONS = {
    # Draft management
    "save_draft": {},
    "edit_article": {"requires_article": True},
    "create_new_article": {},
    # View switching
    "switch_view_editor": {},
    "switch_view_preview": {},
    "switch_view_resources": {},
    # Resource actions (delegated to resource sub-graph)
    "browse_resources": {"resource_action": "browse"},
    "add_resource": {"resource_action": "add", "requires_resource": True},
    "remove_resource": {"resource_action": "remove", "requires_resource": True},
    "link_resource": {"resource_action": "link", "requires_resource": True},
    "unlink_resource": {"resource_action": "unlink", "requires_resource": True},
    "open_resource_modal": {},
    "select_resource": {"requires_resource": True},
    # Submission
    "submit_for_review": {"requires_article": True},
    "submit_article": {"requires_article": True},
}

# Content generation actions (delegated to article_content sub-graph)
CONTENT_ACTIONS = {
    "create": "create",
    "regenerate_headline": "regenerate_headline",
    "regenerate_keywords": "regenerate_keywords",
    "regenerate_content": "regenerate_content",
    "edit_section": "edit_section",
    "refine_content": "refine_content",
    # Aliases
    "rewrite": "regenerate_content",
    "rephrase_headline": "regenerate_headline",
}


def analyst_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle analyst context requests.

    This node orchestrates:
    1. Analyst UI actions (save, edit, view switching)
    2. Content generation via article_content sub-graph
    3. Resource management via resource sub-graph
    4. Article submission workflow

    SPECIAL HANDLING: When in analyst_editor section, automatically detect
    content operations from natural language (e.g., "better headline",
    "rewrite the intro", "make it more concise").

    Args:
        state: Current agent state with messages and context

    Returns:
        Updated state with response and optional editor_content/ui_action
    """
    intent = state.get("intent", {})
    intent_type = intent.get("intent_type", "")
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})
    messages = state.get("messages", [])
    section = nav_context.get("section", "")

    # Get topic and verify permission
    topic = details.get("topic") or nav_context.get("topic")
    if topic:
        allowed, error_msg = check_topic_permission(topic, "analyst", user_context)
        if not allowed:
            return {
                "response_text": error_msg,
                "selected_agent": "analyst",
                "is_final": True
            }

    # Check for UI action
    action_type = details.get("action_type", "")
    action = details.get("action", "")

    # ==========================================================================
    # SPECIAL HANDLING: analyst_editor section
    # When user is actively editing an article, intelligently route requests
    # ==========================================================================
    if section == "analyst_editor":
        return _handle_editor_context(state, topic, user_context, nav_context, messages, intent_type, details)

    # Route content generation to sub-graph
    if intent_type == "content_generation" or action in CONTENT_ACTIONS:
        return _handle_content_generation(state, topic, user_context, nav_context, messages)

    # Route resource actions to sub-graph
    if action_type in ANALYST_UI_ACTIONS and ANALYST_UI_ACTIONS[action_type].get("resource_action"):
        return _handle_resource_action(action_type, details, user_context, nav_context, topic)

    # Handle analyst UI actions
    if action_type in ANALYST_UI_ACTIONS:
        return _handle_analyst_ui_action(action_type, details, user_context, nav_context, topic)

    # Infer action from message
    if messages:
        user_query = messages[-1].content
        inferred_action = _infer_analyst_action(user_query)

        if inferred_action in CONTENT_ACTIONS:
            return _handle_content_generation(state, topic, user_context, nav_context, messages)

        if inferred_action in ANALYST_UI_ACTIONS:
            return _handle_analyst_ui_action(inferred_action, details, user_context, nav_context, topic)

    # Default: help message for analyst context
    return _handle_analyst_chat(messages, user_context, nav_context, topic)


def _handle_editor_context(
    state: AgentState,
    topic: Optional[str],
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any],
    messages: List,
    intent_type: str,
    details: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle requests when user is actively in the article editor (analyst_editor section).

    This provides a smooth editing experience by automatically detecting:
    - Headline requests → regenerate_headline
    - Keyword requests → regenerate_keywords
    - Section edits (rewrite intro, expand analysis) → edit_section
    - Style refinements (more concise, professional) → refine_content
    - Resource requests → resource sub-graph
    - UI actions (save, submit, switch view) → direct handling
    """
    user_query = messages[-1].content if messages else ""
    action_type = details.get("action_type", "")

    # Check for explicit UI actions first
    if action_type in ANALYST_UI_ACTIONS:
        return _handle_analyst_ui_action(action_type, details, user_context, nav_context, topic)

    # Check for resource requests
    if is_resource_request(user_query, details):
        resource_action = details.get("action_type", "browse_resources")
        if resource_action not in ANALYST_UI_ACTIONS:
            resource_action = "browse_resources"
        return _handle_resource_action(resource_action, details, user_context, nav_context, topic)

    # Detect content action from message
    detected_action = detect_content_action(user_query, details)
    logger.info(f"Editor context: detected action '{detected_action}' from message: {user_query[:50]}...")

    # For content actions, use the content generation handler with the detected action
    if detected_action in CONTENT_ACTIONS:
        # Override the action in details
        modified_details = dict(details)
        modified_details["action"] = detected_action

        modified_state = dict(state)
        modified_intent = dict(state.get("intent", {}))
        modified_intent["details"] = modified_details
        modified_state["intent"] = modified_intent

        return _handle_content_generation(
            modified_state, topic, user_context, nav_context, messages
        )

    # Fallback: treat as general analyst chat
    return _handle_analyst_chat(messages, user_context, nav_context, topic)


def _handle_content_generation(
    state: AgentState,
    topic: Optional[str],
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any],
    messages: List
) -> Dict[str, Any]:
    """Handle content generation via article_content sub-graph."""
    intent = state.get("intent", {})
    details = intent.get("details", {})

    # Determine action type
    action = details.get("action", "create")
    if action not in CONTENT_ACTIONS:
        action = "create"

    # Get user query
    user_query = messages[-1].content if messages else ""

    # Extract content request
    content_request = _extract_content_request(user_query, nav_context)

    # Topic validation
    if not topic:
        topic = _infer_topic_from_query(user_query)

    if not topic:
        from agents.shared.topic_manager import get_available_topics
        available_topics = get_available_topics()
        topics_list = ", ".join(available_topics) if available_topics else "no topics available"
        query_preview = user_query[:100] + "..." if len(user_query) > 100 else user_query

        return {
            "response_text": f"I'd be happy to help you write about **\"{query_preview}\"**.\n\n"
                           f"Which topic should this article be filed under? "
                           f"Please specify one of: {topics_list}.",
            "selected_agent": "analyst",
            "is_final": True
        }

    # Get existing content for regeneration actions
    article_id = details.get("article_id") or nav_context.get("article_id")
    existing_headline = nav_context.get("article_headline", "")
    existing_keywords = nav_context.get("article_keywords", "")
    existing_content = ""

    if article_id:
        existing_content = _get_article_content(article_id)

    # Build conversation history
    conversation_history = []
    if messages:
        for msg in messages[-10:]:
            role = "assistant" if hasattr(msg, 'type') and msg.type == "ai" else "user"
            content = msg.content if hasattr(msg, 'content') else str(msg)
            conversation_history.append({"role": role, "content": content})

    # Invoke article content sub-graph
    result = invoke_article_content(
        action=CONTENT_ACTIONS.get(action, "create"),
        query=content_request,
        topic=topic,
        user_context=user_context,
        article_id=article_id,
        existing_headline=existing_headline,
        existing_keywords=existing_keywords,
        existing_content=existing_content,
        conversation_history=conversation_history
    )

    if not result.get("success"):
        return {
            "response_text": f"Content generation failed: {result.get('error', 'Unknown error')}",
            "selected_agent": "analyst",
            "error": result.get("error"),
            "is_final": True
        }

    # Build response
    response_text = _build_content_response(result, action, topic, article_id)

    response = {
        "response_text": response_text,
        "editor_content": {
            "headline": result.get("headline", ""),
            "content": result.get("content", ""),
            "keywords": result.get("keywords", ""),
            "article_id": result.get("article_id") or article_id,
            "linked_resources": result.get("linked_resources", []),
            "action": _get_editor_action(action),
            "timestamp": datetime.utcnow().isoformat()
        },
        "selected_agent": "analyst",
        "routing_reason": f"Content generation: {action}",
        "is_final": True
    }

    # Add navigation action to open editor for new articles
    result_article_id = result.get("article_id") or article_id
    if result_article_id and action == "create":
        response["ui_action"] = {
            "type": "goto",
            "params": {
                "section": "analyst_editor",
                "topic": topic,
                "article_id": result_article_id
            }
        }

    return response


def _handle_resource_action(
    action_type: str,
    details: Dict[str, Any],
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any],
    topic: Optional[str]
) -> Dict[str, Any]:
    """Handle resource actions via resource sub-graph."""
    action_config = ANALYST_UI_ACTIONS.get(action_type, {})
    resource_action = action_config.get("resource_action", "browse")

    article_id = details.get("article_id") or nav_context.get("article_id")
    resource_id = details.get("resource_id") or nav_context.get("resource_id")
    query = details.get("query", "")

    # Invoke resource sub-graph
    result = invoke_resource_action(
        action=resource_action,
        topic=topic or "",
        user_context=user_context,
        article_id=article_id,
        resource_id=resource_id,
        query=query
    )

    if not result.get("success"):
        return {
            "response_text": f"Resource action failed: {result.get('error', 'Unknown error')}",
            "selected_agent": "analyst",
            "error": result.get("error"),
            "is_final": True
        }

    # Build response based on action
    response = {
        "response_text": result.get("message", f"Completed {resource_action} action."),
        "selected_agent": "analyst",
        "routing_reason": f"Resource action: {resource_action}",
        "is_final": True
    }

    # Include resources list for browse/query
    if result.get("resources"):
        resources_list = result["resources"]
        if resources_list:
            resources_text = "\n".join([
                f"- **{r['name']}** (#{r['id']}): {r.get('description', '')[:50]}..."
                for r in resources_list[:10]
            ])
            response["response_text"] += f"\n\n**Available Resources:**\n{resources_text}"

    # Include UI action for modal/selection
    if action_type in ["browse_resources", "open_resource_modal"]:
        response["ui_action"] = {
            "type": "open_resource_modal",
            "params": {"topic": topic, "article_id": article_id}
        }
    elif result.get("resource_info"):
        response["ui_action"] = {
            "type": action_type,
            "params": {
                "article_id": article_id,
                "resource_id": resource_id,
                "resource_info": result["resource_info"]
            }
        }

    return response


def _handle_analyst_ui_action(
    action_type: str,
    details: Dict[str, Any],
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any],
    topic: Optional[str]
) -> Dict[str, Any]:
    """Handle analyst-specific UI actions."""
    action_config = ANALYST_UI_ACTIONS.get(action_type, {})
    params = _extract_params(details, nav_context)

    # Validate article access if required
    if action_config.get("requires_article"):
        article_id = params.get("article_id")
        if not article_id:
            return {
                "response_text": "Please specify an article for this action.",
                "selected_agent": "analyst",
                "is_final": True
            }

        try:
            from database import SessionLocal
            db = SessionLocal()
            try:
                allowed, error_msg, article_info = validate_article_access(
                    article_id, user_context, db, topic
                )
                if not allowed:
                    return {
                        "response_text": error_msg,
                        "selected_agent": "analyst",
                        "is_final": True
                    }
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Article access validation failed: {e}")

    # Handle submission actions
    if action_type in ["submit_for_review", "submit_article"]:
        return _handle_submit_for_review(params.get("article_id"), topic, user_context)

    # Build response
    response_text = _build_analyst_action_response(action_type, params)

    return {
        "response_text": response_text,
        "ui_action": {
            "type": action_type,
            "params": params
        },
        "selected_agent": "analyst",
        "routing_reason": f"Analyst action: {action_type}",
        "is_final": True
    }


def _handle_submit_for_review(
    article_id: Optional[int],
    topic: Optional[str],
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle article submission for review."""
    if not article_id:
        return {
            "response_text": "Which article would you like to submit for review?",
            "selected_agent": "analyst",
            "is_final": True
        }

    try:
        from agents.shared.article_query_agent import ArticleQueryAgent
        from database import SessionLocal
        from langchain_openai import ChatOpenAI
        import os

        db = SessionLocal()
        try:
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
                    "selected_agent": "analyst",
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
                    "params": {"article_id": article_id, "new_status": "editor"}
                },
                "selected_agent": "analyst",
                "routing_reason": f"Submitted article #{article_id}",
                "is_final": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Submit for review failed: {e}")
        return {
            "response_text": f"Submission failed: {str(e)}",
            "selected_agent": "analyst",
            "error": str(e),
            "is_final": True
        }


def _handle_analyst_chat(
    messages: List,
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any],
    topic: Optional[str]
) -> Dict[str, Any]:
    """Handle general chat in analyst context."""
    if not messages:
        topic_display = topic.replace("_", " ").title() if topic else "your selected topic"
        return {
            "response_text": f"""You're in the analyst hub for **{topic_display}**.

**What would you like to do?**
- Write a new article: "Write an article about..."
- Edit existing draft: "Edit article #123"
- Browse resources: "Show me available resources"
- Submit for review: "Submit this article"

How can I help you today?""",
            "selected_agent": "analyst",
            "is_final": True
        }

    user_query = messages[-1].content

    # Check if it looks like a content request
    if _looks_like_content_request(user_query):
        return _handle_content_generation(
            {"intent": {"details": {"action": "create"}}, "messages": messages,
             "user_context": user_context, "navigation_context": nav_context},
            topic, user_context, nav_context, messages
        )

    return {
        "response_text": "I can help you with content creation and article management. "
                       "What would you like to write about?",
        "selected_agent": "analyst",
        "is_final": True
    }


# =============================================================================
# Helper Functions
# =============================================================================

def _infer_analyst_action(message: str) -> Optional[str]:
    """Infer analyst action from message."""
    message_lower = message.lower()

    # Content regeneration - check BEFORE generic "write/create/generate" to avoid false matches
    # More specific patterns must be checked first
    if any(w in message_lower for w in ["rephrase headline", "new headline", "better headline"]):
        return "regenerate_headline"
    if any(w in message_lower for w in ["regenerate keywords", "new keywords", "better keywords"]):
        return "regenerate_keywords"
    if any(w in message_lower for w in ["rewrite", "regenerate content", "rewrite content"]):
        return "regenerate_content"

    # Content creation - check AFTER specific regeneration patterns
    if any(w in message_lower for w in ["write", "create", "draft", "generate"]):
        return "create"

    # UI actions
    if "save" in message_lower:
        return "save_draft"
    if "submit" in message_lower:
        return "submit_for_review"
    if "preview" in message_lower:
        return "switch_view_preview"
    if "resource" in message_lower:
        if "add" in message_lower:
            return "add_resource"
        if "remove" in message_lower:
            return "remove_resource"
        return "browse_resources"

    return None


def _looks_like_content_request(query: str) -> bool:
    """Check if query looks like a content generation request."""
    query_lower = query.lower()
    content_indicators = [
        "write", "create", "draft", "generate", "article about",
        "analysis of", "report on", "piece about", "content about"
    ]
    return any(indicator in query_lower for indicator in content_indicators)


def _extract_content_request(query: str, nav_context: Dict[str, Any]) -> str:
    """Extract content request from query."""
    prefixes = [
        "write an article about", "write about", "generate content about",
        "create an article about", "draft an article about",
        "write me", "generate", "create", "draft", "write"
    ]

    query_lower = query.lower().strip()
    for prefix in prefixes:
        if query_lower.startswith(prefix):
            query = query[len(prefix):].strip()
            break

    if len(query) < 10:
        headline = nav_context.get("article_headline", "")
        keywords = nav_context.get("article_keywords", "")
        if headline:
            query = f"Article about: {headline}"
            if keywords:
                query += f". Keywords: {keywords}"

    return query


def _infer_topic_from_query(query: str) -> Optional[str]:
    """Infer topic from query."""
    from agents.shared.topic_manager import infer_topic
    return infer_topic(query)


def _get_article_content(article_id: int) -> str:
    """Get article content from database."""
    try:
        from database import SessionLocal
        from models import ContentArticle

        db = SessionLocal()
        try:
            article = db.query(ContentArticle).filter(
                ContentArticle.id == article_id
            ).first()
            return article.content if article else ""
        finally:
            db.close()
    except Exception:
        return ""


def _get_editor_action(action: str) -> str:
    """Map content action to editor action for frontend."""
    action_map = {
        "create": "fill",
        "regenerate_headline": "update_headline",
        "regenerate_keywords": "update_keywords",
        "regenerate_content": "update_content",
        "edit_section": "update_content",
        "refine_content": "update_content",
    }
    return action_map.get(action, "fill")


def _build_content_response(
    result: Dict[str, Any],
    action: str,
    topic: str,
    article_id: Optional[int]
) -> str:
    """Build response text for content generation."""
    if action == "regenerate_headline":
        return f"I've generated a new headline:\n\n**{result.get('headline', '')}**"

    if action == "regenerate_keywords":
        return f"I've generated new keywords:\n\n**{result.get('keywords', '')}**"

    if action == "regenerate_content":
        word_count = len(result.get("content", "").split())
        return f"I've rewritten the article content.\n\n**Word count:** ~{word_count} words"

    if action == "edit_section":
        section_edited = result.get("section_edited", "requested section")
        word_count = len(result.get("content", "").split())
        return (f"I've edited the **{section_edited}**.\n\n"
                f"**Word count:** ~{word_count} words\n\n"
                f"The rest of the article remains unchanged.")

    if action == "refine_content":
        refinement = result.get("refinement_applied", "your requested changes")
        word_count = len(result.get("content", "").split())
        return (f"I've applied **{refinement}** to the article.\n\n"
                f"**Word count:** ~{word_count} words")

    # Default: create
    headline = result.get("headline", "Untitled")
    word_count = len(result.get("content", "").split())
    return (f"I've drafted a new article for {topic}.\n\n"
            f"**Headline:** {headline}\n"
            f"**Word count:** ~{word_count} words\n\n"
            f"Opening the article editor so you can review and edit.")


def _extract_params(details: Dict[str, Any], nav_context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract parameters from details and nav_context."""
    params = {}

    for key in ["article_id", "resource_id", "topic", "view", "tab"]:
        if details.get(key):
            params[key] = details[key]
        elif nav_context.get(key):
            params[key] = nav_context[key]

    return params


def _build_analyst_action_response(action_type: str, params: Dict[str, Any]) -> str:
    """Build response for analyst UI actions."""
    topic = params.get("topic")
    topic_display = topic.replace("_", " ").title() if topic else None
    article_id = params.get("article_id")

    responses = {
        "save_draft": "Saving your draft...",
        "edit_article": f"Opening article #{article_id} in the editor...",
        "create_new_article": f"Creating new article{' for ' + topic_display if topic_display else ''}...",
        "switch_view_editor": "Switching to editor view.",
        "switch_view_preview": "Switching to preview mode.",
        "switch_view_resources": "Showing resources panel.",
        "open_resource_modal": "Opening resource selection...",
        "select_resource": f"Selecting resource #{params.get('resource_id', '')}.",
    }

    return responses.get(action_type, f"Executing {action_type}...")
