"""
General Chat node for the main chat graph.

This node handles general conversation and topic-specific Q&A queries.
It integrates with:
- WebSearchAgent for live news and web data
- DataDownloadAgent for financial data
- ArticleQueryAgent for existing articles
- ResourceQueryAgent for linked resources

LangGraph Features Used:
- State-based context preservation
- Tool integration with sub-agents
- Topic routing from dynamic database
"""

from typing import Dict, Any, Optional, List
import logging
import os
import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from agents.builds.v2.state import AgentState

logger = logging.getLogger(__name__)


# Keywords that indicate need for live/real-time data
LIVE_DATA_KEYWORDS = [
    "latest", "recent", "today", "current", "now", "this week",
    "this month", "breaking", "news", "update", "just"
]

# Keywords that indicate need for market data
MARKET_DATA_KEYWORDS = [
    "price", "quote", "trading", "market", "stock price",
    "yield", "rate", "performance", "returns"
]

# Topic inference keywords - DEPRECATED: Use TopicManager.infer_topic() instead
# Kept as fallback only if TopicManager fails to infer from database
# These will be phased out once topic keywords are stored in the database
TOPIC_KEYWORDS: Dict[str, List[str]] = {}


def general_chat_node(state: AgentState) -> Dict[str, Any]:
    """
    Handle general conversation and topic-specific Q&A.

    This node:
    1. Determines the topic from message context
    2. Analyzes data needs (web search, market data)
    3. Fetches live data using WebSearchAgent
    4. Fetches market data using DataDownloadAgent
    5. Searches relevant articles and resources
    6. Synthesizes a comprehensive response

    Args:
        state: Current agent state with messages and context

    Returns:
        Updated state with response_text and relevant metadata
    """
    messages = state.get("messages", [])
    user_context = state.get("user_context", {})
    nav_context = state.get("navigation_context", {})

    if not messages:
        return {
            "response_text": "How can I help you today?",
            "selected_agent": "general",
            "is_final": True
        }

    # Get the user's query
    user_query = messages[-1].content if hasattr(messages[-1], 'content') else str(messages[-1])

    # Determine topic
    topic = _infer_topic(user_query, nav_context)

    # Analyze what data is needed
    data_needs = _analyze_data_needs(user_query)

    # Build context from various sources
    context_data = {}

    # # Fetch web search results using WebSearchAgent
    # if data_needs.get("needs_web_search"):
    #     context_data["web_results"] = _fetch_web_search(user_query, topic)

    # # Fetch market data using DataDownloadAgent
    # if data_needs.get("needs_market_data"):
    #     context_data["market_data"] = _fetch_market_data(user_query, topic)

    # Search relevant articles using ArticleQueryAgent
    context_data["articles"] = _search_articles(user_query, topic, user_context)

    # Search relevant resources using ResourceQueryAgent
    context_data["resources"] = _search_resources(user_query, topic)

    # Generate response
    try:
        response = _generate_response(
            query=user_query,
            topic=topic,
            context_data=context_data,
            user_context=user_context,
            conversation_history=messages[:-1]  # Previous messages for context
        )

        return {
            "response_text": response["text"],
            "referenced_articles": response.get("articles", []),
            "selected_agent": topic or "general",
            "routing_reason": f"General chat" + (f" ({topic})" if topic else ""),
            "is_final": True
        }

    except Exception as e:
        logger.exception(f"Response generation failed: {e}")
        return {
            "response_text": f"I apologize, but I encountered an error processing your request. "
                           f"Please try rephrasing your question.",
            "selected_agent": "general",
            "error": str(e),
            "is_final": True
        }


def _infer_topic(query: str, nav_context: Dict[str, Any]) -> Optional[str]:
    """
    Infer the topic from the query itself.

    For general article queries, we prioritize what the user explicitly mentions
    in their message. If no topic is mentioned, we search across all topics
    rather than defaulting to the navigation context topic.

    This ensures queries like "what is the latest research" search all topics,
    not just the one the user happens to be viewing.
    """
    # Use dynamic TopicManager for topic inference from database
    from agents.shared.topic_manager import infer_topic as tm_infer_topic

    # Try to infer topic from the query using TopicManager
    topic = tm_infer_topic(query)
    if topic:
        return topic

    # Fallback to hardcoded keywords if TopicManager returns nothing
    query_lower = query.lower()
    for topic_slug, keywords in TOPIC_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            return topic_slug

    # No topic mentioned in query - return None to search all topics
    # Don't fall back to nav_context topic for general queries
    return None


def _analyze_data_needs(query: str) -> Dict[str, bool]:
    """Analyze what external data the query needs."""
    query_lower = query.lower()

    return {
        "needs_web_search": any(kw in query_lower for kw in LIVE_DATA_KEYWORDS),
        "needs_market_data": any(kw in query_lower for kw in MARKET_DATA_KEYWORDS)
    }


