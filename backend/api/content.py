"""API endpoints for content article management."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from database import get_db
from services.content_service import ContentService
from services.pdf_service import PDFService
from dependencies import get_current_user, require_admin, require_analyst


router = APIRouter(prefix="/api/content", tags=["content"])


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
    created_at: str
    updated_at: str
    created_by_agent: str
    is_active: bool


class RateArticleRequest(BaseModel):
    rating: int  # 1-5


class EditArticleRequest(BaseModel):
    headline: Optional[str] = None
    content: Optional[str] = None
    keywords: Optional[str] = None
    author: Optional[str] = None
    editor: Optional[str] = None
    status: Optional[str] = None  # draft, editor, or published


class CreateContentRequest(BaseModel):
    query: str  # The query to send to the content agent


class ContentAgentChatRequest(BaseModel):
    message: str  # The instruction/message to the content agent
    current_headline: str
    current_content: str
    current_keywords: Optional[str] = None


# Dependencies are now imported from dependencies.py - no more monkey-patching!


@router.get("/articles/{topic}", response_model=List[ArticleResponse])
async def get_topic_articles(
    topic: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Get recent articles for a specific topic.

    Args:
        topic: Topic name (macro, equity, fixed_income, esg)
        limit: Maximum number of articles to return (default: 10, max: 50)
        db: Database session
        user: Current authenticated user

    Returns:
        List of articles
    """
    # Validate topic
    valid_topics = ["macro", "equity", "fixed_income", "esg"]
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic. Must be one of: {valid_topics}"
        )

    # Limit max results
    limit = min(limit, 50)

    # Get articles
    articles = ContentService.get_recent_articles(db, topic, limit)

    return articles


@router.get("/articles/{topic}/top-rated", response_model=List[ArticleResponse])
async def get_top_rated_articles(
    topic: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Get top-rated articles for a specific topic.

    Args:
        topic: Topic name (macro, equity, fixed_income, esg)
        limit: Maximum number of articles to return (default: 10, max: 50)
        db: Database session
        user: Current authenticated user

    Returns:
        List of top-rated articles
    """
    # Validate topic
    valid_topics = ["macro", "equity", "fixed_income", "esg"]
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic. Must be one of: {valid_topics}"
        )

    # Limit max results
    limit = min(limit, 50)

    # Get articles
    articles = ContentService.get_top_rated_articles(db, topic, limit)

    return articles


@router.get("/articles/{topic}/most-read", response_model=List[ArticleResponse])
async def get_most_read_articles(
    topic: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Get most-read articles for a specific topic.

    Args:
        topic: Topic name (macro, equity, fixed_income, esg)
        limit: Maximum number of articles to return (default: 10, max: 50)
        db: Database session
        user: Current authenticated user

    Returns:
        List of most-read articles
    """
    # Validate topic
    valid_topics = ["macro", "equity", "fixed_income", "esg"]
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic. Must be one of: {valid_topics}"
        )

    # Limit max results
    limit = min(limit, 50)

    # Get articles
    articles = ContentService.get_most_read_articles(db, topic, limit)

    return articles


