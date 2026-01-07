"""
Analyst Sub-Graph for research and article creation.

This module implements a proper LangGraph StateGraph for the analyst workflow,
showcasing LangGraph features including:
- Multi-node graph with specialized processing
- Conditional edges for dynamic routing
- State reducers for accumulating research
- Tool integration with sub-agents
- Optional Celery background execution

The graph structure:
                    START
                      │
                      ▼
               ┌─────────────┐
               │ Query Parser│
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
│Article │     │ Resource  │     │Web Search│
│ Search │     │  Query    │     │  Agent   │
└────┬───┘     └─────┬─────┘     └────┬─────┘
    │                 │                │
    └─────────────────┼────────────────┘
                      │
                      ▼
               ┌─────────────┐
               │Data Download│
               │   Agent    │
               └──────┬──────┘
                      │
                      ▼
               ┌─────────────┐
               │  Content   │
               │ Synthesize │
               └──────┬──────┘
                      │
                      ▼
               ┌─────────────┐
               │  Article   │
               │   Create   │
               └──────┬──────┘
                      │
                      ▼
                     END
"""

import os
import logging
from typing import Dict, Any, Optional, List, Literal, TypedDict, Annotated
from operator import add

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


# ============================================================================
# Analyst-specific State Schema
# ============================================================================

class ResearchState(TypedDict, total=False):
    """State schema for the analyst research workflow."""
    # Input
    query: str
    topic: str
    article_id: Optional[int]
    user_context: Dict[str, Any]

    # Permission check
    permission_granted: bool
    permission_error: Optional[str]

    # Research results (accumulated using reducer)
    existing_articles: Annotated[List[Dict], add]
    resources: Annotated[List[Dict], add]
    web_results: Annotated[List[Dict], add]
    data_results: Annotated[List[Dict], add]

    # Generated content
    headline: Optional[str]
    content: Optional[str]
    keywords: Optional[str]

    # Output
    result_article_id: Optional[int]
    linked_resources: List[Dict]
    sources_summary: Dict[str, int]

    # Control flow
    error: Optional[str]
    is_complete: bool


def create_research_state(
    query: str,
    topic: str,
    user_context: Dict[str, Any],
    article_id: Optional[int] = None
) -> ResearchState:
    """Create initial research state."""
    return ResearchState(
        query=query,
        topic=topic,
        article_id=article_id,
        user_context=user_context,
        permission_granted=False,
        permission_error=None,
        existing_articles=[],
        resources=[],
        web_results=[],
        data_results=[],
        headline=None,
        content=None,
        keywords=None,
        result_article_id=None,
        linked_resources=[],
        sources_summary={},
        error=None,
        is_complete=False
    )


# ============================================================================
# Node Functions
# ============================================================================

def query_parser_node(state: ResearchState) -> Dict[str, Any]:
    """
    Parse and enhance the research query.

    Extracts keywords, identifies data needs, and prepares query for sub-agents.
    """
    query = state.get("query", "")
    topic = state.get("topic", "")

    # Extract keywords (simple implementation)
    import re
    symbols = re.findall(r'\b[A-Z]{1,5}\b', query)

    # Identify query type
    query_lower = query.lower()
    needs_web_search = any(w in query_lower for w in [
        "latest", "recent", "news", "today", "current", "update"
    ])
    needs_data = any(w in query_lower for w in [
        "stock", "price", "yield", "rate", "chart", "data", "treasury"
    ]) or bool(symbols)

    keywords = ", ".join(symbols) if symbols else topic

    logger.info(f"📋 Query parsed: symbols={symbols}, needs_web={needs_web_search}, needs_data={needs_data}")

    return {
        "keywords": keywords,
        "_query_meta": {
            "symbols": symbols,
            "needs_web_search": needs_web_search,
            "needs_data": needs_data
        }
    }


def permission_check_node(state: ResearchState) -> Dict[str, Any]:
    """
    Check if user has analyst permission for the topic.
    """
    user_context = state.get("user_context", {})
    topic = state.get("topic", "")

    from agents.permission_utils import check_topic_permission

    allowed, error_msg = check_topic_permission(topic, "analyst", user_context)

    if not allowed:
        logger.warning(f"🚫 Permission denied for topic {topic}: {error_msg}")
        return {
            "permission_granted": False,
            "permission_error": error_msg,
            "is_complete": True
        }

    logger.info(f"✅ Permission granted for topic {topic}")
    return {
        "permission_granted": True
    }


