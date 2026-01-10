"""
Content Generation node for the main chat graph.

This node handles content generation requests - when users ask to write,
draft, or generate article content. It delegates to the AnalystAgent for
the actual research and writing work.
"""

from typing import Dict, Any, Optional
import logging
import os

from langchain_openai import ChatOpenAI

from agents.state import AgentState
from agents.permission_utils import validate_article_access

logger = logging.getLogger(__name__)


# Role hierarchy for permission checking
ROLE_HIERARCHY = {
    "reader": 1,
    "editor": 2,
    "analyst": 3,
    "admin": 4
}


def content_generation_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle content generation and editing requests.

    This node:
    1. Checks if user has analyst permission for the topic
    2. Determines the action type (create, regenerate_headline, regenerate_keywords, regenerate_content)
    3. For regenerate actions, uses existing content from nav_context or database
    4. Delegates to appropriate handler for the action
    5. Returns generated content with editor_content metadata

    Args:
        state: Current agent state with messages and context

    Returns:
        Updated state with response_text, editor_content, and is_final=True
    """
    intent = state.get("intent", {})
    details = intent.get("details", {})
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})
    messages = state.get("messages", [])

    # Determine the action type
    action = details.get("action", "create")

    # Get the user's query
    user_query = messages[-1].content if messages else ""

    # Check role context - readers should be guided to analyst dashboard first
    current_role = nav_context.get("role", "reader")
    if current_role == "reader":
        # Check if user has analyst permission for any topic
        topic_roles = user_context.get("topic_roles", {})
        highest_role = user_context.get("highest_role", "reader")
        has_analyst_access = highest_role in ["analyst", "editor", "admin"] or \
                            any(r in ["analyst", "editor", "admin"] for r in topic_roles.values())

        if has_analyst_access:
            # Guide them to analyst dashboard
            topic = details.get("topic") or nav_context.get("topic")
            return {
                "response_text": "I'll take you to the analyst dashboard first, where you can create and manage articles.",
                "navigation": {
                    "action": "navigate",
                    "target": f"/analyst/{topic}" if topic else "/analyst",
                    "params": {"section": "analyst", "topic": topic}
                },
                "selected_agent": "content_generation",
                "routing_reason": "Reader context - redirecting to analyst dashboard",
                "is_final": True
            }
        else:
            return {
                "response_text": "You don't have permission to create articles. "
                               "Please contact an administrator if you need analyst access.",
                "selected_agent": "content_generation",
                "is_final": True
            }

    # Determine topic
    topic = details.get("topic") or nav_context.get("topic")
    if not topic:
        topic = _infer_topic_from_query(user_query)

    if not topic:
        # Get available topics from database dynamically
        from agents.topic_manager import get_available_topics
        available_topics = get_available_topics()
        topics_list = ", ".join(available_topics) if available_topics else "no topics available"

        # Build a contextual response that acknowledges what the user asked
        query_preview = user_query[:100] + "..." if len(user_query) > 100 else user_query

        return {
            "response_text": f"I'd be happy to help you write about **\"{query_preview}\"**.\n\n"
                           f"Which topic should this article be filed under? "
                           f"Please specify one of: {topics_list}.",
            "selected_agent": "content_generation",
            "is_final": True
        }

    # Check analyst permission for topic
    permission_result = _check_analyst_permission(topic, user_context)
    if not permission_result["allowed"]:
        return {
            "response_text": permission_result["message"],
            "selected_agent": "content_generation",
            "is_final": True
        }

    # Get article context
    article_id = details.get("article_id") or nav_context.get("article_id")

    # Validate article access if article_id is provided
    if article_id:
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
                        "selected_agent": "content_generation",
                        "is_final": True
                    }
                # Update topic from article if not set
                if not topic and article_info:
                    topic = article_info.get("topic")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Article access validation failed: {e}")

    # Route based on action type
    if action == "regenerate_headline":
        return _handle_regenerate_headline(topic, article_id, nav_context, user_context)
    elif action == "regenerate_keywords":
        return _handle_regenerate_keywords(topic, article_id, nav_context, user_context)
    elif action == "regenerate_content":
        return _handle_regenerate_content(topic, article_id, nav_context, user_context, user_query)

    # Default: create new content
    # Extract what the user wants to write about
    content_request = _extract_content_request(user_query, nav_context)

    # Generate content using LLM
    try:
        generated = _generate_content(
            query=content_request,
            topic=topic,
            article_id=article_id,
            user_context=user_context,
            nav_context=nav_context,
            messages=messages  # Pass conversation history
        )

        if generated.get("error"):
            return {
                "response_text": f"Content generation failed: {generated['error']}",
                "selected_agent": "content_generation",
                "error": generated["error"],
                "is_final": True
            }

        # Build success response
        # Use the article_id from generated result (new article) or the original article_id (existing)
        result_article_id = generated.get("article_id") or article_id
        response_text = _build_generation_response(generated, topic, result_article_id)

        result = {
            "response_text": response_text,
            "editor_content": {
                "headline": generated.get("headline", ""),
                "content": generated.get("content", ""),
                "keywords": generated.get("keywords", ""),
                "article_id": result_article_id,
                "linked_resources": generated.get("linked_resources", []),
                "action": "fill",  # Fill empty fields only
                "timestamp": _get_timestamp()
            },
            "selected_agent": "content_generation",
            "routing_reason": f"Content generation for {topic}",
            "is_final": True
        }

        # Add UI action to open the article editor if we have an article_id
        if result_article_id:
            result["ui_action"] = {
                "type": "edit_article",
                "params": {
                    "article_id": result_article_id,
                    "topic": topic
                }
            }

        return result

    except Exception as e:
        logger.exception(f"Content generation failed: {e}")
        return {
            "response_text": f"Sorry, content generation encountered an error: {str(e)}",
            "selected_agent": "content_generation",
            "error": str(e),
            "is_final": True
        }


def _handle_regenerate_headline(
    topic: str,
    article_id: Optional[int],
    nav_context: Dict[str, Any],
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle request to regenerate/rephrase the headline.

    Uses existing content and keywords to generate a new headline.
    """
    # Get existing content from nav_context or database
    existing_headline = nav_context.get("article_headline", "")
    existing_keywords = nav_context.get("article_keywords", "")

    # Need content to generate a good headline - try to get from database if we have article_id
    existing_content = ""
    if article_id:
        try:
            from database import SessionLocal
            from models import Article
            db = SessionLocal()
            try:
                article = db.query(Article).filter(Article.id == article_id).first()
                if article:
                    existing_content = article.content or ""
                    if not existing_headline:
                        existing_headline = article.headline or ""
                    if not existing_keywords:
                        existing_keywords = article.keywords or ""
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Could not fetch article content: {e}")

    # Allow rephrasing if we have ANY context: headline, content, or keywords
    if not existing_content and not existing_keywords and not existing_headline:
        return {
            "response_text": "I need existing content, keywords, or a headline to generate a new headline. "
                           "Please provide some context first.",
            "selected_agent": "content_generation",
            "is_final": True
        }

    try:
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        # Build prompt for headline generation
        prompt_parts = [f"Generate a compelling, professional headline for a {topic} research article."]
        if existing_keywords:
            prompt_parts.append(f"Keywords: {existing_keywords}")
        if existing_content:
            # Use first 1000 chars of content
            content_excerpt = existing_content[:1000]
            prompt_parts.append(f"Content excerpt: {content_excerpt}")
        if existing_headline:
            prompt_parts.append(f"Current headline (rephrase differently): {existing_headline}")

        prompt_parts.append("\nGenerate a new headline (max 100 characters):")

        response = llm.invoke([
            {"role": "system", "content": "You are a professional financial editor. Generate concise, engaging headlines."},
            {"role": "user", "content": "\n".join(prompt_parts)}
        ])

        new_headline = response.content.strip().strip('"\'')[:100]

        return {
            "response_text": f"I've generated a new headline for your article:\n\n**{new_headline}**",
            "editor_content": {
                "headline": new_headline,
                "article_id": article_id,
                "action": "update_headline",
                "timestamp": _get_timestamp()
            },
            "selected_agent": "content_generation",
            "routing_reason": "Headline regeneration",
            "is_final": True
        }

    except Exception as e:
        logger.exception(f"Headline regeneration failed: {e}")
        return {
            "response_text": f"Sorry, headline generation failed: {str(e)}",
            "selected_agent": "content_generation",
            "error": str(e),
            "is_final": True
        }


