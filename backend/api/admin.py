"""API endpoints for admin functions.

This module provides two routers:
- topic_router: /api/admin/{topic}/... - Requires global:admin OR {topic}:admin
- global_router: /api/admin/global/... - Requires global:admin only
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from database import get_db
from models import ContentArticle, User
from services.content_service import ContentService
from services.vector_service import VectorService
from services.article_resource_service import ArticleResourceService
from services.resource_service import ResourceService
from dependencies import (
    require_admin,
    require_admin_for_topic,
    validate_article_topic,
    get_valid_topics,
)
from services.content_cache import ContentCache
import logging

logger = logging.getLogger("uvicorn")


# =============================================================================
# Two Routers: Topic-specific and Global
# =============================================================================

# Topic-specific admin: /api/admin/{topic}/...
# Requires: global:admin OR {topic}:admin
topic_router = APIRouter(prefix="/api/admin/{topic}", tags=["admin-topic"])

# Global admin only: /api/admin/global/...
# Requires: global:admin
global_router = APIRouter(prefix="/api/admin/global", tags=["admin-global"])


# =============================================================================
# Pydantic Models
# =============================================================================


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
    status: str
    priority: int
    is_sticky: bool
    created_at: str
    updated_at: str
    created_by_agent: str
    is_active: bool


class ArticleReorderItem(BaseModel):
    """Item for reordering articles."""
    id: int
    priority: int


class ArticleReorderRequest(BaseModel):
    """Request model for bulk reordering articles."""
    articles: List[ArticleReorderItem]


class ArticleSyncRequest(BaseModel):
    """Request model for syncing article content to ChromaDB."""
    article_id: int
    headline: str
    content: str
    topic: str
    author: Optional[str] = None
    editor: Optional[str] = None
    keywords: Optional[str] = None
    status: str = "published"


class BulkArticleSyncRequest(BaseModel):
    """Request model for bulk syncing articles to ChromaDB."""
    articles: List[ArticleSyncRequest]


# =============================================================================
# Topic-Specific Admin Endpoints
# Require: global:admin OR {topic}:admin
# =============================================================================


@topic_router.get("/articles", response_model=List[ArticleResponse])
async def get_all_articles(
    topic: str,
    offset: int = 0,
    limit: int = 20,
    user_topic: Tuple[dict, str] = Depends(require_admin_for_topic),
    db: Session = Depends(get_db)
):
    """
    Get all articles for a topic with pagination (including inactive).

    Args:
        topic: Topic slug from URL path
        offset: Number of articles to skip (default: 0)
        limit: Maximum number of articles to return (default: 20, max: 100)

    Returns:
        List of articles including inactive ones
    """
    user, validated_topic = user_topic
    limit = min(limit, 100)
    articles = ContentService.get_all_articles_admin(db, validated_topic, offset, limit)
    return articles


@topic_router.delete("/article/{article_id}")
async def delete_article(
    topic: str,
    article_id: int,
    user_topic: Tuple[dict, str] = Depends(require_admin_for_topic),
    db: Session = Depends(get_db)
):
    """
    Soft delete an article.

    Args:
        topic: Topic slug from URL path
        article_id: Article ID to delete

    Returns:
        Success message
    """
    user, validated_topic = user_topic

    # Validate article belongs to this topic
    validate_article_topic(validated_topic, article_id, db)

    try:
        ContentService.delete_article(db, article_id)
        return {"message": f"Article {article_id} deleted successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@topic_router.post("/article/{article_id}/reactivate")
async def reactivate_article(
    topic: str,
    article_id: int,
    user_topic: Tuple[dict, str] = Depends(require_admin_for_topic),
    db: Session = Depends(get_db)
):
    """
    Reactivate a soft-deleted article.

    Args:
        topic: Topic slug from URL path
        article_id: Article ID to reactivate

    Returns:
        Success message
    """
    user, validated_topic = user_topic

    # Validate article belongs to this topic
    validate_article_topic(validated_topic, article_id, db)

    try:
        ContentService.reactivate_article(db, article_id)
        return {"message": f"Article {article_id} reactivated successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@topic_router.post("/article/{article_id}/recall")
async def recall_article(
    topic: str,
    article_id: int,
    user_topic: Tuple[dict, str] = Depends(require_admin_for_topic),
    db: Session = Depends(get_db)
):
    """
    Recall a published article (move back to draft status).

    Args:
        topic: Topic slug from URL path
        article_id: Article ID to recall

    Returns:
        Success message with updated article
    """
    user, validated_topic = user_topic

    # Validate article belongs to this topic
    validate_article_topic(validated_topic, article_id, db)

    try:
        updated = ContentService.recall_article(db, article_id)
        return {"message": f"Article {article_id} recalled to draft", "article": updated}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@topic_router.post("/article/{article_id}/regenerate-resources")
async def regenerate_article_resources(
    topic: str,
    article_id: int,
    user_topic: Tuple[dict, str] = Depends(require_admin_for_topic),
    db: Session = Depends(get_db)
):
    """
    Regenerate publication resources (HTML, PDF) for a published article.

    Args:
        topic: Topic slug from URL path
        article_id: Article ID

    Returns:
        Success message with resource hash IDs
    """
    user, validated_topic = user_topic

    # Validate article belongs to this topic
    validate_article_topic(validated_topic, article_id, db)

    article = ContentService.get_article(db, article_id, increment_readership=False)
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    if article["status"] != "published":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only published articles can have resources regenerated"
        )

    admin_email = user.get("email", "")
    admin_user = db.query(User).filter(User.email == admin_email).first()
    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin user not found"
        )

    # Delete existing ARTICLE resources first
    ArticleResourceService.delete_article_resources(db, article_id)

    # Get article content from ChromaDB
    content = VectorService.get_article_content(article_id)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve article content from vector database"
        )

    # Create new resources
    article_model = db.query(ContentArticle).filter(ContentArticle.id == article_id).first()
    ArticleResourceService.create_article_resources(db, article_model, content, admin_user.id)

    resources = ArticleResourceService.get_article_publication_resources(db, article_id)

    return {
        "message": f"Resources regenerated for article {article_id}",
        "resources": resources
    }


# =============================================================================
# Global Admin Endpoints
# Require: global:admin ONLY
# =============================================================================


@global_router.delete("/article/{article_id}/purge")
async def purge_article(
    article_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Permanently delete an article and all related data.
    This action cannot be undone.

    Args:
        article_id: Article ID to purge

    Returns:
        Success message
    """
    try:
        ContentService.purge_article(db, article_id)
        return {"message": f"Article {article_id} permanently deleted"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@global_router.post("/articles/reorder")
async def reorder_articles(
    request: ArticleReorderRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Bulk update priority for multiple articles.

    Accepts a list of {id, priority} pairs and updates each article's priority.

    Args:
        request: List of article IDs and their new priorities

    Returns:
        List of updated article IDs
    """
    updated = []
    for item in request.articles:
        article = db.query(ContentArticle).filter(ContentArticle.id == item.id).first()
        if article:
            article.priority = item.priority
            updated.append(item.id)
            ContentCache.invalidate_article(item.id)
            ContentCache.invalidate_topic(article.topic)

    db.commit()

    return {
        "message": f"Reordered {len(updated)} articles",
        "updated": updated
    }


@global_router.post("/articles/regenerate-all-resources")
async def regenerate_all_published_resources(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Regenerate publication resources for ALL published articles that don't have resources yet.

    Returns:
        Summary of processed articles with success/failure status
    """
    admin_email = admin.get("email", "")
    admin_user = db.query(User).filter(User.email == admin_email).first()
    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin user not found"
        )

    # Get all published articles
    articles = db.query(ContentArticle).filter(ContentArticle.status == "published").all()

    results = []
    for article_model in articles:
        article_id = article_model.id

        # Check if resources already exist
        existing = ArticleResourceService.get_article_publication_resources(db, article_id)
        if existing.get("html") or existing.get("pdf"):
            results.append({
                "article_id": article_id,
                "headline": article_model.headline,
                "status": "skipped",
                "reason": "Resources already exist"
            })
            continue

        # Get article content from ChromaDB
        content = VectorService.get_article_content(article_id)
        if not content:
            results.append({
                "article_id": article_id,
                "headline": article_model.headline,
                "status": "error",
                "reason": "Could not retrieve content from vector database"
            })
            continue

        try:
            ArticleResourceService.create_article_resources(db, article_model, content, admin_user.id)
            resources = ArticleResourceService.get_article_publication_resources(db, article_id)
            results.append({
                "article_id": article_id,
                "headline": article_model.headline,
                "status": "success",
                "resources": resources
            })
        except Exception as e:
            results.append({
                "article_id": article_id,
                "headline": article_model.headline,
                "status": "error",
                "reason": str(e)
            })

    successful = len([r for r in results if r["status"] == "success"])
    skipped = len([r for r in results if r["status"] == "skipped"])
    failed = len([r for r in results if r["status"] == "error"])

    return {
        "message": f"Processed {len(results)} articles: {successful} regenerated, {skipped} skipped, {failed} failed",
        "results": results
    }


@global_router.post("/sync-article")
async def sync_article_to_chromadb(
    request: ArticleSyncRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Sync article content to ChromaDB.

    Used to populate ChromaDB after database migration.

    Args:
        request: Article data to sync

    Returns:
        Success status
    """
    from datetime import datetime

    metadata = {
        "topic": request.topic,
        "headline": request.headline,
        "author": request.author or "",
        "editor": request.editor or "",
        "keywords": request.keywords or "",
        "status": request.status,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    success = VectorService.add_article(
        article_id=request.article_id,
        headline=request.headline,
        content=request.content,
        metadata=metadata
    )

    if success:
        logger.info(f"Synced article {request.article_id} to ChromaDB")
        return {"message": f"Article {request.article_id} synced to ChromaDB", "success": True}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to sync article to ChromaDB"
        )


@global_router.post("/sync-articles-bulk")
async def sync_articles_bulk(
    request: BulkArticleSyncRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Bulk sync multiple articles to ChromaDB.

    Args:
        request: List of articles to sync

    Returns:
        Summary of sync results
    """
    from datetime import datetime

    results = []
    for article in request.articles:
        metadata = {
            "topic": article.topic,
            "headline": article.headline,
            "author": article.author or "",
            "editor": article.editor or "",
            "keywords": article.keywords or "",
            "status": article.status,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        success = VectorService.add_article(
            article_id=article.article_id,
            headline=article.headline,
            content=article.content,
            metadata=metadata
        )

        results.append({
            "article_id": article.article_id,
            "headline": article.headline[:50],
            "success": success
        })

    successful = len([r for r in results if r["success"]])
    failed = len([r for r in results if not r["success"]])

    return {
        "message": f"Synced {successful} articles, {failed} failed",
        "results": results
    }


@global_router.post("/resources/purge-orphans")
async def purge_orphan_resources(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Purge all orphaned resources (resources with no article or group links).

    This performs HARD DELETE - removes files and all data permanently.

    Returns:
        Count of purged resources
    """
    purged_count = ResourceService.purge_all_orphans(db)

    return {
        "message": f"Purged {purged_count} orphan resources",
        "purged_count": purged_count
    }