@router.get("/article/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Get a specific article by ID.
    Increments readership counter.

    Args:
        article_id: Article ID
        db: Database session
        user: Current authenticated user

    Returns:
        Article details
    """
    article = ContentService.get_article(db, article_id, increment_readership=True)

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

    return article


@router.post("/article/{article_id}/rate", response_model=ArticleResponse)
async def rate_article(
    article_id: int,
    request: RateArticleRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Rate an article (1-5 stars).

    Args:
        article_id: Article ID
        request: Rating request with rating value
        db: Database session
        user: Current authenticated user

    Returns:
        Updated article with new rating
    """
    user_id = int(user.get("sub"))

    try:
        updated_article = ContentService.rate_article(
            db,
            article_id=article_id,
            user_id=user_id,
            rating=request.rating
        )

        return updated_article

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/search/{topic}")
async def search_articles(
    topic: str,
    q: Optional[str] = None,
    headline: Optional[str] = None,
    keywords: Optional[str] = None,
    author: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Advanced search for articles with multiple criteria.

    Args:
        topic: Topic name (macro, equity, fixed_income, esg, all) - use 'all' to search across all topics
        q: General search query (searches headline, keywords, and content via vector search)
        headline: Filter by headline (partial match)
        keywords: Filter by keywords (partial match)
        author: Filter by author name (partial match)
        created_after: Filter articles created after this date (ISO format, e.g., 2024-01-01)
        created_before: Filter articles created before this date (ISO format)
        limit: Maximum number of results (default: 10, max: 50)
        db: Database session
        user: Current authenticated user

    Returns:
        List of matching articles (default: 10 most relevant)
    """
    # Validate topic
    valid_topics = ["macro", "equity", "fixed_income", "esg", "all"]
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic. Must be one of: {valid_topics}"
        )

    # Limit max results
    limit = min(limit, 50)

    # Convert 'all' to None for the service layer
    search_topic = None if topic == "all" else topic

    # Search articles with all criteria
    articles = ContentService.search_articles(
        db=db,
        topic=search_topic,
        query=q,
        headline=headline,
        keywords=keywords,
        author=author,
        created_after=created_after,
        created_before=created_before,
        limit=limit
    )

    return articles


# Admin endpoints use require_admin dependency from dependencies.py


@router.get("/admin/articles/{topic}", response_model=List[ArticleResponse])
async def admin_get_all_articles(
    topic: str,
    offset: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Admin endpoint: Get all articles for a topic with pagination.

    Args:
        topic: Topic name (macro, equity, fixed_income, esg)
        offset: Number of articles to skip (default: 0)
        limit: Maximum number of articles to return (default: 20, max: 100)
        db: Database session
        admin: Current admin user

    Returns:
        List of articles
    """
    # Validate topic
    valid_topics = ["macro", "equity", "fixed_income", "esg"]
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic. Must be one of: {valid_topics}"
        )

    # Limit max results
    limit = min(limit, 100)

    # Get all articles (including inactive ones for admin)
    articles = ContentService.get_all_articles_admin(db, topic, offset, limit)

    return articles


@router.delete("/admin/article/{article_id}")
async def admin_delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Admin endpoint: Soft delete an article.

    Args:
        article_id: Article ID to delete
        db: Database session
        admin: Current admin user

    Returns:
        Success message
    """
    try:
        ContentService.delete_article(db, article_id)
        return {"message": f"Article {article_id} deleted successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/admin/article/{article_id}/reactivate")
async def admin_reactivate_article(
    article_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Admin endpoint: Reactivate a soft-deleted article.

    Args:
        article_id: Article ID to reactivate
        db: Database session
        admin: Current admin user

    Returns:
        Success message
    """
    try:
        ContentService.reactivate_article(db, article_id)
        return {"message": f"Article {article_id} reactivated successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/article/{article_id}/edit", response_model=ArticleResponse)
async def edit_article(
    article_id: int,
    request: EditArticleRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Edit an article. Requires analyst permission for the article's topic.

    Args:
        article_id: Article ID to edit
        request: Edit request with updated fields
        db: Database session
        user: Current authenticated user (must be analyst for this topic)

    Returns:
        Updated article
    """
    # Get the article first to check its topic
    article = ContentService.get_article(db, article_id, increment_readership=False)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

    # Check if user has analyst permission for this topic
    topic = article["topic"]
    analyst_check = require_analyst(topic)
    analyst_check(user)  # This will raise HTTPException if user doesn't have permission

    # Update the article
    try:
        updated_article = ContentService.update_article(
            db,
            article_id=article_id,
            headline=request.headline,
            content=request.content,
            keywords=request.keywords,
            author=request.author,
            editor=request.editor,
            status=request.status
        )
        return updated_article
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/generate/{topic}", response_model=ArticleResponse)
async def generate_content(
    topic: str,
    request: CreateContentRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Generate new content using a content agent. Requires analyst permission for the topic.

    Args:
        topic: Topic name (macro, equity, fixed_income, esg)
        request: Content generation request with query
        db: Database session
        user: Current authenticated user (must be analyst for this topic)

    Returns:
        Newly created article
    """
    # Validate topic
    valid_topics = ["macro", "equity", "fixed_income", "esg"]
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic. Must be one of: {valid_topics}"
        )

    # Check if user has analyst permission for this topic
    analyst_check = require_analyst(topic)
    analyst_check(user)  # This will raise HTTPException if user doesn't have permission

    # Generate content using the content agent
    try:
        from services.agent_service import AgentService

        user_id = int(user.get("sub"))
        agent_service = AgentService(user_id, db)

        # Use the content agent to generate an article
        article = agent_service.generate_content_article(topic, request.query)

        return article
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating content: {str(e)}"
        )