def _handle_regenerate_keywords(
    topic: str,
    article_id: Optional[int],
    nav_context: Dict[str, Any],
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle request to regenerate keywords from headline, content, or existing keywords.

    Uses existing headline, content, and/or keywords to generate new comma-separated keywords.
    """
    existing_headline = nav_context.get("article_headline", "")
    existing_keywords = nav_context.get("article_keywords", "")
    existing_content = ""

    # Try to get content from database if we have article_id
    if article_id:
        try:
            from database import SessionLocal
            from models import Article
            db = SessionLocal()
            try:
                article = db.query(Article).filter(Article.id == article_id).first()
                if article:
                    existing_content = article.content or ""
                    if not existing_headline:
                        existing_headline = article.headline or ""
                    if not existing_keywords:
                        existing_keywords = article.keywords or ""
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Could not fetch article content: {e}")

    # Allow regeneration if we have ANY context: headline, content, or keywords
    if not existing_headline and not existing_content and not existing_keywords:
        return {
            "response_text": "I need a headline, content, or existing keywords to generate new keywords. "
                           "Please provide some context first.",
            "selected_agent": "content_generation",
            "is_final": True
        }

    try:
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.3,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        # Use first 1500 chars of content
        content_excerpt = existing_content[:1500] if existing_content else ""

        # Build prompt parts based on available context
        prompt_parts = [f"Generate 5-8 relevant keywords for a {topic} article."]
        if existing_headline:
            prompt_parts.append(f"Headline: {existing_headline}")
        if content_excerpt:
            prompt_parts.append(f"Content excerpt: {content_excerpt}")
        if existing_keywords:
            prompt_parts.append(f"Current keywords (generate different alternatives): {existing_keywords}")
        prompt_parts.append("\nReturn only comma-separated keywords, no explanation:")

        response = llm.invoke([
            {"role": "system", "content": "You are a professional financial editor. Generate relevant, SEO-friendly keywords."},
            {"role": "user", "content": "\n".join(prompt_parts)}
        ])

        new_keywords = response.content.strip()

        return {
            "response_text": f"I've generated new keywords for your article:\n\n**{new_keywords}**",
            "editor_content": {
                "keywords": new_keywords,
                "article_id": article_id,
                "action": "update_keywords",
                "timestamp": _get_timestamp()
            },
            "selected_agent": "content_generation",
            "routing_reason": "Keyword regeneration",
            "is_final": True
        }

    except Exception as e:
        logger.exception(f"Keyword regeneration failed: {e}")
        return {
            "response_text": f"Sorry, keyword generation failed: {str(e)}",
            "selected_agent": "content_generation",
            "error": str(e),
            "is_final": True
        }


def _handle_regenerate_content(
    topic: str,
    article_id: Optional[int],
    nav_context: Dict[str, Any],
    user_context: Dict[str, Any],
    user_query: str
) -> Dict[str, Any]:
    """
    Handle request to rewrite/regenerate article content.

    Uses existing headline and keywords as context for the new content.
    """
    existing_headline = nav_context.get("article_headline", "")
    existing_keywords = nav_context.get("article_keywords", "")
    existing_content = ""

    # Try to get existing content from database
    if article_id:
        try:
            from database import SessionLocal
            from models import Article
            db = SessionLocal()
            try:
                article = db.query(Article).filter(Article.id == article_id).first()
                if article:
                    existing_content = article.content or ""
                    if not existing_headline:
                        existing_headline = article.headline or ""
                    if not existing_keywords:
                        existing_keywords = article.keywords or ""
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Could not fetch article: {e}")

    if not existing_headline:
        return {
            "response_text": "I need at least a headline to rewrite the content. "
                           "Please provide a headline first.",
            "selected_agent": "content_generation",
            "is_final": True
        }

    try:
        # Get user's content tonality preference
        tonality = user_context.get("content_tonality_text", "")

        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        # Build system prompt
        system_prompt = f"""You are a professional financial analyst and writer specializing in {topic}.

Your task is to rewrite/regenerate article content. The content should be:
- Well-researched and accurate
- Professionally written
- Structured with clear sections
- Suitable for a professional finance audience

{f'Writing style preference: {tonality}' if tonality else ''}"""

        # Build user prompt with existing context
        user_prompt = f"""Please rewrite the content for this article:

Headline: {existing_headline}
Keywords: {existing_keywords}
Topic: {topic}

{f'Previous content to improve upon: {existing_content[:2000]}...' if existing_content else ''}

{f'Additional instructions: {user_query}' if 'rewrite' not in user_query.lower()[:20] else ''}

Write a comprehensive, well-structured article in markdown format.
Include sections like Executive Summary, Key Findings, Analysis, and Conclusion."""

        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        new_content = response.content

        word_count = len(new_content.split())

        return {
            "response_text": f"I've rewritten the article content.\n\n"
                           f"**Headline:** {existing_headline}\n"
                           f"**Word count:** ~{word_count} words\n\n"
                           f"The new content has been sent to the editor.",
            "editor_content": {
                "content": new_content,
                "article_id": article_id,
                "action": "update_content",
                "timestamp": _get_timestamp()
            },
            "selected_agent": "content_generation",
            "routing_reason": "Content regeneration",
            "is_final": True
        }

    except Exception as e:
        logger.exception(f"Content regeneration failed: {e}")
        return {
            "response_text": f"Sorry, content regeneration failed: {str(e)}",
            "selected_agent": "content_generation",
            "error": str(e),
            "is_final": True
        }


def _infer_topic_from_query(query: str) -> Optional[str]:
    """Infer topic from the content generation query using dynamic TopicManager."""
    from agents.topic_manager import infer_topic
    return infer_topic(query)


def _check_analyst_permission(topic: str, user_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check if user has analyst permission for the specific topic.

    Permission model:
    - global:admin - Can access all topics
    - {topic}:admin - Can access specific topic with admin rights
    - {topic}:analyst - Can create/edit content for specific topic

    IMPORTANT: Having analyst role on one topic does NOT grant access to other topics.
    """
    scopes = user_context.get("scopes", [])
    topic_roles = user_context.get("topic_roles", {})

    # Global admin can do anything
    if "global:admin" in scopes:
        return {"allowed": True}

    # Check topic-specific permissions in scopes
    # Must have explicit permission for THIS topic
    if f"{topic}:analyst" in scopes or f"{topic}:admin" in scopes:
        return {"allowed": True}

    # Check topic_roles dict (parsed from scopes)
    topic_role = topic_roles.get(topic)
    if topic_role and ROLE_HIERARCHY.get(topic_role, 0) >= ROLE_HIERARCHY["analyst"]:
        return {"allowed": True}

    # Explicit denial - having analyst on another topic doesn't help
    # Get user's available topics for helpful message
    available_topics = [
        t for t, r in topic_roles.items()
        if ROLE_HIERARCHY.get(r, 0) >= ROLE_HIERARCHY["analyst"]
    ]

    if available_topics:
        topics_str = ", ".join(available_topics)
        return {
            "allowed": False,
            "message": f"You don't have analyst access for **{topic}**. "
                       f"You can create content for: {topics_str}."
        }

    return {
        "allowed": False,
        "message": f"You need analyst access for **{topic}** to generate content. "
                   "Contact an administrator to request access."
    }


def _extract_content_request(query: str, nav_context: Dict[str, Any]) -> str:
    """Extract the content request from user query."""
    # Remove common prefixes
    prefixes_to_remove = [
        "write an article about",
        "write about",
        "generate content about",
        "create an article about",
        "draft an article about",
        "write me",
        "generate",
        "create",
        "draft",
        "write"
    ]

    query_lower = query.lower().strip()
    for prefix in prefixes_to_remove:
        if query_lower.startswith(prefix):
            query = query[len(prefix):].strip()
            break

    # If query is too short, use article context
    if len(query) < 10:
        headline = nav_context.get("article_headline", "")
        keywords = nav_context.get("article_keywords", "")
        if headline:
            query = f"Article about: {headline}"
            if keywords:
                query += f". Keywords: {keywords}"

    return query


def _generate_content(
    query: str,
    topic: str,
    article_id: Optional[int],
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any],
    messages: Optional[list] = None
) -> Dict[str, Any]:
    """
    Generate article content using AnalystAgent.

    This properly delegates to the AnalystAgent for full research capabilities:
    - Web search for current information
    - Data download for financial metrics
    - Resource queries for existing content
    - Article creation/update

    Args:
        query: The content generation query
        topic: Topic slug
        article_id: Optional existing article to update
        user_context: User context for permissions
        nav_context: Navigation context
        messages: Optional list of previous messages for context

    Returns:
        Dict with generated content
    """
    # Convert messages to conversation history format
    conversation_history = []
    if messages:
        for msg in messages[-10:]:  # Last 10 messages
            role = "assistant" if hasattr(msg, 'type') and msg.type == "ai" else "user"
            content = msg.content if hasattr(msg, 'content') else str(msg)
            conversation_history.append({"role": role, "content": content})

    try:
        # Use AnalystAgent directly
        from agents.analyst_agent import AnalystAgent
        from database import SessionLocal

        # Get database session
        db = SessionLocal()

        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0.7,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            agent = AnalystAgent(topic=topic, llm=llm, db=db)

            # Run the full research and write workflow
            result = agent.research_and_write(
                query=query,
                user_context=user_context,
                article_id=article_id,
                conversation_history=conversation_history
            )

            if not result.get("success", True):
                return {"error": result.get("error", "Research failed")}

            return {
                "headline": result.get("headline", ""),
                "content": result.get("content", ""),
                "keywords": result.get("keywords", topic),
                "article_id": result.get("article_id"),
                "linked_resources": result.get("resources_attached", []),
            }

        finally:
            db.close()

    except ImportError as e:
        logger.warning(f"AnalystAgent not available, using fallback: {e}")
        return _generate_content_fallback(query, topic, user_context, nav_context)

    except Exception as e:
        logger.exception(f"Content generation failed: {e}")
        return {"error": str(e)}


