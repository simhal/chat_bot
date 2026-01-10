"""API endpoints for editor access to content articles.

These endpoints require editor or admin role for the specified topic.
URL pattern: /api/editor/{topic}/...
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from database import get_db
from models import ContentArticle
from services.content_service import ContentService
from services.vector_service import VectorService
from dependencies import (
    get_current_user,
    require_editor_for_topic,
    validate_article_topic,
)
import logging

logger = logging.getLogger("uvicorn")


router = APIRouter(prefix="/api/editor/{topic}", tags=["editor"])


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


class RejectArticleRequest(BaseModel):
    feedback: Optional[str] = None  # Optional feedback for the analyst


# =============================================================================
# Editor Endpoints - Require {topic}:editor+ permission
# =============================================================================


@router.get("/articles", response_model=List[ArticleResponse])
async def get_pending_articles(
    topic: str,
    offset: int = 0,
    limit: int = 20,
    user_topic: Tuple[dict, str] = Depends(require_editor_for_topic),
    db: Session = Depends(get_db)
):
    """
    Get articles pending editor review (status='editor').

    Args:
        topic: Topic slug from URL path
        offset: Number of articles to skip (default: 0)
        limit: Maximum number of articles to return (default: 20, max: 100)

    Returns:
        List of articles in 'editor' status for the topic
    """
    user, validated_topic = user_topic
    limit = min(limit, 100)
    articles = ContentService.get_articles_by_status(db, validated_topic, "editor", offset, limit)
    return articles


@router.post("/article/{article_id}/reject")
async def reject_article(
    topic: str,
    article_id: int,
    request: RejectArticleRequest = RejectArticleRequest(),
    user_topic: Tuple[dict, str] = Depends(require_editor_for_topic),
    db: Session = Depends(get_db)
):
    """
    Reject an article in editor review (moves back to 'draft' status).

    Args:
        topic: Topic slug from URL path
        article_id: Article ID
        request: Optional feedback for the analyst

    Returns:
        Success message with updated article
    """
    user, validated_topic = user_topic

    # Validate article belongs to this topic
    article_model = validate_article_topic(validated_topic, article_id, db)

    # Get article dict for status check
    article = ContentService.get_article(db, article_id, increment_readership=False)

    # Verify article is in editor status (normalize for comparison)
    article_status = article["status"]
    if hasattr(article_status, 'value'):
        status_str = article_status.value.lower()
    else:
        status_str = str(article_status).lower()
    if status_str != "editor":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only articles in editor review can be rejected. Current status: '{status_str}'"
        )

    try:
        updated = ContentService.update_article_status(db, article_id, "draft")
        result = {"message": "Article rejected and sent back to draft", "article": updated}
        if request.feedback:
            result["feedback"] = request.feedback
            logger.info(f"Article {article_id} rejected with feedback: {request.feedback[:100]}...")
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/article/{article_id}/publish")
async def publish_article(
    topic: str,
    article_id: int,
    user_topic: Tuple[dict, str] = Depends(require_editor_for_topic),
    db: Session = Depends(get_db)
):
    """
    Publish an article (moves from 'editor' to 'published' status).
    Creates publication resources (HTML, PDF).

    Args:
        topic: Topic slug from URL path
        article_id: Article ID

    Returns:
        Success message with updated article and resource creation status
    """
    from services.article_resource_service import ArticleResourceService

    user, validated_topic = user_topic

    # Validate article belongs to this topic
    article_model = validate_article_topic(validated_topic, article_id, db)
    logger.info(f"Publish article {article_id}: article_model.status={article_model.status}")

    # Query fresh article status directly from database (bypass any caching)
    # Use db.expire_all() to clear session cache, then re-query
    db.expire_all()
    fresh_article = db.query(ContentArticle).filter(ContentArticle.id == article_id).first()
    logger.info(f"Publish article {article_id}: fresh_article.status={fresh_article.status if fresh_article else 'None'}")

    # Also try raw SQL to compare
    from sqlalchemy import text
    raw_result = db.execute(text(f"SELECT status FROM content_articles WHERE id = {article_id}")).fetchone()
    logger.info(f"Publish article {article_id}: RAW SQL status={raw_result[0] if raw_result else 'None'}")

    # Verify article is in editor status
    article_status = fresh_article.status if fresh_article else article_model.status
    # Normalize status for comparison (handle enum or string)
    if hasattr(article_status, 'value'):
        status_str = article_status.value.lower()
    else:
        status_str = str(article_status).lower()
    logger.info(f"Publish article {article_id}: FINAL status='{status_str}' (raw: {article_status}, type: {type(article_status)})")
    if status_str != "editor":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only articles in editor review can be published. Current status: '{status_str}'"
        )

    try:
        # Use publish_article_with_editor which sets editor to publisher's email
        editor_email = user.get("email", "")
        updated = ContentService.publish_article_with_editor(db, article_id, editor_email)

        # Create publication resources (HTML, PDF) on publish
        user_id = int(user.get("sub"))
        resources_created = False
        resources_warning = None

        if article_model:
            content = VectorService.get_article_content(article_id)
            if content:
                parent, html_res, pdf_res = ArticleResourceService.create_article_resources(
                    db=db,
                    article=article_model,
                    content=content,
                    editor_user_id=user_id
                )
                if parent:
                    logger.info(f"Created publication resources for article {article_id}")
                    resources_created = True
            else:
                logger.warning(f"No content found for article {article_id} - publication resources not created")
                resources_warning = "Article content not found in vector database. Please re-save the article and publish again to generate HTML/PDF resources."

        result = {"message": "Article published successfully", "article": updated, "resources_created": resources_created}
        if resources_warning:
            result["warning"] = resources_warning
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/article/{article_id}", response_model=ArticleResponse)
async def get_article_for_review(
    topic: str,
    article_id: int,
    user_topic: Tuple[dict, str] = Depends(require_editor_for_topic),
    db: Session = Depends(get_db)
):
    """
    Get a specific article for editor view.
    Editors can access articles with status 'editor' or 'published'.
    Does not increment readership counter.

    Args:
        topic: Topic slug from URL path
        article_id: Article ID

    Returns:
        Article details
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

    # Editors can only access editor and published articles
    if article["status"] not in ["editor", "published"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Editors can only access articles in editor or published status"
        )

    return article


@router.get("/all-articles", response_model=List[ArticleResponse])
async def get_all_articles_for_editor(
    topic: str,
    offset: int = 0,
    limit: int = 20,
    status_filter: Optional[str] = None,
    user_topic: Tuple[dict, str] = Depends(require_editor_for_topic),
    db: Session = Depends(get_db)
):
    """
    Get articles for editor view (published and editor status only).
    Editors cannot see draft articles.

    Args:
        topic: Topic slug from URL path
        offset: Number of articles to skip (default: 0)
        limit: Maximum number of articles to return (default: 20, max: 100)
        status_filter: Optional filter by status (editor or published only)

    Returns:
        List of articles in editor or published status
    """
    user, validated_topic = user_topic
    limit = min(limit, 100)

    # Editors can only see editor and published articles
    allowed_statuses = ["editor", "published"]

    if status_filter:
        if status_filter not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter. Editors can only view: {', '.join(allowed_statuses)}"
            )
        articles = ContentService.get_articles_by_status(db, validated_topic, status_filter, offset, limit)
    else:
        # Get both editor and published articles
        # Use search_articles with statuses filter
        articles = ContentService.search_articles(
            db=db,
            topic=validated_topic,
            statuses=allowed_statuses,
            limit=limit
        )
        # Apply offset manually since search doesn't support it
        if offset > 0:
            articles = articles[offset:]

    return articles
