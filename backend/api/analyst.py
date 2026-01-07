"""API endpoints for analyst access to content articles.

These endpoints require analyst, editor, or admin role for the specified topic.
URL pattern: /api/analyst/{topic}/...
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from database import get_db
from services.content_service import ContentService
from dependencies import (
    get_current_user,
    require_analyst_for_topic,
    validate_article_topic,
)
import logging

logger = logging.getLogger("uvicorn")


router = APIRouter(prefix="/api/analyst/{topic}", tags=["analyst"])


# Pydantic models for API
class ArticleResponse(BaseModel):
    id: int
    topic: str
    headline: str
    author: Optional[str]
    editor: Optional[str]
    content: str
    readership_count: int
    rating: Optional[int]
    rating_count: int
    keywords: Optional[str]
    status: str  # draft, editor, or published
    priority: int
    is_sticky: bool
    created_at: str
    updated_at: str
    created_by_agent: str
    is_active: bool


class EditArticleRequest(BaseModel):
    headline: Optional[str] = None
    content: Optional[str] = None
    keywords: Optional[str] = None
    author: Optional[str] = None
    editor: Optional[str] = None
    status: Optional[str] = None  # draft, editor, or published
    priority: Optional[int] = None
    is_sticky: Optional[bool] = None


class CreateContentRequest(BaseModel):
    query: str  # The query to send to the content agent


class CreateEmptyArticleRequest(BaseModel):
    headline: Optional[str] = "New Article"


class ContentAgentChatRequest(BaseModel):
    message: str  # The instruction/message to the content agent
    current_headline: str
    current_content: str
    current_keywords: Optional[str] = None


# =============================================================================
# Analyst Endpoints - Require {topic}:analyst+ permission
# =============================================================================


@router.get("/articles", response_model=List[ArticleResponse])
async def get_draft_articles(
    topic: str,
    offset: int = 0,
    limit: int = 20,
    user_topic: Tuple[dict, str] = Depends(require_analyst_for_topic),
    db: Session = Depends(get_db)
):
    """
    Get draft articles for analyst view.

    Args:
        topic: Topic slug from URL path
        offset: Number of articles to skip (default: 0)
        limit: Maximum number of articles to return (default: 20, max: 100)

    Returns:
        List of draft articles for the topic
    """
    user, validated_topic = user_topic
    limit = min(limit, 100)
    articles = ContentService.get_articles_by_status(db, validated_topic, "draft", offset, limit)
    return articles


@router.post("/article", response_model=ArticleResponse)
async def create_empty_article(
    topic: str,
    request: CreateEmptyArticleRequest = CreateEmptyArticleRequest(),
    user_topic: Tuple[dict, str] = Depends(require_analyst_for_topic),
    db: Session = Depends(get_db)
):
    """
    Create a new empty article.

    Args:
        topic: Topic slug from URL path
        request: Optional headline for the new article

    Returns:
        Newly created empty article
    """
    user, validated_topic = user_topic

    try:
        article = ContentService.create_article(
            db=db,
            topic=validated_topic,
            headline=request.headline or "New Article",
            content="",  # Empty content
            keywords="",
            agent_name="manual"
        )
        return article
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating article: {str(e)}"
        )


@router.post("/generate", response_model=ArticleResponse)
async def generate_content(
    topic: str,
    request: CreateContentRequest,
    user_topic: Tuple[dict, str] = Depends(require_analyst_for_topic),
    db: Session = Depends(get_db)
):
    """
    Generate new content using a content agent.

    Args:
        topic: Topic slug from URL path
        request: Content generation request with query

    Returns:
        Newly created article with AI-generated content
    """
    user, validated_topic = user_topic

    try:
        from services.agent_service import AgentService
        import traceback

        user_id = int(user.get("sub"))
        logger.info(f"[CONTENT GENERATE] Topic: {validated_topic}, User: {user_id}, Query: {request.query[:50]}...")

        agent_service = AgentService(user_id, db)

        # Use the content agent to generate an article
        article = agent_service.generate_content_article(validated_topic, request.query)
        logger.info(f"[CONTENT GENERATE] Success - Article ID: {article.get('id', 'N/A')}")

        return article
    except Exception as e:
        logger.error(f"[CONTENT GENERATE ERROR] Topic: {validated_topic}, Error: {str(e)}")
        logger.error(f"[CONTENT GENERATE ERROR] Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating content: {str(e)}"
        )


@router.put("/article/{article_id}", response_model=ArticleResponse)
async def edit_article(
    topic: str,
    article_id: int,
    request: EditArticleRequest,
    user_topic: Tuple[dict, str] = Depends(require_analyst_for_topic),
    db: Session = Depends(get_db)
):
    """
    Edit an article.

    Args:
        topic: Topic slug from URL path (validated against article's topic)
        article_id: Article ID
        request: Edit request with updated fields

    Returns:
        Updated article
    """
    user, validated_topic = user_topic

    # Validate article belongs to this topic
    article = validate_article_topic(validated_topic, article_id, db)

    try:
        updated_article = ContentService.update_article(
            db,
            article_id=article_id,
            headline=request.headline,
            content=request.content,
            keywords=request.keywords,
            author=request.author,
            editor=request.editor,
            status=request.status,
            priority=request.priority,
            is_sticky=request.is_sticky
        )

        return updated_article
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/article/{article_id}/chat")
async def chat_with_content_agent(
    topic: str,
    article_id: int,
    request: ContentAgentChatRequest,
    user_topic: Tuple[dict, str] = Depends(require_analyst_for_topic),
    db: Session = Depends(get_db)
):
    """
    Chat with content agent to modify an article.

    Args:
        topic: Topic slug from URL path
        article_id: Article ID being edited
        request: Chat request with message and current article state

    Returns:
        Agent's response with suggested modifications
    """
    user, validated_topic = user_topic

    # Validate article belongs to this topic
    article_model = validate_article_topic(validated_topic, article_id, db)

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
        from services.prompt_service import PromptService
        from agents.web_search_agent import WebSearchAgent
        from agents.data_download_agent import DataDownloadAgent
        from agents.article_query_agent import ArticleQueryAgent
        from services.user_context_service import UserContextService
        import os
        import re

        # Initialize LLM
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        llm = ChatOpenAI(
            api_key=openai_api_key,
            model=openai_model,
            temperature=0.7
        )

        # Initialize subagents for research
        web_search_agent = WebSearchAgent(llm=llm, topic=validated_topic)
        data_download_agent = DataDownloadAgent(llm=llm, db=db, topic=validated_topic)
        article_query_agent = ArticleQueryAgent(llm=llm, db=db, topic=validated_topic)

        # Build user context
        user_context = UserContextService.build(user, db)

        # Detect what kind of research is needed from the analyst's message
        message_lower = request.message.lower()
        research_context = ""

        # Check for web search needs
        news_keywords = ["latest", "recent", "news", "current", "today", "update", "search", "find", "research"]
        if any(kw in message_lower for kw in news_keywords):
            logger.info(f"[ARTICLE CHAT] Delegating to WebSearchAgent for news research...")
            search_result = web_search_agent.search_financial_news(request.message, max_results=5)
            if search_result.get("success") and search_result.get("results"):
                research_context += "\n### Latest News from Web Search:\n"
                for i, news in enumerate(search_result["results"][:5], 1):
                    research_context += f"{i}. **{news.get('title', 'N/A')}**\n"
                    research_context += f"   Source: {news.get('source', 'N/A')} | Date: {news.get('date', 'N/A')}\n"
                    research_context += f"   {news.get('snippet', '')[:200]}\n\n"
                logger.info(f"[ARTICLE CHAT] Got {len(search_result['results'])} news results")

        # Check for stock data needs
        stock_symbols = re.findall(r'\b([A-Z]{1,5})\b', request.message)
        common_words = {"I", "A", "THE", "AND", "OR", "FOR", "TO", "IN", "ON", "AT", "IS", "IT", "BE", "AS", "AN", "BY", "SO", "IF", "OF", "US", "UK", "EU", "GDP", "CPI", "FED", "ECB", "FX", "PE", "CEO", "CFO", "IPO", "JSON", "HEADLINE", "CONTENT", "KEYWORDS"}
        stock_symbols = [s for s in stock_symbols if s not in common_words][:3]

        if stock_symbols:
            logger.info(f"[ARTICLE CHAT] Delegating to DataDownloadAgent for: {stock_symbols}")
            research_context += "\n### Live Market Data:\n"
            for symbol in stock_symbols:
                stock_result = data_download_agent.fetch_stock_info(symbol)
                if stock_result.get("success"):
                    info = stock_result.get("info", {})
                    research_context += f"\n**{symbol}** - {info.get('name', 'N/A')}\n"
                    research_context += f"Sector: {info.get('sector', 'N/A')} | Industry: {info.get('industry', 'N/A')}\n"
                    if info.get('market_cap'):
                        research_context += f"Market Cap: ${info.get('market_cap', 0):,.0f}\n"
                    if info.get('pe_ratio'):
                        research_context += f"P/E Ratio: {info.get('pe_ratio'):.2f}\n"
                    if info.get('dividend_yield'):
                        research_context += f"Dividend Yield: {info.get('dividend_yield', 0)*100:.2f}%\n"
                    logger.info(f"[ARTICLE CHAT] Got data for {symbol}")

        # Check for article reference needs
        article_keywords = ["similar", "related", "other articles", "previous", "reference", "compare"]
        if any(kw in message_lower for kw in article_keywords):
            logger.info(f"[ARTICLE CHAT] Delegating to ArticleQueryAgent for related articles...")
            article_result = article_query_agent.search_articles(request.message, limit=3)
            if article_result.get("success") and article_result.get("articles"):
                research_context += "\n### Related Articles in Knowledge Base:\n"
                for art in article_result["articles"][:3]:
                    research_context += f"- **{art.get('headline', 'N/A')}** (ID: {art.get('id')})\n"
                    research_context += f"  Keywords: {art.get('keywords', 'N/A')}\n"
                logger.info(f"[ARTICLE CHAT] Got {len(article_result['articles'])} related articles")

        # Get system prompt for content agent
        system_prompt = PromptService.get_content_agent_template(validated_topic)

        # Add user context to prompt
        user_name = user_context.get("name", "Analyst")

        # Create context-aware prompt with research data
        messages = [
            SystemMessage(content=f"""{system_prompt}

You are helping {user_name} (an analyst) edit an article. The analyst will give you instructions on how to modify the article.

IMPORTANT INSTRUCTIONS:
1. When the analyst asks you to modify the article, provide the COMPLETE modified article content
2. Format your response as JSON with these fields:
   - "headline": The modified or original headline
   - "content": The complete modified article content (in Markdown format)
   - "keywords": Comma-separated keywords
   - "explanation": Brief explanation of what you changed

3. If the analyst's instruction is unclear, ask for clarification
4. Maintain the article's professional tone and format
5. Always return the FULL article content, not just the changes
6. If research data is provided below, USE IT to enhance the article with current information
{research_context}
"""),
            HumanMessage(content=f"""Current article:

HEADLINE: {request.current_headline}

KEYWORDS: {request.current_keywords or 'None'}

CONTENT:
{request.current_content}

---

ANALYST INSTRUCTION: {request.message}

Please provide your response as JSON with fields: headline, content, keywords, explanation
""")
        ]

        logger.info(f"[ARTICLE CHAT] Invoking LLM for article {article_id}...")
        # Use async invoke to not block the event loop during long LLM calls
        response = await llm.ainvoke(messages)
        agent_response = response.content
        logger.info(f"[ARTICLE CHAT] LLM response received, length: {len(agent_response)} chars")

        # Truncate response if it's too large (>50KB can cause issues)
        max_response_len = 50000
        if len(agent_response) > max_response_len:
            logger.warning(f"[ARTICLE CHAT] Response too large ({len(agent_response)} chars), truncating to {max_response_len}")
            agent_response = agent_response[:max_response_len] + "\n\n[Response truncated due to length]"

        # Ensure response is properly encoded
        if isinstance(agent_response, str):
            agent_response = agent_response.encode('utf-8', errors='replace').decode('utf-8')

        logger.info(f"[ARTICLE CHAT] Building response for article {article_id}...")
        return {
            "response": agent_response,
            "article_id": article_id
        }

    except Exception as e:
        import traceback
        logger.error(f"[ARTICLE CHAT ERROR] Article {article_id}: {str(e)}")
        logger.error(f"[ARTICLE CHAT ERROR] Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error communicating with content agent: {str(e)}"
        )


@router.post("/article/{article_id}/submit")
async def submit_article_for_review(
    topic: str,
    article_id: int,
    user_topic: Tuple[dict, str] = Depends(require_analyst_for_topic),
    db: Session = Depends(get_db)
):
    """
    Submit a draft article for editor review (moves to 'editor' status).

    Args:
        topic: Topic slug from URL path
        article_id: Article ID

    Returns:
        Success message with updated article
    """
    user, validated_topic = user_topic

    # Validate article belongs to this topic
    article_model = validate_article_topic(validated_topic, article_id, db)

    # Get article dict for status check
    article = ContentService.get_article(db, article_id, increment_readership=False)

    # Verify article is in draft status
    if article["status"] != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft articles can be submitted for review"
        )

    try:
        # Use submit_article which sets author to submitter's email
        author_email = user.get("email", "")
        updated = ContentService.submit_article(db, article_id, author_email)
        return {"message": "Article submitted for review", "article": updated}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