def _generate_content_fallback(
    query: str,
    topic: str,
    user_context: Dict[str, Any],
    nav_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Fallback content generation using direct LLM call.

    Used when AnalystAgent is not available or for quick drafts.
    """
    # Get user's content tonality preference
    tonality = user_context.get("content_tonality_text", "")

    # Build the generation prompt
    system_prompt = _build_system_prompt(topic, tonality)
    user_prompt = _build_user_prompt(query, nav_context)

    try:
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        return _parse_generated_content(response.content, query)

    except Exception as e:
        logger.exception(f"Fallback content generation failed: {e}")
        return {"error": str(e)}


def _build_system_prompt(topic: str, tonality: str) -> str:
    """Build system prompt for content generation."""
    # Get topic description from database dynamically
    from agents.topic_manager import get_topic_config
    topic_config = get_topic_config(topic)
    topic_description = topic_config.description if topic_config and topic_config.description else topic

    prompt = f"""You are a professional financial analyst and writer specializing in {topic_description}.

Your task is to generate high-quality article content for publication. The content should be:
- Well-researched and accurate
- Professionally written
- Structured with clear sections
- Suitable for a professional finance audience

{f'Writing style preference: {tonality}' if tonality else ''}

When generating content, provide:
1. A compelling headline (on a line starting with "HEADLINE:")
2. Keywords for SEO (on a line starting with "KEYWORDS:")
3. The article content in markdown format

Format your response exactly as:
HEADLINE: Your headline here
KEYWORDS: keyword1, keyword2, keyword3
CONTENT:
Your article content in markdown format here...
"""
    return prompt


def _build_user_prompt(query: str, nav_context: Dict[str, Any]) -> str:
    """Build user prompt for content generation."""
    # Include existing article context if available
    existing_headline = nav_context.get("article_headline", "")
    existing_keywords = nav_context.get("article_keywords", "")

    prompt = f"Please write an article about: {query}"

    if existing_headline:
        prompt += f"\n\nExisting headline: {existing_headline}"
    if existing_keywords:
        prompt += f"\nExisting keywords: {existing_keywords}"

    prompt += "\n\nGenerate the content now."

    return prompt


def _parse_generated_content(content: str, original_query: str) -> Dict[str, Any]:
    """Parse the generated content into structured format."""
    result = {
        "headline": "",
        "keywords": "",
        "content": "",
        "linked_resources": []
    }

    lines = content.split("\n")
    in_content = False
    content_lines = []

    for line in lines:
        line_stripped = line.strip()

        if line_stripped.upper().startswith("HEADLINE:"):
            result["headline"] = line_stripped[9:].strip()
        elif line_stripped.upper().startswith("KEYWORDS:"):
            result["keywords"] = line_stripped[9:].strip()
        elif line_stripped.upper().startswith("CONTENT:"):
            in_content = True
        elif in_content:
            content_lines.append(line)

    result["content"] = "\n".join(content_lines).strip()

    # Fallback if parsing failed
    if not result["headline"]:
        # Generate headline from query
        result["headline"] = original_query[:100].title()

    if not result["content"]:
        # Use full response as content
        result["content"] = content

    return result


def _build_generation_response(generated: Dict[str, Any], topic: str, article_id: Optional[int]) -> str:
    """Build user-friendly response for generated content."""
    headline = generated.get("headline", "Untitled")
    word_count = len(generated.get("content", "").split())

    if article_id:
        return (f"I've generated content for your article.\n\n"
                f"**Headline:** {headline}\n"
                f"**Word count:** ~{word_count} words\n\n"
                f"Opening the article editor so you can review and edit before submitting.")
    else:
        return (f"I've drafted a new article for {topic}.\n\n"
                f"**Headline:** {headline}\n"
                f"**Word count:** ~{word_count} words\n\n"
                f"Opening the article editor so you can review and edit before submitting.")


def _build_editor_navigation(topic: str, article_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """Build navigation to the editor if no article context."""
    if article_id:
        return None  # Already in an article context

    return {
        "action": "navigate",
        "target": f"/analyst/{topic}",
        "params": {
            "topic": topic,
            "section": "analyst"
        }
    }


def _get_timestamp() -> str:
    """Get current ISO timestamp."""
    from datetime import datetime
    return datetime.utcnow().isoformat()
