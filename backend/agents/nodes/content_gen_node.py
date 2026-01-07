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
    Handle content generation requests.

    This node:
    1. Checks if user has analyst permission for the topic
    2. Determines the topic and article context
    3. Delegates to AnalystAgent for content generation
    4. Returns generated content with editor_content metadata

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

    # Get the user's query
    user_query = messages[-1].content if messages else ""

    # Determine topic
    topic = details.get("topic") or nav_context.get("topic")
    if not topic:
        topic = _infer_topic_from_query(user_query)

    if not topic:
        return {
            "response_text": "Which topic would you like to write about? "
                           "Please specify: macro, equity, fixed_income, or esg.",
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

    # Extract what the user wants to write about
    content_request = _extract_content_request(user_query, nav_context)

    # Generate content using LLM
    try:
        generated = _generate_content(
            query=content_request,
            topic=topic,
            article_id=article_id,
            user_context=user_context,
            nav_context=nav_context
        )

        if generated.get("error"):
            return {
                "response_text": f"Content generation failed: {generated['error']}",
                "selected_agent": "content_generation",
                "error": generated["error"],
                "is_final": True
            }

        # Build success response
        response_text = _build_generation_response(generated, topic, article_id)

        return {
            "response_text": response_text,
            "editor_content": {
                "headline": generated.get("headline", ""),
                "content": generated.get("content", ""),
                "keywords": generated.get("keywords", ""),
                "article_id": article_id,
                "linked_resources": generated.get("linked_resources", []),
                "action": "fill",  # Fill empty fields only
                "timestamp": _get_timestamp()
            },
            "navigation": _build_editor_navigation(topic, article_id) if not article_id else None,
            "selected_agent": "content_generation",
            "routing_reason": f"Content generation for {topic}",
            "is_final": True
        }

    except Exception as e:
        logger.exception(f"Content generation failed: {e}")
        return {
            "response_text": f"Sorry, content generation encountered an error: {str(e)}",
            "selected_agent": "content_generation",
            "error": str(e),
            "is_final": True
        }


def _infer_topic_from_query(query: str) -> Optional[str]:
    """Infer topic from the content generation query."""
    query_lower = query.lower()

    topic_keywords = {
        "macro": ["economy", "economic", "gdp", "inflation", "fed", "interest rate",
                  "monetary", "fiscal", "unemployment", "growth"],
        "equity": ["stock", "equity", "company", "earnings", "market cap",
                   "valuation", "p/e", "dividend", "shares"],
        "fixed_income": ["bond", "yield", "credit", "treasury", "debt",
                        "fixed income", "coupon", "maturity", "duration"],
        "esg": ["esg", "sustainability", "climate", "environmental", "social",
                "governance", "carbon", "renewable", "impact"]
    }

    for topic, keywords in topic_keywords.items():
        if any(kw in query_lower for kw in keywords):
            return topic

    return None


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
    use_celery: bool = False
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
        use_celery: If True, queue task for background processing

    Returns:
        Dict with generated content or task info
    """
    try:
        if use_celery:
            # Queue heavy research task on Celery worker
            from tasks.agent_tasks import analyst_research_task

            user_id = user_context.get("user_id", 0)
            task = analyst_research_task.delay(
                user_id=user_id,
                topic=topic,
                query=query,
                article_id=article_id
            )

            return {
                "async": True,
                "task_id": task.id,
                "message": "Research task queued. You'll be notified when complete.",
                "headline": f"Researching: {query[:50]}...",
                "content": "",
                "keywords": topic,
            }

        # Synchronous execution using AnalystAgent directly
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
                article_id=article_id
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
    topic_descriptions = {
        "macro": "macroeconomic analysis, covering topics like GDP, inflation, "
                 "interest rates, monetary policy, and economic indicators",
        "equity": "equity market analysis, covering stocks, company valuations, "
                  "earnings, market trends, and investment opportunities",
        "fixed_income": "fixed income analysis, covering bonds, yields, credit "
                        "markets, treasury securities, and debt instruments",
        "esg": "ESG (Environmental, Social, Governance) analysis, covering "
               "sustainability, climate risks, corporate governance, and impact investing"
    }

    prompt = f"""You are a professional financial analyst and writer specializing in {topic_descriptions.get(topic, topic)}.

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
                f"The content has been sent to the editor. "
                f"You can review and edit it there.")
    else:
        return (f"I've drafted a new article for {topic}.\n\n"
                f"**Headline:** {headline}\n"
                f"**Word count:** ~{word_count} words\n\n"
                f"Click 'Create New Article' in the analyst hub to start editing.")


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