def _fetch_web_search(query: str, topic: Optional[str]) -> List[Dict[str, str]]:
    """
    Fetch web search results using WebSearchAgent.

    Integrates with the WebSearchAgent for live news and information.
    """
    try:
        from agents.shared.web_search_agent import WebSearchAgent

        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        agent = WebSearchAgent(llm=llm, topic=topic)

        # Search for news related to the query
        search_query = f"{topic} {query}" if topic else query
        result = agent.search_news(
            query=search_query,
            max_results=5
        )

        web_results = result.get("results", [])
        logger.info(f"🌐 Web search returned {len(web_results)} results")

        return [
            {
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
                "url": r.get("url", "")
            }
            for r in web_results
        ]

    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return []


def _fetch_market_data(query: str, topic: Optional[str]) -> Dict[str, Any]:
    """
    Fetch market data using DataDownloadAgent.

    Fetches financial data relevant to the query.
    """
    try:
        from agents.shared.data_download_agent import DataDownloadAgent
        from database import SessionLocal

        db = SessionLocal()
        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            agent = DataDownloadAgent(llm=llm, db=db, topic=topic)

            # Extract stock symbols from query
            symbols = re.findall(r'\b[A-Z]{1,5}\b', query)
            data = {}

            # Fetch stock data for mentioned symbols
            for symbol in symbols[:3]:  # Limit to 3 symbols
                stock_data = agent.fetch_stock_data(symbol, period="1mo")
                if stock_data.get("success"):
                    data[symbol] = {
                        "latest_price": stock_data.get("latest_price"),
                        "change_percent": stock_data.get("change_percent"),
                        "volume": stock_data.get("volume")
                    }

            # Check for treasury/yield keywords
            query_lower = query.lower()
            if any(w in query_lower for w in ["yield", "treasury", "bond rate"]):
                treasury_data = agent.fetch_treasury_yields("10Y", period="1mo")
                if treasury_data.get("success"):
                    data["treasury_10y"] = {
                        "yield": treasury_data.get("latest_yield"),
                        "date": treasury_data.get("latest_date")
                    }

            # Check for FX keywords
            if any(w in query_lower for w in ["dollar", "euro", "currency", "fx"]):
                fx_data = agent.fetch_fx_rate("USD", "EUR", period="1mo")
                if fx_data.get("success"):
                    data["usd_eur"] = {
                        "rate": fx_data.get("latest_rate"),
                        "date": fx_data.get("latest_date")
                    }

            logger.info(f"📊 Fetched market data for {len(data)} symbols/instruments")

            return data

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Market data fetch failed: {e}")
        return {}


