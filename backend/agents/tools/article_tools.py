"""
Article tools for content management operations.

These tools provide article search, creation, and management capabilities
for analysts and editors working with the content system.
"""

from typing import Optional, List
from langchain_core.tools import tool
import json
import logging

logger = logging.getLogger("uvicorn")


# =============================================================================
# Article Query Tools (Reader+)
# =============================================================================

@tool
def search_articles(
    query: str,
    topic: Optional[str] = None,
    limit: int = 10,
    include_drafts: bool = False,
) -> str:
    """
    Search for articles matching a query.

    Use this tool to find articles related to a topic or query.
    Returns published articles by default. Set include_drafts=True
    to include draft articles (requires analyst permission).

    Args:
        query: Search query string
        topic: Optional topic slug to filter (macro, equity, fixed_income, esg)
        limit: Maximum number of results (default 10)
        include_drafts: Include draft articles (requires analyst+ permission)

    Returns:
        JSON string with matching articles
    """
    try:
        # Import here to avoid circular imports
        from database import SessionLocal
        from services.content_service import ContentService

        db = SessionLocal()
        try:
            articles = ContentService.search_articles(
                db=db,
                topic=topic,
                query=query,
                limit=limit,
            )

            formatted = [
                {
                    "id": a.get("id"),
                    "headline": a.get("headline"),
                    "topic": a.get("topic"),
                    "status": a.get("status"),
                    "author": a.get("author"),
                    "created_at": a.get("created_at"),
                }
                for a in articles
            ]

            return json.dumps({
                "success": True,
                "message": f"Found {len(formatted)} articles",
                "articles": formatted,
                "query": query,
                "topic": topic,
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error searching articles: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error searching articles: {str(e)}",
            "articles": [],
        })


@tool
def get_article(article_id: int) -> str:
    """
    Get a specific article by ID with its content.

    Use this tool to retrieve full article details including content.
    Note: Draft articles require analyst+ permission.

    Args:
        article_id: The ID of the article to retrieve

    Returns:
        JSON string with article details and content
    """
    try:
        from database import SessionLocal
        from services.content_service import ContentService

        db = SessionLocal()
        try:
            article = ContentService.get_article(db, article_id)

            if not article:
                return json.dumps({
                    "success": False,
                    "message": f"Article {article_id} not found",
                    "article": None,
                })

            # Content is already included in the article dict from ContentService
            return json.dumps({
                "success": True,
                "message": f"Retrieved article {article_id}",
                "article": {
                    "id": article.get("id"),
                    "headline": article.get("headline"),
                    "topic": article.get("topic"),
                    "status": article.get("status"),
                    "author": article.get("author"),
                    "editor": article.get("editor"),
                    "keywords": article.get("keywords"),
                    "content": article.get("content", ""),
                    "created_at": article.get("created_at"),
                    "updated_at": article.get("updated_at"),
                },
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error getting article {article_id}: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error getting article: {str(e)}",
            "article": None,
        })


# =============================================================================
# Article Creation Tools (Analyst+)
# =============================================================================

@tool
def create_draft_article(
    headline: str,
    topic: str,
    author: str,
    keywords: Optional[str] = None,
) -> str:
    """
    Create a new draft article.

    Use this tool to create a new article in draft status.
    Requires analyst+ permission for the topic.

    Args:
        headline: Article headline (max 200 chars)
        topic: Topic slug (macro, equity, fixed_income, esg)
        author: Author name
        keywords: Optional comma-separated keywords

    Returns:
        JSON string with created article info
    """
    try:
        from database import SessionLocal
        from services.content_service import ContentService
        from models import ArticleStatus

        db = SessionLocal()
        try:
            article = ContentService.create_article(
                db=db,
                topic=topic,
                headline=headline[:200],
                author=author,
                keywords=keywords,
                status=ArticleStatus.DRAFT,
            )

            return json.dumps({
                "success": True,
                "message": f"Created draft article {article.id}",
                "article_id": article.id,
                "headline": article.headline,
                "topic": topic,
                "status": "draft",
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error creating draft article: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error creating article: {str(e)}",
            "article_id": None,
        })


