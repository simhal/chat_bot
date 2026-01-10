"""
Editor tools for editorial review and HITL publishing workflow.

These tools provide editorial capabilities for reviewing, approving,
and publishing articles through the human-in-the-loop workflow.
"""

from typing import Optional, List
from langchain_core.tools import tool
import json
import logging
from datetime import datetime, timedelta
import uuid

logger = logging.getLogger("uvicorn")


# =============================================================================
# Editorial Review Tools (Editor+)
# =============================================================================

@tool
def review_article(article_id: int) -> str:
    """
    Get an article for editorial review.

    Use this tool to retrieve an article in EDITOR status for review.
    Returns article details and content for editorial assessment.
    Requires editor+ permission for the article's topic.

    Args:
        article_id: ID of the article to review

    Returns:
        JSON string with article details for review
    """
    try:
        from database import SessionLocal
        from models import ContentArticle, ArticleStatus
        from services.content_service import ContentService

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

            if article.status != ArticleStatus.EDITOR:
                return json.dumps({
                    "success": False,
                    "message": f"Article must be in EDITOR status, currently '{article.status.value}'",
                })

            # Get content
            from services.vector_service import VectorService
            content = VectorService.get_article_content(article_id)

            return json.dumps({
                "success": True,
                "message": f"Article {article_id} ready for review",
                "article": {
                    "id": article.id,
                    "headline": article.headline,
                    "topic": article.topic_slug,
                    "status": article.status.value,
                    "author": article.author,
                    "keywords": article.keywords,
                    "content_length": len(content) if content else 0,
                },
                "content_preview": content[:2000] if content else "",
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error reviewing article {article_id}: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error reviewing article: {str(e)}",
        })