def _search_articles(
    query: str,
    topic: Optional[str],
    user_context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Search articles using ArticleQueryAgent.

    Finds relevant articles in the system for context.
    Includes popup URLs for published articles so chat can link to them.
    Only searches topics with access_mainchat=True (AI-accessible topics).
    """
    try:
        from agents.shared.article_query_agent import ArticleQueryAgent
        from agents.shared.topic_manager import get_ai_accessible_topic_slugs
        from services.article_resource_service import ArticleResourceService
        from database import SessionLocal

        db = SessionLocal()
        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            # If no specific topic, search across all AI-accessible topics
            search_topic = topic
            if topic:
                # Verify the topic is AI-accessible
                ai_topics = get_ai_accessible_topic_slugs()
                if topic not in ai_topics:
                    logger.debug(f"Topic '{topic}' is not AI-accessible, skipping article search")
                    return []

            agent = ArticleQueryAgent(llm=llm, db=db, topic=search_topic)

            result = agent.search_articles(
                query=query,
                user_context=user_context,
                topic=search_topic,
                limit=5,
                include_drafts=False,  # Only published articles for general chat
                ai_accessible_only=True  # Only search AI-accessible topics
            )

            articles = result.get("articles", [])
            logger.info(f"📰 Found {len(articles)} relevant articles")

            # Get popup URLs for published articles
            formatted_articles = []
            base_url = os.getenv("PUBLIC_API_URL", "http://localhost:8000")

            for a in articles:
                article_data = {
                    "id": a.get("id"),
                    "headline": a.get("headline"),
                    "topic": a.get("topic"),
                    "status": a.get("status"),
                    "author": a.get("author"),
                    "url": None  # Will be set if article has popup resource
                }

                # Get popup URL for published articles
                if a.get("id") and a.get("status") == "published":
                    try:
                        resources = ArticleResourceService.get_article_publication_resources(
                            db, a.get("id")
                        )
                        if resources.get("popup"):
                            article_data["url"] = f"{base_url}/api/r/{resources['popup']}"
                    except Exception as e:
                        logger.debug(f"Could not get popup URL for article {a.get('id')}: {e}")

                formatted_articles.append(article_data)

            return formatted_articles

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Article search failed: {e}")
        return []


def _search_resources(query: str, topic: Optional[str]) -> List[Dict[str, Any]]:
    """
    Search resources using ResourceQueryAgent.

    Finds relevant data resources for context.
    """
    try:
        from agents.shared.resource_query_agent import ResourceQueryAgent
        from database import SessionLocal

        db = SessionLocal()
        try:
            llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0,
                api_key=os.getenv("OPENAI_API_KEY", "")
            )

            agent = ResourceQueryAgent(llm=llm, db=db, topic=topic)

            result = agent.query(
                search_query=query,
                topic=topic,
                limit=5
            )

            resources = result.get("resources", [])
            logger.info(f"📦 Found {len(resources)} relevant resources")

            return [
                {
                    "id": r.get("resource_id"),
                    "name": r.get("name"),
                    "type": r.get("type"),
                    "description": r.get("description", "")[:100]
                }
                for r in resources
            ]

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Resource search failed: {e}")
        return []


def _generate_response(
    query: str,
    topic: Optional[str],
    context_data: Dict[str, Any],
    user_context: Dict[str, Any],
    conversation_history: List
) -> Dict[str, Any]:
    """
    Generate a response using LLM with context.

    This synthesizes information from various sources into a coherent response.
    """
    # Get user's chat tonality preference
    tonality = user_context.get("chat_tonality_text", "")

    # Build system prompt
    system_prompt = _build_system_prompt(topic, tonality, context_data)

    # Build conversation for LLM
    llm_messages = [{"role": "system", "content": system_prompt}]

    # Add recent conversation history (last 5 exchanges)
    for msg in conversation_history[-10:]:
        if hasattr(msg, 'content'):
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            llm_messages.append({"role": role, "content": msg.content})

    # Add current query
    llm_messages.append({"role": "user", "content": query})

    # Generate response
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.7,
        api_key=os.getenv("OPENAI_API_KEY", "")
    )

    response = llm.invoke(llm_messages)

    return {
        "text": response.content,
        "articles": context_data.get("articles", [])
    }


def _build_system_prompt(
    topic: Optional[str],
    tonality: str,
    context_data: Dict[str, Any]
) -> str:
    """Build the system prompt for response generation."""
    base_prompt = """You are a helpful financial assistant integrated into a content management system for financial analysis.

Your role is to:
- Answer questions about financial topics accurately and clearly
- Help users understand market concepts and trends
- Provide context from available articles and data
- Guide users to relevant content in the system

Be conversational but professional. Keep responses concise unless asked for detail."""

    if topic:
        # Get topic description from database
        from agents.shared.topic_manager import get_topic_config
        topic_config = get_topic_config(topic)
        topic_desc = topic_config.description if topic_config and topic_config.description else topic_config.name if topic_config else topic
        base_prompt += f"\n\nCurrent topic focus: {topic_desc}"

    if tonality:
        base_prompt += f"\n\nUser's preferred communication style: {tonality}"

    # Add context data if available
    if context_data.get("web_results"):
        base_prompt += "\n\n## Recent News\n"
        for result in context_data["web_results"][:3]:
            title = result.get('title', 'News item')
            snippet = result.get('snippet', '')[:100]
            base_prompt += f"- **{title}**: {snippet}\n"

    if context_data.get("market_data"):
        base_prompt += "\n\n## Live Market Data\n"
        for symbol, data in context_data["market_data"].items():
            if "latest_price" in data:
                base_prompt += f"- **{symbol}**: ${data['latest_price']}"
                if data.get("change_percent"):
                    base_prompt += f" ({data['change_percent']:+.2f}%)"
                base_prompt += "\n"
            elif "yield" in data:
                base_prompt += f"- **{symbol}**: {data['yield']}%\n"
            elif "rate" in data:
                base_prompt += f"- **{symbol}**: {data['rate']}\n"

    if context_data.get("articles"):
        base_prompt += "\n\n## Relevant Articles in System\n"
        base_prompt += "When referencing articles, use the provided URL to create clickable links.\n\n"
        for article in context_data["articles"][:3]:
            headline = article.get('headline', 'Article')
            topic = article.get('topic', '')
            article_id = article.get('id', '')
            url = article.get('url')
            if url:
                # Article has a popup URL - include it for linking
                base_prompt += f"- [{headline}]({url}) ({topic}) - Article #{article_id}\n"
            else:
                # No URL available - just mention the headline
                base_prompt += f"- **{headline}** ({topic}) - Article #{article_id}\n"

    if context_data.get("resources"):
        base_prompt += "\n\n## Available Resources\n"
        for resource in context_data["resources"][:3]:
            name = resource.get('name', 'Resource')
            res_type = resource.get('type', '')
            base_prompt += f"- **{name}** ({res_type})\n"

    base_prompt += """

## Response Guidelines
- Use the provided data and context to give accurate, grounded answers
- If you cite market data, mention it came from the system
- When referencing articles, create markdown links using the URLs provided above (e.g., [Article Title](url))
- If an article has no URL, just mention it by headline and ID
- If you don't have specific data, say so rather than making up numbers
- For detailed analysis, suggest the user check the relevant analyst section
- Keep responses focused and actionable
- Use markdown formatting for readability"""

    return base_prompt