@router.post("/article/{article_id}/chat")
async def chat_with_content_agent(
    article_id: int,
    request: ContentAgentChatRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Chat with content agent to modify an article. Requires analyst permission for the article's topic.

    Args:
        article_id: Article ID being edited
        request: Chat request with message and current article state
        db: Database session
        user: Current authenticated user (must be analyst for this topic)

    Returns:
        Agent's response with suggested modifications
    """
    # Get the article to check topic and permissions
    article = ContentService.get_article(db, article_id, increment_readership=False)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

    # Check if user has analyst permission for this topic
    topic = article["topic"]
    analyst_check = require_analyst(topic)
    analyst_check(user)  # This will raise HTTPException if user doesn't have permission

    # Chat with content agent
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
        from services.prompt_service import PromptService
        import os

        # Initialize LLM
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        llm = ChatOpenAI(
            api_key=openai_api_key,
            model=openai_model,
            temperature=0.7
        )

        # Get system prompt for content agent
        system_prompt = PromptService.get_content_agent_template(topic)

        # Create context-aware prompt
        messages = [
            SystemMessage(content=f"""{system_prompt}

You are helping an analyst edit an article. The analyst will give you instructions on how to modify the article.

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

        # Get agent response
        response = llm.invoke(messages)
        agent_response = response.content

        return {
            "response": agent_response,
            "article_id": article_id
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error communicating with content agent: {str(e)}"
        )


@router.get("/article/{article_id}/pdf")
async def download_article_pdf(
    article_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Download article as PDF.

    Args:
        article_id: Article ID
        db: Database session
        user: Current authenticated user

    Returns:
        PDF file as streaming response
    """
    # Get the article
    article = ContentService.get_article(db, article_id, increment_readership=False)

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

    try:
        # Generate PDF
        pdf_buffer = PDFService.generate_article_pdf(
            headline=article["headline"],
            content=article["content"],
            topic=article["topic"],
            created_at=article["created_at"],
            keywords=article.get("keywords"),
            readership_count=article["readership_count"],
            rating=article.get("rating"),
            rating_count=article["rating_count"]
        )

        # Create a safe filename from the headline
        safe_headline = "".join(
            c for c in article["headline"] if c.isalnum() or c in (' ', '-', '_')
        ).rstrip()
        safe_headline = safe_headline.replace(' ', '_')[:50]  # Limit filename length
        filename = f"{safe_headline}_article_{article_id}.pdf"

        # Return PDF as streaming response
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating PDF: {str(e)}"
        )


# Editorial workflow endpoints

@router.get("/analyst/articles/{topic}", response_model=List[ArticleResponse])
async def get_analyst_draft_articles(
    topic: str,
    offset: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Get draft articles for analyst view. Requires analyst permission for the topic.
    """
    valid_topics = ["macro", "equity", "fixed_income", "esg"]
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic. Must be one of: {valid_topics}"
        )
    
    # Check analyst permission
    analyst_check = require_analyst(topic)
    analyst_check(user)
    
    limit = min(limit, 100)
    articles = ContentService.get_articles_by_status(db, topic, "draft", offset, limit)
    return articles


@router.get("/editor/articles/{topic}", response_model=List[ArticleResponse])
async def get_editor_articles(
    topic: str,
    offset: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Get articles in 'editor' status for editor review. Requires editor permission.
    """
    from dependencies import require_editor
    
    valid_topics = ["macro", "equity", "fixed_income", "esg"]
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic. Must be one of: {valid_topics}"
        )
    
    # Check editor permission
    editor_check = require_editor(topic)
    editor_check(user)
    
    limit = min(limit, 100)
    articles = ContentService.get_articles_by_status(db, topic, "editor", offset, limit)
    return articles


@router.get("/published/articles/{topic}", response_model=List[ArticleResponse])
async def get_published_articles(
    topic: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Get published articles for a topic. Available to all authenticated users.
    """
    valid_topics = ["macro", "equity", "fixed_income", "esg"]
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic. Must be one of: {valid_topics}"
        )
    
    limit = min(limit, 50)
    articles = ContentService.get_published_articles(db, topic, limit)
    return articles


@router.post("/article/{article_id}/approve")
async def approve_article(
    article_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Approve a draft article (moves to 'editor' status). Requires analyst permission.
    """
    # Get article to check topic
    article = ContentService.get_article(db, article_id, increment_readership=False)
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    
    # Check analyst permission for this topic
    analyst_check = require_analyst(article["topic"])
    analyst_check(user)
    
    # Verify article is in draft status
    if article["status"] != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only draft articles can be submitted"
        )
    
    try:
        # Use submit_article which sets author to submitter's email
        author_email = user.get("email", "")
        updated = ContentService.submit_article(db, article_id, author_email)
        return {"message": "Article submitted for review", "article": updated}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/article/{article_id}/reject")
async def reject_article(
    article_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Reject an article in editor review (moves back to 'draft' status). Requires editor permission.
    """
    from dependencies import require_editor
    
    # Get article to check topic
    article = ContentService.get_article(db, article_id, increment_readership=False)
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    
    # Check editor permission for this topic
    editor_check = require_editor(article["topic"])
    editor_check(user)
    
    # Verify article is in editor status
    if article["status"] != "editor":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only articles in editor review can be rejected"
        )
    
    try:
        updated = ContentService.update_article_status(db, article_id, "draft")
        return {"message": "Article rejected and sent back to draft", "article": updated}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/article/{article_id}/publish")
async def publish_article(
    article_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Publish an article (moves from 'editor' to 'published' status). Requires editor permission.
    """
    from dependencies import require_editor
    
    # Get article to check topic
    article = ContentService.get_article(db, article_id, increment_readership=False)
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    
    # Check editor permission for this topic
    editor_check = require_editor(article["topic"])
    editor_check(user)
    
    # Verify article is in editor status
    if article["status"] != "editor":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only articles in editor review can be published"
        )
    
    try:
        # Use publish_article_with_editor which sets editor to publisher's email
        editor_email = user.get("email", "")
        updated = ContentService.publish_article_with_editor(db, article_id, editor_email)
        return {"message": "Article published successfully", "article": updated}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/admin/article/{article_id}/recall")
async def admin_recall_article(
    article_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Admin endpoint: Recall a published article (move back to draft status).
    """
    try:
        updated = ContentService.recall_article(db, article_id)
        return {"message": f"Article {article_id} recalled to draft", "article": updated}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/admin/article/{article_id}/purge")
async def admin_purge_article(
    article_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Admin endpoint: Permanently delete an article and all related data.
    This action cannot be undone.
    """
    try:
        ContentService.purge_article(db, article_id)
        return {"message": f"Article {article_id} permanently deleted"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