@tool
def request_changes(
    article_id: int,
    notes: str,
) -> str:
    """
    Request changes to an article (return to DRAFT).

    Use this tool to send an article back to the author for revisions.
    Changes status from EDITOR to DRAFT with editor notes.
    Requires editor+ permission for the article's topic.

    Args:
        article_id: ID of the article
        notes: Editor notes explaining requested changes

    Returns:
        JSON string with result
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

            if article.status not in [ArticleStatus.EDITOR, ArticleStatus.PENDING_APPROVAL]:
                return json.dumps({
                    "success": False,
                    "message": f"Cannot request changes for article in status '{article.status.value}'",
                })

            # Update status and add notes
            article.status = ArticleStatus.DRAFT
            article.editor = f"Changes requested: {notes[:200]}"
            db.commit()

            return json.dumps({
                "success": True,
                "message": "Article returned to draft for revisions",
                "article_id": article_id,
                "new_status": "draft",
                "notes": notes,
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error requesting changes for article {article_id}: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error requesting changes: {str(e)}",
        })


@tool
def submit_for_approval(
    article_id: int,
    editor_notes: Optional[str] = None,
) -> str:
    """
    Submit an article for human approval (HITL).

    Use this tool to create an approval request for an article.
    This triggers the human-in-the-loop workflow and pauses
    the agent until a human reviewer approves or rejects.
    Requires editor+ permission for the article's topic.

    Args:
        article_id: ID of the article to submit
        editor_notes: Optional notes from the editor

    Returns:
        JSON string with approval request details
    """
    try:
        from database import SessionLocal
        from models import ContentArticle, ArticleStatus, ApprovalRequest, ApprovalStatus

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

            if article.status != ArticleStatus.EDITOR:
                return json.dumps({
                    "success": False,
                    "message": f"Article must be in EDITOR status, currently '{article.status.value}'",
                })

            # Create approval request
            thread_id = str(uuid.uuid4())
            expires_at = datetime.utcnow() + timedelta(hours=24)

            approval_request = ApprovalRequest(
                article_id=article_id,
                editor_notes=editor_notes,
                status=ApprovalStatus.PENDING,
                expires_at=expires_at,
                thread_id=thread_id,
            )

            db.add(approval_request)

            # Update article status
            article.status = ArticleStatus.PENDING_APPROVAL

            db.commit()

            return json.dumps({
                "success": True,
                "status": "awaiting_approval",
                "message": "Article submitted for approval. Awaiting human review.",
                "article_id": article_id,
                "approval_request_id": approval_request.id,
                "thread_id": thread_id,
                "expires_at": expires_at.isoformat(),
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error submitting article {article_id} for approval: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error submitting for approval: {str(e)}",
        })


@tool
def process_approval(
    article_id: int,
    approved: bool,
    review_notes: Optional[str] = None,
) -> str:
    """
    Process an approval decision.

    Use this tool to approve or reject a pending article.
    If approved, article status changes to PUBLISHED.
    If rejected, article status changes back to EDITOR.
    Requires editor+ permission for the article's topic.

    Args:
        article_id: ID of the article
        approved: Whether to approve (True) or reject (False)
        review_notes: Optional notes from the reviewer

    Returns:
        JSON string with result and new status
    """
    try:
        from database import SessionLocal
        from models import ContentArticle, ArticleStatus, ApprovalRequest, ApprovalStatus

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

            if article.status != ArticleStatus.PENDING_APPROVAL:
                return json.dumps({
                    "success": False,
                    "message": f"Article is not pending approval, status: '{article.status.value}'",
                })

            # Find pending approval request
            approval_request = db.query(ApprovalRequest).filter(
                ApprovalRequest.article_id == article_id,
                ApprovalRequest.status == ApprovalStatus.PENDING,
            ).first()

            if not approval_request:
                return json.dumps({
                    "success": False,
                    "message": "No pending approval request found",
                })

            # Update approval request
            approval_request.reviewed_at = datetime.utcnow()
            approval_request.review_notes = review_notes
            approval_request.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED

            # Update article status
            if approved:
                article.status = ArticleStatus.PUBLISHED
                new_status = "published"
                message = "Article has been published."
            else:
                article.status = ArticleStatus.EDITOR
                new_status = "editor"
                message = "Article rejected. Returned to editor status."

            db.commit()

            return json.dumps({
                "success": True,
                "message": message,
                "article_id": article_id,
                "new_status": new_status,
                "approved": approved,
                "review_notes": review_notes,
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error processing approval for article {article_id}: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error processing approval: {str(e)}",
        })


@tool
def get_pending_approvals(topic: Optional[str] = None) -> str:
    """
    Get list of pending approval requests.

    Use this tool to see all articles awaiting approval.
    Can filter by topic. Requires editor+ permission.

    Args:
        topic: Optional topic slug to filter

    Returns:
        JSON string with list of pending approvals
    """
    try:
        from database import SessionLocal
        from models import ApprovalRequest, ApprovalStatus, ContentArticle

        db = SessionLocal()
        try:
            query = db.query(ApprovalRequest).join(ContentArticle).filter(
                ApprovalRequest.status == ApprovalStatus.PENDING,
            )

            if topic:
                query = query.filter(ContentArticle.topic_slug == topic)

            approvals = query.order_by(ApprovalRequest.requested_at.desc()).all()

            formatted = [
                {
                    "id": a.id,
                    "article_id": a.article_id,
                    "article_headline": a.article.headline if a.article else "Unknown",
                    "topic": a.article.topic_slug if a.article else None,
                    "requested_at": a.requested_at.isoformat() if a.requested_at else None,
                    "expires_at": a.expires_at.isoformat() if a.expires_at else None,
                    "editor_notes": a.editor_notes,
                }
                for a in approvals
            ]

            return json.dumps({
                "success": True,
                "message": f"Found {len(formatted)} pending approvals",
                "pending_approvals": formatted,
                "count": len(formatted),
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error getting pending approvals: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error getting approvals: {str(e)}",
            "pending_approvals": [],
        })


# =============================================================================
# Tool Collections
# =============================================================================

def get_editor_review_tools() -> List:
    """Get editor review tools (Editor+)."""
    return [
        review_article,
        request_changes,
        get_pending_approvals,
    ]


def get_editor_approval_tools() -> List:
    """Get editor approval tools (Editor+, HITL)."""
    return [
        submit_for_approval,
        process_approval,
    ]


def get_all_editor_tools() -> List:
    """Get all editor tools."""
    return get_editor_review_tools() + get_editor_approval_tools()
