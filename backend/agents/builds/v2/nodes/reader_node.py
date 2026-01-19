"""
Reader node for the main chat graph.

This node handles reader role context:
- Article viewing and browsing
- Search functionality
- Rating articles
- Topic selection
- PDF downloads
- General Q&A about articles

Routes based on nav_context.role == 'reader'
"""

from typing import Dict, Any, Optional, List
import logging
import os

from langchain_openai import ChatOpenAI

from agents.builds.v2.state import AgentState
from agents.shared.permission_utils import validate_article_access

logger = logging.getLogger(__name__)


# Reader UI actions
READER_UI_ACTIONS = {
    # Article viewing
    "open_article": {"requires_article": True},
    "view_article": {"requires_article": True},
    "focus_article": {"requires_article": True},
    "select_article": {"requires_article": True},
    # Search
    "search_articles": {},
    "clear_search": {},
    # Rating
    "rate_article": {"requires_article": True},
    # Topic selection
    "select_topic_tab": {},
    "select_topic": {},
    # Downloads
    "download_pdf": {"requires_article": True},
    # Modals
    "close_modal": {},
    "confirm_action": {},
    "cancel_action": {},
}


def reader_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle reader context requests.

    This node handles:
    1. Reader UI actions (view, search, rate, download)
    2. General Q&A about articles and content
    3. Article recommendations

    Args:
        state: Current agent state with messages and context

    Returns:
        Updated state with response and optional UI actions
    """
    intent = state.get("intent", {})
    intent_type = intent.get("intent_type", "")
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})
    messages = state.get("messages", [])

    # Check for UI action first
    action_type = details.get("action_type", "")
    if action_type in READER_UI_ACTIONS:
        return _handle_reader_ui_action(action_type, details, user_context, nav_context)

    # Infer action from message if UI action intent
    if intent_type == "ui_action":
        user_query = messages[-1].content if messages else ""
        inferred_action = _infer_reader_action(user_query)
        if inferred_action:
            return _handle_reader_ui_action(inferred_action, details, user_context, nav_context)

    # Handle general chat/Q&A for readers
    return _handle_reader_chat(messages, user_context, nav_context)


def _handle_reader_ui_action(
    action_type: str,
    details: Dict[str, Any],
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle reader-specific UI actions."""

    params = _extract_params(details, nav_context)
    action_config = READER_UI_ACTIONS.get(action_type, {})

    # Validate article access if required
    if action_config.get("requires_article") and params.get("article_id"):
        try:
            from database import SessionLocal
            db = SessionLocal()
            try:
                allowed, error_msg, article_info = validate_article_access(
                    params["article_id"], user_context, db, params.get("topic")
                )
                if not allowed:
                    return {
                        "response_text": error_msg,
                        "selected_agent": "reader",
                        "is_final": True
                    }
                if article_info and not params.get("topic"):
                    params["topic"] = article_info.get("topic")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Article access validation failed: {e}")

    # Build response based on action type
    response_text = _build_reader_action_response(action_type, params)

    return {
        "response_text": response_text,
        "ui_action": {
            "type": action_type,
            "params": params
        },
        "selected_agent": "reader",
        "routing_reason": f"Reader action: {action_type}",
        "is_final": True
    }


