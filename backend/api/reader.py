"""API endpoints for reader access to content articles.

These endpoints require reader or higher role for the specified topic.
URL pattern: /api/reader/{topic}/...

Permission: global:reader+ OR {topic}:reader+
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from database import get_db
from services.content_service import ContentService
from services.pdf_service import PDFService
from dependencies import (
    require_reader_for_topic,
    validate_article_topic,
)
import logging

logger = logging.getLogger("uvicorn")


router = APIRouter(prefix="/api/reader/{topic}", tags=["reader"])


# Pydantic models for API responses
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


class RateArticleRequest(BaseModel):
    rating: int  # 1-5


# =============================================================================
# Reader Endpoints - Require global:reader+ OR {topic}:reader+
# =============================================================================


@router.get("/articles", response_model=List[ArticleResponse])
async def get_topic_articles(
    topic: str,
    limit: int = 10,
    user_topic: Tuple[dict, str] = Depends(require_reader_for_topic),
    db: Session = Depends(get_db)
):
    """
    Get published articles for a specific topic.
    Readers can only access published articles.

    Args:
        topic: Topic slug from URL path
        limit: Maximum number of articles to return (default: 10, max: 50)

    Returns:
        List of published articles for the topic
    """
    user, validated_topic = user_topic
    limit = min(limit, 50)
    # Readers can only see published articles
    articles = ContentService.get_published_articles(db, validated_topic, limit)
    return articles


@router.get("/articles/top-rated", response_model=List[ArticleResponse])
async def get_top_rated_articles(
    topic: str,
    limit: int = 10,
    user_topic: Tuple[dict, str] = Depends(require_reader_for_topic),
    db: Session = Depends(get_db)
):
    """
    Get top-rated published articles for a specific topic.
    Readers can only access published articles.

    Args:
        topic: Topic slug from URL path
        limit: Maximum number of articles to return (default: 10, max: 50)

    Returns:
        List of top-rated published articles
    """
    user, validated_topic = user_topic
    limit = min(limit, 50)
    # Readers can only see published articles
    articles = ContentService.get_top_rated_articles(db, validated_topic, limit, status="published")
    return articles


@router.get("/articles/most-read", response_model=List[ArticleResponse])
async def get_most_read_articles(
    topic: str,
    limit: int = 10,
    user_topic: Tuple[dict, str] = Depends(require_reader_for_topic),
    db: Session = Depends(get_db)
):
    """
    Get most-read published articles for a specific topic.
    Readers can only access published articles.

    Args:
        topic: Topic slug from URL path
        limit: Maximum number of articles to return (default: 10, max: 50)

    Returns:
        List of most-read published articles
    """
    user, validated_topic = user_topic
    limit = min(limit, 50)
    # Readers can only see published articles
    articles = ContentService.get_most_read_articles(db, validated_topic, limit, status="published")
    return articles


@router.get("/article/{article_id}", response_model=ArticleResponse)
async def get_article(
    topic: str,
    article_id: int,
    user_topic: Tuple[dict, str] = Depends(require_reader_for_topic),
    db: Session = Depends(get_db)
):
    """
    Get a specific published article by ID.
    Validates article belongs to the specified topic.
    Readers can only access published articles.
    Increments readership counter.

    Args:
        topic: Topic slug from URL path
        article_id: Article ID

    Returns:
        Article details
    """
    user, validated_topic = user_topic

    # Validate article belongs to this topic
    validate_article_topic(validated_topic, article_id, db)

    article = ContentService.get_article(db, article_id, increment_readership=True)

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

    # Readers can only access published articles
    if article["status"] != "published":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Article is not published"
        )

    return article


@router.post("/article/{article_id}/rate", response_model=ArticleResponse)
async def rate_article(
    topic: str,
    article_id: int,
    request: RateArticleRequest,
    user_topic: Tuple[dict, str] = Depends(require_reader_for_topic),
    db: Session = Depends(get_db)
):
    """
    Rate a published article (1-5 stars).
    Readers can only rate published articles.

    Args:
        topic: Topic slug from URL path
        article_id: Article ID
        request: Rating request with rating value (1-5)

    Returns:
        Updated article with new rating
    """
    user, validated_topic = user_topic

    # Validate article belongs to this topic
    validate_article_topic(validated_topic, article_id, db)

    # Check article is published before allowing rating
    article = ContentService.get_article(db, article_id, increment_readership=False)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )
    if article["status"] != "published":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only rate published articles"
        )

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


@router.get("/search")
async def search_articles(
    topic: str,
    q: Optional[str] = None,
    headline: Optional[str] = None,
    keywords: Optional[str] = None,
    author: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    limit: int = 10,
    user_topic: Tuple[dict, str] = Depends(require_reader_for_topic),
    db: Session = Depends(get_db)
):
    """
    Advanced search for published articles with multiple criteria.
    Readers can only search published articles.

    Args:
        topic: Topic slug from URL path
        q: General search query (searches headline, keywords, content)
        headline: Filter by headline (partial match)
        keywords: Filter by keywords (partial match)
        author: Filter by author name (partial match)
        created_after: Filter articles created after this date (ISO format)
        created_before: Filter articles created before this date (ISO format)
        limit: Maximum number of results (default: 10, max: 50)

    Returns:
        List of matching published articles
    """
    user, validated_topic = user_topic
    limit = min(limit, 50)

    # Convert "all" to None for cross-topic search
    search_topic = None if validated_topic == "all" else validated_topic

    # Readers can only search published articles
    articles = ContentService.search_articles(
        db=db,
        topic=search_topic,
        query=q,
        headline=headline,
        keywords=keywords,
        author=author,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        status="published"
    )

    return articles


@router.get("/published", response_model=List[ArticleResponse])
async def get_published_articles(
    topic: str,
    limit: int = 10,
    user_topic: Tuple[dict, str] = Depends(require_reader_for_topic),
    db: Session = Depends(get_db)
):
    """
    Get published articles for a topic.

    Args:
        topic: Topic slug from URL path
        limit: Maximum number of articles (default: 10, max: 50)

    Returns:
        List of published articles
    """
    user, validated_topic = user_topic
    limit = min(limit, 50)
    articles = ContentService.get_published_articles(db, validated_topic, limit)
    return articles


@router.get("/article/{article_id}/pdf")
async def download_article_pdf(
    topic: str,
    article_id: int,
    user_topic: Tuple[dict, str] = Depends(require_reader_for_topic),
    db: Session = Depends(get_db)
):
    """
    Download published article as PDF.
    Readers can only download PDFs of published articles.

    Args:
        topic: Topic slug from URL path
        article_id: Article ID

    Returns:
        PDF file as streaming response
    """
    user, validated_topic = user_topic

    # Validate article belongs to this topic
    validate_article_topic(validated_topic, article_id, db)

    article = ContentService.get_article(db, article_id, increment_readership=False)

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

    # Readers can only download published articles
    if article["status"] != "published":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only download published articles"
        )

    try:
        pdf_buffer = PDFService.generate_article_pdf(
            headline=article["headline"],
            content=article["content"],
            topic=article["topic"],
            created_at=article["created_at"],
            keywords=article.get("keywords"),
            readership_count=article["readership_count"],
            rating=article.get("rating"),
            rating_count=article["rating_count"],
            db=db
        )

        # Create a safe filename from the headline
        safe_headline = "".join(
            c for c in article["headline"] if c.isalnum() or c in (' ', '-', '_')
        ).rstrip()
        safe_headline = safe_headline.replace(' ', '_')[:50]
        filename = f"{safe_headline}_article_{article_id}.pdf"

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


@router.get("/article/{article_id}/resources")
async def get_article_publication_resources(
    topic: str,
    article_id: int,
    user_topic: Tuple[dict, str] = Depends(require_reader_for_topic),
    db: Session = Depends(get_db)
):
    """
    Get publication resource URLs for a published article.

    Returns hash_ids that can be used with /api/r/{hash_id}
    for public access to HTML and PDF versions.

    Args:
        topic: Topic slug from URL path
        article_id: Article ID

    Returns:
        Resource URLs and hash_ids for popup, HTML, and PDF versions
    """
    from services.article_resource_service import ArticleResourceService

    user, validated_topic = user_topic

    # Validate article belongs to this topic
    validate_article_topic(validated_topic, article_id, db)

    article = ContentService.get_article(db, article_id, increment_readership=False)
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    if article["status"] != "published":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only published articles have publication resources"
        )

    resources = ArticleResourceService.get_article_publication_resources(db, article_id)

    # Build URLs using public resource endpoint
    base_url = "/api/r"
    return {
        "article_id": article_id,
        "resources": {
            "popup_url": f"{base_url}/{resources['popup']}" if resources['popup'] else None,
            "html_url": f"{base_url}/{resources['html']}" if resources['html'] else None,
            "pdf_url": f"{base_url}/{resources['pdf']}" if resources['pdf'] else None
        },
        "hash_ids": resources
    }
