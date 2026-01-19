"""
Article Content sub-graph for analyst workflows.

This is a LangGraph sub-graph that handles content generation:
- create: Create new article content
- regenerate_headline: Generate new headline preserving content
- regenerate_keywords: Generate new keywords from content
- regenerate_content: Full content rewrite
- edit_section: Edit a specific section (intro, conclusion, etc.) NEW
- refine_content: Apply style/tone refinement to content NEW

Used by analyst_node when content generation is needed.
"""

from typing import Dict, Any, Optional, TypedDict, List
import logging
import os

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


# =============================================================================
# Sub-graph State
# =============================================================================

class ArticleContentState(TypedDict, total=False):
    """State for article content sub-graph."""
    # Input
    action: str  # create, regenerate_headline, regenerate_keywords, regenerate_content, edit_section, refine_content
    query: str  # User's request or instruction for the action
    topic: str
    article_id: Optional[int]
    existing_headline: Optional[str]
    existing_keywords: Optional[str]
    existing_content: Optional[str]
    user_context: Dict[str, Any]
    conversation_history: List[Dict[str, str]]

    # Output
    headline: Optional[str]
    keywords: Optional[str]
    content: Optional[str]
    linked_resources: List[Dict]
    error: Optional[str]
    success: bool


# =============================================================================
# Sub-graph Nodes
# =============================================================================

def route_action_node(state: ArticleContentState) -> Dict[str, Any]:
    """Route to appropriate content action."""
    action = state.get("action", "create")
    return {"action": action}


def create_content_node(state: ArticleContentState) -> Dict[str, Any]:
    """Create new article content using AnalystAgent."""
    query = state.get("query", "")
    topic = state.get("topic", "")
    article_id = state.get("article_id")
    user_context = state.get("user_context", {})
    conversation_history = state.get("conversation_history", [])

    try:
        from agents.shared.analyst_agent import AnalystAgent
        from database import SessionLocal

        db = SessionLocal()
        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0.7,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            agent = AnalystAgent(topic=topic, llm=llm, db=db)
            result = agent.research_and_write(
                query=query,
                user_context=user_context,
                article_id=article_id,
                conversation_history=conversation_history
            )

            if not result.get("success", True):
                return {"error": result.get("error", "Research failed"), "success": False}

            return {
                "headline": result.get("headline", ""),
                "content": result.get("content", ""),
                "keywords": result.get("keywords", topic),
                "article_id": result.get("article_id"),
                "linked_resources": result.get("resources_attached", []),
                "success": True
            }

        finally:
            db.close()

    except ImportError as e:
        logger.warning(f"AnalystAgent not available, using fallback: {e}")
        return _create_content_fallback(query, topic, user_context)

    except Exception as e:
        logger.exception(f"Content creation failed: {e}")
        return {"error": str(e), "success": False}


def regenerate_headline_node(state: ArticleContentState) -> Dict[str, Any]:
    """Regenerate article headline."""
    topic = state.get("topic", "")
    existing_headline = state.get("existing_headline", "")
    existing_keywords = state.get("existing_keywords", "")
    existing_content = state.get("existing_content", "")

    if not existing_content and not existing_keywords and not existing_headline:
        return {
            "error": "Need existing content, keywords, or headline to generate a new headline.",
            "success": False
        }

    try:
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        prompt_parts = [f"Generate a compelling, professional headline for a {topic} research article."]
        if existing_keywords:
            prompt_parts.append(f"Keywords: {existing_keywords}")
        if existing_content:
            prompt_parts.append(f"Content excerpt: {existing_content[:1000]}")
        if existing_headline:
            prompt_parts.append(f"Current headline (rephrase differently): {existing_headline}")
        prompt_parts.append("\nGenerate a new headline (max 100 characters):")

        response = llm.invoke([
            {"role": "system", "content": "You are a professional financial editor. Generate concise, engaging headlines."},
            {"role": "user", "content": "\n".join(prompt_parts)}
        ])

        new_headline = response.content.strip().strip('"\'')[:100]
        return {"headline": new_headline, "success": True}

    except Exception as e:
        logger.exception(f"Headline regeneration failed: {e}")
        return {"error": str(e), "success": False}


def regenerate_keywords_node(state: ArticleContentState) -> Dict[str, Any]:
    """Regenerate article keywords."""
    topic = state.get("topic", "")
    existing_headline = state.get("existing_headline", "")
    existing_keywords = state.get("existing_keywords", "")
    existing_content = state.get("existing_content", "")

    if not existing_headline and not existing_content and not existing_keywords:
        return {
            "error": "Need a headline, content, or existing keywords to generate new keywords.",
            "success": False
        }

    try:
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.3,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        prompt_parts = [f"Generate 5-8 relevant keywords for a {topic} article."]
        if existing_headline:
            prompt_parts.append(f"Headline: {existing_headline}")
        if existing_content:
            prompt_parts.append(f"Content excerpt: {existing_content[:1500]}")
        if existing_keywords:
            prompt_parts.append(f"Current keywords (generate different alternatives): {existing_keywords}")
        prompt_parts.append("\nReturn only comma-separated keywords, no explanation:")

        response = llm.invoke([
            {"role": "system", "content": "You are a professional financial editor. Generate relevant, SEO-friendly keywords."},
            {"role": "user", "content": "\n".join(prompt_parts)}
        ])

        new_keywords = response.content.strip()
        return {"keywords": new_keywords, "success": True}

    except Exception as e:
        logger.exception(f"Keyword regeneration failed: {e}")
        return {"error": str(e), "success": False}