def article_search_node(state: ResearchState) -> Dict[str, Any]:
    """
    Search existing articles for relevant content.
    """
    query = state.get("query", "")
    topic = state.get("topic", "")
    user_context = state.get("user_context", {})

    try:
        from agents.article_query_agent import ArticleQueryAgent
        from database import SessionLocal

        db = SessionLocal()
        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            agent = ArticleQueryAgent(llm=llm, db=db, topic=topic)
            results = agent.search_articles(
                query=query,
                user_context=user_context,
                topic=topic,
                limit=5,
                include_drafts=True
            )

            articles = results.get("articles", [])
            logger.info(f"📰 Found {len(articles)} existing articles")

            return {"existing_articles": articles}

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Article search failed: {e}")
        return {"existing_articles": []}


def resource_query_node(state: ResearchState) -> Dict[str, Any]:
    """
    Query existing resources for supporting data.
    """
    query = state.get("query", "")
    topic = state.get("topic", "")

    try:
        from agents.resource_query_agent import ResourceQueryAgent
        from database import SessionLocal

        db = SessionLocal()
        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            agent = ResourceQueryAgent(llm=llm, db=db, topic=topic)
            results = agent.query(
                search_query=query,
                topic=topic,
                limit=10
            )

            resources = results.get("resources", [])
            logger.info(f"📦 Found {len(resources)} resources")

            return {"resources": resources}

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Resource query failed: {e}")
        return {"resources": []}


def web_search_node(state: ResearchState) -> Dict[str, Any]:
    """
    Perform web search for current information.
    """
    query = state.get("query", "")
    topic = state.get("topic", "")

    try:
        from agents.web_search_agent import WebSearchAgent

        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        agent = WebSearchAgent(llm=llm, topic=topic)
        results = agent.search_news(
            query=f"{topic} {query}",
            max_results=10
        )

        web_results = results.get("results", [])
        logger.info(f"🌐 Found {len(web_results)} web results")

        return {"web_results": web_results}

    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return {"web_results": []}


def data_download_node(state: ResearchState) -> Dict[str, Any]:
    """
    Download relevant financial data.
    """
    query = state.get("query", "")
    topic = state.get("topic", "")

    try:
        from agents.data_download_agent import DataDownloadAgent
        from database import SessionLocal
        import re

        db = SessionLocal()
        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            agent = DataDownloadAgent(llm=llm, db=db, topic=topic)
            results = []
            query_lower = query.lower()

            # Look for stock symbols
            symbols = re.findall(r'\b[A-Z]{1,5}\b', query)
            for symbol in symbols[:3]:
                data = agent.fetch_stock_data(symbol, period="3mo")
                if data.get("success"):
                    results.append(data)

            # Fetch treasury data if relevant
            if any(word in query_lower for word in ["yield", "treasury", "bond", "rate", "interest"]):
                treasury = agent.fetch_treasury_yields("10Y", period="3mo")
                if treasury.get("success"):
                    results.append(treasury)

            # Fetch FX data if relevant
            if any(word in query_lower for word in ["currency", "dollar", "euro", "forex", "fx"]):
                fx = agent.fetch_fx_rate("USD", "EUR", period="3mo")
                if fx.get("success"):
                    results.append(fx)

            logger.info(f"📊 Downloaded {len(results)} data sources")

            return {"data_results": results}

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Data download failed: {e}")
        return {"data_results": []}