@tool
def write_article_content(
    article_id: int,
    content: str,
) -> str:
    """
    Write or update content for an article.

    Use this tool to write markdown content to an article.
    Only works on articles in DRAFT or EDITOR status.
    Requires analyst+ permission for the article's topic.

    Args:
        article_id: ID of the article to update
        content: Markdown content to write

    Returns:
        JSON string with update result
    """
    try:
        from database import SessionLocal
        from services.content_service import ContentService
        from models import ContentArticle, ArticleStatus

        db = SessionLocal()
        try:
            # Check article exists and status
            article = db.query(ContentArticle).filter(
                ContentArticle.id == article_id
            ).first()

            if not article:
                return json.dumps({
                    "success": False,
                    "message": f"Article {article_id} not found",
                })

            if article.status not in [ArticleStatus.DRAFT, ArticleStatus.EDITOR]:
                return json.dumps({
                    "success": False,
                    "message": f"Cannot modify article in status '{article.status.value}'",
                })

            ContentService.update_article(
                db=db,
                article_id=article_id,
                content=content,
            )

            return json.dumps({
                "success": True,
                "message": f"Updated content for article {article_id}",
                "article_id": article_id,
                "content_length": len(content),
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error writing article content: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error writing content: {str(e)}",
        })


@tool
def submit_for_review(article_id: int) -> str:
    """
    Submit a draft article for editorial review.

    Use this tool to change article status from DRAFT to EDITOR.
    The article will then be visible to editors for review.
    Requires analyst+ permission for the article's topic.

    Args:
        article_id: ID of the article to submit

    Returns:
        JSON string with submission result
    """
    try:
        from database import SessionLocal
        from models import ContentArticle, ArticleStatus

        db = SessionLocal()
        try:
            article = db.query(ContentArticle).filter(
                ContentArticle.id == article_id
            ).first()

            if not article:
                return json.dumps({
                    "success": False,
                    "message": f"Article {article_id} not found",
                })

            if article.status != ArticleStatus.DRAFT:
                return json.dumps({
                    "success": False,
                    "message": f"Article must be in DRAFT status, currently '{article.status.value}'",
                })

            article.status = ArticleStatus.EDITOR
            db.commit()

            return json.dumps({
                "success": True,
                "message": "Article submitted for editorial review",
                "article_id": article_id,
                "new_status": "editor",
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error submitting article for review: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error submitting article: {str(e)}",
        })


@tool
def attach_resource_to_article(
    article_id: int,
    resource_id: int,
) -> str:
    """
    Attach a resource to an article.

    Use this tool to link a resource (data, chart, table) to an article.
    Requires analyst+ permission for the article's topic.

    Args:
        article_id: ID of the article
        resource_id: ID of the resource to attach

    Returns:
        JSON string with attachment result
    """
    try:
        from database import SessionLocal
        from services.article_resource_service import ArticleResourceService

        db = SessionLocal()
        try:
            resource_service = ArticleResourceService(db)
            resource_service.attach_resource(article_id, resource_id)

            return json.dumps({
                "success": True,
                "message": f"Attached resource {resource_id} to article {article_id}",
                "article_id": article_id,
                "resource_id": resource_id,
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error attaching resource: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error attaching resource: {str(e)}",
        })


# =============================================================================
# Tool Collections
# =============================================================================

def get_article_query_tools() -> List:
    """Get article query tools (Reader+)."""
    return [
        search_articles,
        get_article,
    ]


def get_article_write_tools() -> List:
    """Get article write tools (Analyst+)."""
    return [
        create_draft_article,
        write_article_content,
        submit_for_review,
        attach_resource_to_article,
    ]


def get_all_article_tools() -> List:
    """Get all article tools."""
    return get_article_query_tools() + get_article_write_tools()