def regenerate_content_node(state: ArticleContentState) -> Dict[str, Any]:
    """Rewrite article content."""
    topic = state.get("topic", "")
    query = state.get("query", "")
    existing_headline = state.get("existing_headline", "")
    existing_keywords = state.get("existing_keywords", "")
    existing_content = state.get("existing_content", "")
    user_context = state.get("user_context", {})

    if not existing_headline:
        return {
            "error": "Need at least a headline to rewrite the content.",
            "success": False
        }

    try:
        tonality = user_context.get("content_tonality_text", "")

        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        system_prompt = f"""You are a professional financial analyst and writer specializing in {topic}.
Your task is to rewrite/regenerate article content. The content should be:
- Well-researched and accurate
- Professionally written
- Structured with clear sections
- Suitable for a professional finance audience
{f'Writing style preference: {tonality}' if tonality else ''}"""

        user_prompt = f"""Please rewrite the content for this article:

Headline: {existing_headline}
Keywords: {existing_keywords}
Topic: {topic}

{f'Previous content to improve upon: {existing_content[:2000]}...' if existing_content else ''}
{f'Additional instructions: {query}' if query and 'rewrite' not in query.lower()[:20] else ''}

Write a comprehensive, well-structured article in markdown format.
Include sections like Executive Summary, Key Findings, Analysis, and Conclusion."""

        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        return {"content": response.content, "success": True}

    except Exception as e:
        logger.exception(f"Content regeneration failed: {e}")
        return {"error": str(e), "success": False}


def edit_section_node(state: ArticleContentState) -> Dict[str, Any]:
    """
    Edit a specific section of the article.

    Used for requests like:
    - "Rewrite the introduction"
    - "Expand the market analysis section"
    - "Make the conclusion stronger"
    - "Fix the executive summary"

    The query should contain the section name and instruction.
    Only the specified section is modified; other content remains unchanged.
    """
    query = state.get("query", "")
    topic = state.get("topic", "")
    existing_headline = state.get("existing_headline", "")
    existing_content = state.get("existing_content", "")
    user_context = state.get("user_context", {})

    if not existing_content:
        return {
            "error": "No existing content to edit. Please create content first.",
            "success": False
        }

    try:
        tonality = user_context.get("content_tonality_text", "")

        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        system_prompt = f"""You are a professional financial editor specializing in {topic}.
Your task is to edit a SPECIFIC SECTION of an article based on the user's instruction.

CRITICAL RULES:
1. Only modify the section the user mentions (introduction, conclusion, analysis, etc.)
2. Keep ALL OTHER SECTIONS exactly as they are - do not rewrite them
3. Maintain the article's overall structure and markdown formatting
4. Preserve any existing data points, citations, or references in unchanged sections
{f'Writing style: {tonality}' if tonality else ''}

Return the COMPLETE article with only the requested section edited."""

        user_prompt = f"""Article headline: {existing_headline}

Current article content:
{existing_content}

User's editing instruction: {query}

Please edit ONLY the specified section and return the complete article with all other sections unchanged."""

        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        return {"content": response.content, "success": True}

    except Exception as e:
        logger.exception(f"Section edit failed: {e}")
        return {"error": str(e), "success": False}


def refine_content_node(state: ArticleContentState) -> Dict[str, Any]:
    """
    Refine article content based on style/tone instruction.

    Used for requests like:
    - "Make it more concise"
    - "Add more data points"
    - "Make it more professional"
    - "Simplify the language"
    - "Add more technical details"

    Applies changes to the entire content while maintaining structure.
    """
    query = state.get("query", "")
    topic = state.get("topic", "")
    existing_headline = state.get("existing_headline", "")
    existing_content = state.get("existing_content", "")
    user_context = state.get("user_context", {})

    if not existing_content:
        return {
            "error": "No existing content to refine. Please create content first.",
            "success": False
        }

    try:
        tonality = user_context.get("content_tonality_text", "")

        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.5,  # Lower temperature for more consistent refinement
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        system_prompt = f"""You are a professional financial editor specializing in {topic}.
Your task is to refine and improve an article based on the user's instruction.

RULES:
1. Apply the requested changes throughout the article
2. Maintain the article's overall structure and section organization
3. Preserve key points, data, and conclusions while adjusting presentation
4. Keep any resource references, citations, or links intact
5. Ensure the refined content remains accurate and professional
{f'Base writing style: {tonality}' if tonality else ''}

Return the complete refined article in markdown format."""

        user_prompt = f"""Article headline: {existing_headline}

Current article content:
{existing_content}

Refinement instruction: {query}

Please refine the entire article according to this instruction and return the complete updated content."""

        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])

        return {"content": response.content, "success": True}

    except Exception as e:
        logger.exception(f"Content refinement failed: {e}")
        return {"error": str(e), "success": False}