def _handle_reader_chat(
    messages: List,
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle general Q&A for readers.

    Uses RAG to answer questions about articles and content.
    """
    if not messages:
        return {
            "response_text": "How can I help you? You can ask me about articles, search for content, or navigate to different sections.",
            "selected_agent": "reader",
            "is_final": True
        }

    user_query = messages[-1].content if messages else ""
    topic = nav_context.get("topic")

    try:
        # Try to use vector search for relevant articles
        from services.vector_service import VectorService

        # Search for relevant content
        search_results = VectorService.search_articles(
            query=user_query,
            topic=topic,
            limit=5
        )

        if search_results:
            # Build context from search results
            context = _build_context_from_results(search_results)

            # Generate response using LLM
            response = _generate_reader_response(user_query, context, topic, user_context)

            # Include referenced articles
            referenced = [
                {"id": r.get("article_id"), "headline": r.get("headline"), "topic": r.get("topic", "")}
                for r in search_results[:3]
            ]

            return {
                "response_text": response,
                "referenced_articles": referenced,
                "selected_agent": "reader",
                "routing_reason": "Reader Q&A with RAG",
                "is_final": True
            }

    except Exception as e:
        logger.warning(f"RAG search failed: {e}")

    # Fallback: direct LLM response
    response = _generate_reader_response(user_query, "", topic, user_context)

    return {
        "response_text": response,
        "selected_agent": "reader",
        "routing_reason": "Reader Q&A",
        "is_final": True
    }


def _infer_reader_action(message: str) -> Optional[str]:
    """Infer reader action from message."""
    message_lower = message.lower()

    if any(w in message_lower for w in ["search", "find", "look for"]):
        return "search_articles"

    if any(w in message_lower for w in ["open", "view", "show me", "read"]):
        return "open_article"

    if any(w in message_lower for w in ["rate", "rating", "stars"]):
        return "rate_article"

    if any(w in message_lower for w in ["download", "pdf", "export"]):
        return "download_pdf"

    if any(w in message_lower for w in ["clear", "reset"]):
        return "clear_search"

    return None


def _extract_params(details: Dict[str, Any], nav_context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract parameters from details and nav_context."""
    params = {}

    # Article ID
    if details.get("article_id"):
        params["article_id"] = details["article_id"]
    elif nav_context.get("article_id"):
        params["article_id"] = nav_context["article_id"]

    # Topic
    if details.get("topic"):
        params["topic"] = details["topic"]
    elif nav_context.get("topic"):
        params["topic"] = nav_context["topic"]

    # Search query
    if details.get("search_query"):
        params["search_query"] = details["search_query"]

    # Rating
    if details.get("rating"):
        params["rating"] = details["rating"]

    # Tab
    if details.get("tab"):
        params["tab"] = details["tab"]

    return params


def _build_reader_action_response(action_type: str, params: Dict[str, Any]) -> str:
    """Build response message for reader actions."""
    topic = params.get("topic")
    topic_display = topic.replace("_", " ").title() if topic else None
    article_id = params.get("article_id")

    responses = {
        "open_article": f"Opening article{' #' + str(article_id) if article_id else ''}...",
        "view_article": f"Opening article{' #' + str(article_id) if article_id else ''}...",
        "focus_article": f"Focusing on article #{article_id}." if article_id else "Focusing on article.",
        "select_article": f"Selecting article #{article_id}." if article_id else "Select an article.",
        "search_articles": f"Searching{' for ' + params.get('search_query', '') if params.get('search_query') else ''}...",
        "clear_search": "Clearing search.",
        "rate_article": "Opening rating dialog...",
        "select_topic_tab": f"Switching to {topic_display or 'selected'} topic.",
        "select_topic": f"Selecting {topic_display or 'topic'}.",
        "download_pdf": "Generating PDF download...",
        "close_modal": "Closing dialog.",
        "confirm_action": "Confirming action...",
        "cancel_action": "Cancelling action.",
    }

    return responses.get(action_type, f"Executing {action_type}...")


def _build_context_from_results(results: List[Dict]) -> str:
    """Build context string from search results."""
    context_parts = []
    for i, result in enumerate(results[:3], 1):
        headline = result.get("headline", "")
        content = result.get("content", "")[:500]
        context_parts.append(f"Article {i}: {headline}\n{content}...")
    return "\n\n".join(context_parts)


def _generate_reader_response(
    query: str,
    context: str,
    topic: Optional[str],
    user_context: Dict[str, Any]
) -> str:
    """Generate response for reader queries using LLM."""
    try:
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        # Build system prompt
        topic_display = topic.replace("_", " ").title() if topic else "general"
        system_prompt = f"""You are a helpful assistant for a financial research platform.
You are helping a reader who is browsing {topic_display} articles.
Be concise, helpful, and professional.

If you have article context, use it to answer the question.
If asked about specific articles, reference them by headline.
For navigation questions, explain how to find content."""

        # Build user prompt with context
        user_prompt = query
        if context:
            user_prompt = f"""Based on these relevant articles:

{context}

User question: {query}

Provide a helpful response based on the articles above."""

        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        return response.content

    except Exception as e:
        logger.exception(f"Reader response generation failed: {e}")
        return f"I can help you browse and search articles. What would you like to know about?"