def content_synthesize_node(state: ResearchState) -> Dict[str, Any]:
    """
    Synthesize research findings into article content.
    """
    query = state.get("query", "")
    topic = state.get("topic", "")
    user_context = state.get("user_context", {})
    existing_articles = state.get("existing_articles", [])
    resources = state.get("resources", [])
    web_results = state.get("web_results", [])
    data_results = state.get("data_results", [])

    try:
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        # Build context
        context_parts = []

        if existing_articles:
            context_parts.append("## Existing Research\n")
            for a in existing_articles[:3]:
                context_parts.append(f"- {a.get('headline')} (ID: {a.get('id')})")

        if resources:
            context_parts.append("\n## Available Resources\n")
            for r in resources[:5]:
                context_parts.append(f"- {r.get('name')}: {r.get('description', '')[:100]}")

        if web_results:
            context_parts.append("\n## Recent News\n")
            for w in web_results[:5]:
                context_parts.append(f"- {w.get('title')}: {w.get('snippet', '')[:150]}")

        if data_results:
            context_parts.append("\n## Financial Data\n")
            for d in data_results:
                if d.get("symbol"):
                    context_parts.append(
                        f"- {d.get('symbol')}: Latest {d.get('latest_price', 'N/A')} "
                        f"({d.get('data_points', 0)} data points)"
                    )
                elif d.get("maturity"):
                    context_parts.append(
                        f"- Treasury {d.get('maturity')}: {d.get('latest_yield', 'N/A')}%"
                    )

        context = "\n".join(context_parts)

        # Build system prompt with user tonality
        system_prompt = "You are a senior financial analyst writing research articles."
        content_tonality = user_context.get("content_tonality_text")
        if content_tonality:
            system_prompt += f"\n\n## Writing Style\n{content_tonality}"

        # Generate headline
        headline_response = llm.invoke([
            SystemMessage(content="Generate a concise, professional headline for a financial research article."),
            HumanMessage(content=f"Query: {query}\nTopic: {topic}\n\nGenerate a headline (max 100 chars):"),
        ])
        headline = headline_response.content.strip().strip('"\'')[:100]

        # Generate content
        content_prompt = f"""Based on the following research context, write a comprehensive analysis article about: {query}

Topic: {topic}

{context}

Write a well-structured article with:
1. An executive summary
2. Key findings and analysis
3. Data-driven insights
4. Market implications
5. Conclusion

Use markdown formatting. Include relevant data points from the research.
Keep the article professional and suitable for financial analysts."""

        content_response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=content_prompt),
        ])

        logger.info(f"✍️ Generated content: headline='{headline}', ~{len(content_response.content)} chars")

        return {
            "headline": headline,
            "content": content_response.content
        }

    except Exception as e:
        logger.exception(f"Content synthesis failed: {e}")
        # Fallback content
        return {
            "headline": f"Analysis: {query[:80]}",
            "content": f"""# Research: {query}

## Executive Summary

This article analyzes {query} in the context of {topic}.

## Key Findings

Research sources: {len(existing_articles)} articles, {len(resources)} resources, {len(web_results)} web results.

## Conclusion

Further analysis is recommended based on the available data.

---
*Generated by AnalystSubGraph*
"""
        }