def _create_content_fallback(
    query: str,
    topic: str,
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Fallback content generation using direct LLM call."""
    tonality = user_context.get("content_tonality_text", "")

    try:
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        system_prompt = f"""You are a professional financial analyst and writer specializing in {topic}.
Generate high-quality article content for publication.
{f'Writing style preference: {tonality}' if tonality else ''}

Format your response exactly as:
HEADLINE: Your headline here
KEYWORDS: keyword1, keyword2, keyword3
CONTENT:
Your article content in markdown format here..."""

        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Please write an article about: {query}"}
        ])

        # Parse response
        result = _parse_generated_content(response.content, query)
        result["success"] = True
        return result

    except Exception as e:
        logger.exception(f"Fallback content generation failed: {e}")
        return {"error": str(e), "success": False}


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

    if not result["headline"]:
        result["headline"] = original_query[:100].title()
    if not result["content"]:
        result["content"] = content

    return result


# =============================================================================
# Sub-graph Builder
# =============================================================================

def _route_by_action(state: ArticleContentState) -> str:
    """
    Route to appropriate action node.

    Actions:
    - create: Generate new article content
    - regenerate_headline: New headline, keep content
    - regenerate_keywords: New keywords, keep content
    - regenerate_content: Full content rewrite
    - edit_section: Edit specific section (intro, conclusion, etc.)
    - refine_content: Apply style/tone changes throughout
    """
    action = state.get("action", "create")

    action_to_node = {
        "create": "create_content",
        "regenerate_headline": "regenerate_headline",
        "regenerate_keywords": "regenerate_keywords",
        "regenerate_content": "regenerate_content",
        "edit_section": "edit_section",
        "refine_content": "refine_content",
    }

    return action_to_node.get(action, "create_content")


def build_article_content_subgraph():
    """Build the article content sub-graph."""
    workflow = StateGraph(ArticleContentState)

    # Add nodes
    workflow.add_node("router", route_action_node)
    workflow.add_node("create_content", create_content_node)
    workflow.add_node("regenerate_headline", regenerate_headline_node)
    workflow.add_node("regenerate_keywords", regenerate_keywords_node)
    workflow.add_node("regenerate_content", regenerate_content_node)
    workflow.add_node("edit_section", edit_section_node)
    workflow.add_node("refine_content", refine_content_node)

    # Entry point
    workflow.set_entry_point("router")

    # Conditional routing
    workflow.add_conditional_edges(
        "router",
        _route_by_action,
        {
            "create_content": "create_content",
            "regenerate_headline": "regenerate_headline",
            "regenerate_keywords": "regenerate_keywords",
            "regenerate_content": "regenerate_content",
            "edit_section": "edit_section",
            "refine_content": "refine_content",
        }
    )

    # All action nodes go to END
    action_nodes = [
        "create_content", "regenerate_headline", "regenerate_keywords",
        "regenerate_content", "edit_section", "refine_content"
    ]
    for node in action_nodes:
        workflow.add_edge(node, END)

    return workflow.compile()


# Singleton sub-graph instance
_ARTICLE_CONTENT_SUBGRAPH = None


def article_content_subgraph():
    """Get the singleton article content sub-graph."""
    global _ARTICLE_CONTENT_SUBGRAPH
    if _ARTICLE_CONTENT_SUBGRAPH is None:
        _ARTICLE_CONTENT_SUBGRAPH = build_article_content_subgraph()
    return _ARTICLE_CONTENT_SUBGRAPH


def invoke_article_content(
    action: str,
    query: str,
    topic: str,
    user_context: Dict[str, Any],
    article_id: Optional[int] = None,
    existing_headline: Optional[str] = None,
    existing_keywords: Optional[str] = None,
    existing_content: Optional[str] = None,
    conversation_history: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """
    Invoke the article content sub-graph.

    Args:
        action: One of:
            - create: Generate new article content
            - regenerate_headline: Generate new headline (keeps content)
            - regenerate_keywords: Generate new keywords (keeps content)
            - regenerate_content: Full content rewrite
            - edit_section: Edit specific section (e.g., "rewrite the introduction")
            - refine_content: Apply style/tone changes (e.g., "make it more concise")
        query: User's content request or instruction
        topic: Topic slug
        user_context: User context (includes tonality preferences)
        article_id: Optional existing article ID
        existing_headline: Optional existing headline (required for most actions)
        existing_keywords: Optional existing keywords
        existing_content: Optional existing content (required for edit_section, refine_content)
        conversation_history: Optional conversation history

    Returns:
        Dict with headline, keywords, content, linked_resources, success, error
    """
    graph = article_content_subgraph()

    state = ArticleContentState(
        action=action,
        query=query,
        topic=topic,
        article_id=article_id,
        existing_headline=existing_headline,
        existing_keywords=existing_keywords,
        existing_content=existing_content,
        user_context=user_context,
        conversation_history=conversation_history or [],
    )

    result = graph.invoke(state)
    return result
