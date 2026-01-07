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

from agents.state import AgentState

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

# Topic inference keywords
TOPIC_KEYWORDS = {
    "macro": [
        "economy", "economic", "gdp", "inflation", "fed", "federal reserve",
        "interest rate", "unemployment", "jobs", "growth", "recession",
        "monetary policy", "fiscal", "treasury", "ecb", "central bank"
    ],
    "equity": [
        "stock", "equity", "shares", "company", "earnings", "revenue",
        "profit", "valuation", "p/e", "market cap", "dividend", "nasdaq",
        "s&p", "dow", "ipo", "buyback"
    ],
    "fixed_income": [
        "bond", "yield", "credit", "treasury", "debt", "coupon",
        "maturity", "duration", "spread", "default", "investment grade",
        "high yield", "fixed income", "sovereign"
    ],
    "esg": [
        "esg", "sustainability", "climate", "environmental", "social",
        "governance", "carbon", "renewable", "green", "impact",
        "responsible", "ethical"
    ]
}


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

    # Fetch web search results using WebSearchAgent
    if data_needs.get("needs_web_search"):
        context_data["web_results"] = _fetch_web_search(user_query, topic)

    # Fetch market data using DataDownloadAgent
    if data_needs.get("needs_market_data"):
        context_data["market_data"] = _fetch_market_data(user_query, topic)

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
    """Infer the topic from query and navigation context."""
    # First check navigation context
    if nav_context.get("topic"):
        return nav_context["topic"]

    # Then infer from query
    query_lower = query.lower()

    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            return topic

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
        from agents.web_search_agent import WebSearchAgent

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
        from agents.data_download_agent import DataDownloadAgent
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
    """
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

            result = agent.search_articles(
                query=query,
                user_context=user_context,
                topic=topic,
                limit=5,
                include_drafts=False  # Only published articles for general chat
            )

            articles = result.get("articles", [])
            logger.info(f"📰 Found {len(articles)} relevant articles")

            return [
                {
                    "id": a.get("id"),
                    "headline": a.get("headline"),
                    "topic": a.get("topic"),
                    "status": a.get("status"),
                    "author": a.get("author")
                }
                for a in articles
            ]

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
    topic_descriptions = {
        "macro": "macroeconomics and economic policy",
        "equity": "equity markets and stock analysis",
        "fixed_income": "fixed income and bond markets",
        "esg": "ESG investing and sustainability"
    }

    base_prompt = """You are a helpful financial assistant integrated into a content management system for financial analysis.

Your role is to:
- Answer questions about financial topics accurately and clearly
- Help users understand market concepts and trends
- Provide context from available articles and data
- Guide users to relevant content in the system

Be conversational but professional. Keep responses concise unless asked for detail."""

    if topic:
        base_prompt += f"\n\nCurrent topic focus: {topic_descriptions.get(topic, topic)}"

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
        for article in context_data["articles"][:3]:
            headline = article.get('headline', 'Article')
            topic = article.get('topic', '')
            article_id = article.get('id', '')
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
- Reference specific articles when relevant (by ID or headline)
- If you don't have specific data, say so rather than making up numbers
- For detailed analysis, suggest the user check the relevant analyst section
- Keep responses focused and actionable
- Use markdown formatting for readability"""

    return base_prompt