def article_create_node(state: ResearchState) -> Dict[str, Any]:
    """
    Create or update article with synthesized content.
    """
    topic = state.get("topic", "")
    article_id = state.get("article_id")
    user_context = state.get("user_context", {})
    headline = state.get("headline", "")
    content = state.get("content", "")
    keywords = state.get("keywords", "")
    resources = state.get("resources", [])
    existing_articles = state.get("existing_articles", [])
    web_results = state.get("web_results", [])
    data_results = state.get("data_results", [])

    try:
        from agents.article_query_agent import ArticleQueryAgent
        from database import SessionLocal

        db = SessionLocal()
        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            agent = ArticleQueryAgent(llm=llm, db=db, topic=topic)

            if article_id:
                # Update existing article
                result = agent.write_article_content(
                    article_id=article_id,
                    content=content,
                    user_context=user_context
                )
                result_article_id = article_id
            else:
                # Create new article
                create_result = agent.create_draft_article(
                    headline=headline,
                    user_context=user_context,
                    topic=topic,
                    keywords=keywords
                )

                if not create_result.get("success"):
                    return {
                        "error": create_result.get("error", "Failed to create article"),
                        "is_complete": True
                    }

                result_article_id = create_result.get("article_id")

                # Write content
                result = agent.write_article_content(
                    article_id=result_article_id,
                    content=content,
                    user_context=user_context
                )

            if not result.get("success"):
                return {
                    "error": result.get("error", "Failed to write content"),
                    "is_complete": True
                }

            # Link resources to article
            linked_resources = _link_resources(db, result_article_id, resources)

            logger.info(f"📝 Article saved: id={result_article_id}, linked={len(linked_resources)} resources")

            return {
                "result_article_id": result_article_id,
                "linked_resources": linked_resources,
                "sources_summary": {
                    "existing_articles": len(existing_articles),
                    "resources": len(resources),
                    "web_results": len(web_results),
                    "data_sources": len(data_results)
                },
                "is_complete": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Article creation failed: {e}")
        return {
            "error": str(e),
            "is_complete": True
        }


def _link_resources(db, article_id: int, resources: List[Dict]) -> List[Dict]:
    """Link resources to an article."""
    from models import article_resources, Resource
    from sqlalchemy import select

    linked = []
    for resource in resources:
        resource_id = resource.get("resource_id")
        if not resource_id:
            continue

        try:
            # Check if already linked
            existing = db.execute(
                select(article_resources).where(
                    article_resources.c.article_id == article_id,
                    article_resources.c.resource_id == resource_id
                )
            ).first()

            if existing:
                continue

            # Verify resource exists
            db_resource = db.query(Resource).filter(
                Resource.id == resource_id,
                Resource.is_active == True
            ).first()

            if not db_resource:
                continue

            # Create link
            db.execute(
                article_resources.insert().values(
                    article_id=article_id,
                    resource_id=resource_id
                )
            )

            linked.append({
                "resource_id": resource_id,
                "name": resource.get("name") or db_resource.name,
                "type": resource.get("type")
            })

        except Exception as e:
            logger.warning(f"Failed to link resource {resource_id}: {e}")

    if linked:
        try:
            db.commit()
        except Exception:
            db.rollback()
            return []

    return linked


# ============================================================================
# Conditional Edge Functions
# ============================================================================

def check_permission_route(state: ResearchState) -> Literal["continue", "end"]:
    """Route based on permission check result."""
    if state.get("permission_granted"):
        return "continue"
    return "end"


def should_continue(state: ResearchState) -> Literal["continue", "end"]:
    """Check if workflow should continue or has completed."""
    if state.get("is_complete") or state.get("error"):
        return "end"
    return "continue"


# ============================================================================
# Graph Builder
# ============================================================================

def build_analyst_subgraph() -> StateGraph:
    """
    Build the analyst research sub-graph.

    Returns:
        Compiled LangGraph StateGraph for analyst workflows
    """
    workflow = StateGraph(ResearchState)

    # Add nodes
    workflow.add_node("query_parser", query_parser_node)
    workflow.add_node("permission_check", permission_check_node)
    workflow.add_node("article_search", article_search_node)
    workflow.add_node("resource_query", resource_query_node)
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("data_download", data_download_node)
    workflow.add_node("content_synthesize", content_synthesize_node)
    workflow.add_node("article_create", article_create_node)

    # Set entry point
    workflow.set_entry_point("query_parser")

    # Add edges
    workflow.add_edge("query_parser", "permission_check")

    # Conditional edge after permission check
    workflow.add_conditional_edges(
        "permission_check",
        check_permission_route,
        {
            "continue": "article_search",
            "end": END
        }
    )

    # Parallel research branches converge at data_download
    # Note: LangGraph doesn't have true parallelism in basic StateGraph,
    # but we structure it to show the conceptual flow
    workflow.add_edge("article_search", "resource_query")
    workflow.add_edge("resource_query", "web_search")
    workflow.add_edge("web_search", "data_download")

    workflow.add_edge("data_download", "content_synthesize")
    workflow.add_edge("content_synthesize", "article_create")
    workflow.add_edge("article_create", END)

    return workflow.compile()


# ============================================================================
# Public Interface
# ============================================================================

def run_analyst_workflow(
    query: str,
    topic: str,
    user_context: Dict[str, Any],
    article_id: Optional[int] = None,
    use_celery: bool = False
) -> Dict[str, Any]:
    """
    Run the analyst research workflow.

    This is the main entry point for analyst workflows from the main graph.

    Args:
        query: Research query
        topic: Topic slug
        user_context: User context with permissions
        article_id: Optional existing article to update
        use_celery: If True, queue on Celery worker

    Returns:
        Dict with article_id, content, and sources used
    """
    if use_celery:
        # Queue on Celery worker
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
            "message": "Research task queued. You'll be notified when complete."
        }

    # Run synchronously using the sub-graph
    graph = build_analyst_subgraph()

    initial_state = create_research_state(
        query=query,
        topic=topic,
        user_context=user_context,
        article_id=article_id
    )

    logger.info(f"🔬 Starting analyst workflow: topic={topic}, query='{query[:50]}...'")

    try:
        final_state = graph.invoke(initial_state)

        if final_state.get("error"):
            return {
                "success": False,
                "error": final_state["error"]
            }

        if final_state.get("permission_error"):
            return {
                "success": False,
                "error": final_state["permission_error"]
            }

        return {
            "success": True,
            "article_id": final_state.get("result_article_id"),
            "headline": final_state.get("headline"),
            "content": final_state.get("content"),
            "keywords": final_state.get("keywords"),
            "linked_resources": final_state.get("linked_resources", []),
            "sources": final_state.get("sources_summary", {})
        }

    except Exception as e:
        logger.exception(f"Analyst workflow failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
