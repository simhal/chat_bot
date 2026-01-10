"""API endpoints for HITL approval workflow."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from services.permission_service import PermissionService
import logging

logger = logging.getLogger("uvicorn")


router = APIRouter(prefix="/api/approvals", tags=["approvals"])


# Pydantic models for API
class ApprovalRequestResponse(BaseModel):
    id: int
    article_id: int
    article_headline: str
    topic: str
    status: str  # pending, approved, rejected, expired
    requested_by_id: Optional[int]
    requested_by_name: Optional[str]
    editor_notes: Optional[str]
    reviewed_by_id: Optional[int]
    reviewed_by_name: Optional[str]
    review_notes: Optional[str]
    requested_at: str
    reviewed_at: Optional[str]
    expires_at: Optional[str]
    thread_id: Optional[str]


class ApprovalListResponse(BaseModel):
    approvals: List[ApprovalRequestResponse]
    total_count: int


class ProcessApprovalRequest(BaseModel):
    approved: bool
    review_notes: Optional[str] = None


class ProcessApprovalResponse(BaseModel):
    approval_id: int
    article_id: int
    approved: bool
    new_article_status: str
    message: str


@router.get("", response_model=ApprovalListResponse)
async def list_pending_approvals(
    topic: Optional[str] = None,
    include_processed: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    List approval requests accessible to the current user.

    Users can only see approvals for topics they have editor+ permission on.
    Use topic parameter to filter by specific topic.
    Set include_processed=True to include approved/rejected approvals.
    """
    try:
        from models import ApprovalRequest, ApprovalStatus, ContentArticle, User as UserModel

        user_scopes = user.get("scopes", [])

        # Get accessible topics for this user (editor+)
        accessible_topics = PermissionService.get_accessible_topics(user_scopes, "editor")

        if not accessible_topics:
            return ApprovalListResponse(
                approvals=[],
                total_count=0
            )

        # Build query
        query = db.query(ApprovalRequest).join(
            ContentArticle, ApprovalRequest.article_id == ContentArticle.id
        )

        # Filter by status
        if not include_processed:
            query = query.filter(ApprovalRequest.status == ApprovalStatus.PENDING)

        # Filter by topic
        if topic:
            if topic not in accessible_topics and "*" not in accessible_topics:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No editor permission for topic '{topic}'"
                )
            query = query.filter(ContentArticle.topic_slug == topic)
        elif "*" not in accessible_topics:
            # Filter to accessible topics only
            query = query.filter(ContentArticle.topic_slug.in_(accessible_topics))

        # Order and limit
        approvals = query.order_by(ApprovalRequest.requested_at.desc()).limit(limit).all()

        # Format response
        formatted = []
        for a in approvals:
            requester = db.query(UserModel).filter(UserModel.id == a.requested_by).first() if a.requested_by else None
            reviewer = db.query(UserModel).filter(UserModel.id == a.reviewed_by).first() if a.reviewed_by else None

            formatted.append(ApprovalRequestResponse(
                id=a.id,
                article_id=a.article_id,
                article_headline=a.article.headline if a.article else "Unknown",
                topic=a.article.topic_slug if a.article else "unknown",
                status=a.status.value,
                requested_by_id=a.requested_by,
                requested_by_name=f"{requester.name} {requester.surname}".strip() if requester else None,
                editor_notes=a.editor_notes,
                reviewed_by_id=a.reviewed_by,
                reviewed_by_name=f"{reviewer.name} {reviewer.surname}".strip() if reviewer else None,
                review_notes=a.review_notes,
                requested_at=a.requested_at.isoformat() if a.requested_at else None,
                reviewed_at=a.reviewed_at.isoformat() if a.reviewed_at else None,
                expires_at=a.expires_at.isoformat() if a.expires_at else None,
                thread_id=a.thread_id,
            ))

        return ApprovalListResponse(
            approvals=formatted,
            total_count=len(formatted)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing approvals: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing approvals: {str(e)}"
        )


@router.get("/{approval_id}", response_model=ApprovalRequestResponse)
async def get_approval(
    approval_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Get a specific approval request by ID.

    User must have editor+ permission for the article's topic.
    """
    try:
        from models import ApprovalRequest, User as UserModel

        approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()

        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Approval request {approval_id} not found"
            )

        # Check permission
        user_scopes = user.get("scopes", [])
        topic = approval.article.topic_slug if approval.article else None

        if not PermissionService.check_permission(user_scopes, "editor", topic=topic):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Editor permission required for topic '{topic}'"
            )

        requester = db.query(UserModel).filter(UserModel.id == approval.requested_by).first() if approval.requested_by else None
        reviewer = db.query(UserModel).filter(UserModel.id == approval.reviewed_by).first() if approval.reviewed_by else None

        return ApprovalRequestResponse(
            id=approval.id,
            article_id=approval.article_id,
            article_headline=approval.article.headline if approval.article else "Unknown",
            topic=approval.article.topic_slug if approval.article else "unknown",
            status=approval.status.value,
            requested_by_id=approval.requested_by,
            requested_by_name=f"{requester.name} {requester.surname}".strip() if requester else None,
            editor_notes=approval.editor_notes,
            reviewed_by_id=approval.reviewed_by,
            reviewed_by_name=f"{reviewer.name} {reviewer.surname}".strip() if reviewer else None,
            review_notes=approval.review_notes,
            requested_at=approval.requested_at.isoformat() if approval.requested_at else None,
            reviewed_at=approval.reviewed_at.isoformat() if approval.reviewed_at else None,
            expires_at=approval.expires_at.isoformat() if approval.expires_at else None,
            thread_id=approval.thread_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting approval {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting approval: {str(e)}"
        )


@router.post("/{article_id}", response_model=ProcessApprovalResponse)
async def process_approval(
    article_id: int,
    request: ProcessApprovalRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Process an approval decision for an article.

    Approve (approved=True) to publish the article.
    Reject (approved=False) to return it to editor status.

    User must have editor+ permission for the article's topic.
    """
    try:
        from models import ContentArticle, ArticleStatus, ApprovalRequest, ApprovalStatus

        # Get article
        article = db.query(ContentArticle).filter(ContentArticle.id == article_id).first()

        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article {article_id} not found"
            )

        # Check permission
        user_scopes = user.get("scopes", [])
        topic = article.topic_slug

        if not PermissionService.check_permission(user_scopes, "editor", topic=topic):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Editor permission required for topic '{topic}'"
            )

        # Check article status
        if article.status != ArticleStatus.PENDING_APPROVAL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Article is not pending approval. Current status: '{article.status.value}'"
            )

        # Find pending approval request
        approval_request = db.query(ApprovalRequest).filter(
            ApprovalRequest.article_id == article_id,
            ApprovalRequest.status == ApprovalStatus.PENDING,
        ).first()

        if not approval_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No pending approval request found for this article"
            )

        # Process the approval
        user_id = user.get("sub")
        approval_request.reviewed_by = user_id
        approval_request.reviewed_at = datetime.utcnow()
        approval_request.review_notes = request.review_notes
        approval_request.status = ApprovalStatus.APPROVED if request.approved else ApprovalStatus.REJECTED

        # Update article status
        if request.approved:
            article.status = ArticleStatus.PUBLISHED
            user_name = f"{user.get('name', '')} {user.get('surname', '')}".strip()
            article.editor = user_name or article.editor
            new_status = "published"
            message = "Article has been approved and published."
        else:
            article.status = ArticleStatus.EDITOR
            new_status = "editor"
            message = "Article has been rejected and returned to editor status."

        db.commit()

        # Send WebSocket notification
        try:
            import redis
            import json
            import os

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            r = redis.from_url(redis_url)

            notification = {
                "type": "approval_processed",
                "article_id": article_id,
                "approved": request.approved,
                "new_status": new_status,
                "reviewed_by": user_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Publish to article submitter
            if approval_request.requested_by:
                r.publish(f"user:{approval_request.requested_by}:notifications", json.dumps(notification))

            logger.info(f"Approval processed for article {article_id}: {'approved' if request.approved else 'rejected'}")

        except Exception as e:
            logger.warning(f"Failed to send WebSocket notification: {e}")

        return ProcessApprovalResponse(
            approval_id=approval_request.id,
            article_id=article_id,
            approved=request.approved,
            new_article_status=new_status,
            message=message
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing approval for article {article_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing approval: {str(e)}"
        )


@router.delete("/{approval_id}")
async def cancel_approval_request(
    approval_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Cancel a pending approval request.

    Returns the article to EDITOR status without processing.
    User must be the requester or have editor+ permission.
    """
    try:
        from models import ApprovalRequest, ApprovalStatus, ArticleStatus

        approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()

        if not approval:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Approval request {approval_id} not found"
            )

        if approval.status != ApprovalStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel approval in status '{approval.status.value}'"
            )

        # Check permission - must be requester or editor
        user_id = user.get("sub")
        user_scopes = user.get("scopes", [])
        topic = approval.article.topic_slug if approval.article else None

        is_requester = str(approval.requested_by) == str(user_id)
        has_editor_permission = PermissionService.check_permission(user_scopes, "editor", topic=topic)

        if not is_requester and not has_editor_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the requester or an editor can cancel this approval"
            )

        # Cancel the approval
        approval.status = ApprovalStatus.EXPIRED  # Using EXPIRED for cancelled
        approval.review_notes = "Cancelled by user"
        approval.reviewed_by = user_id
        approval.reviewed_at = datetime.utcnow()

        # Return article to EDITOR status
        if approval.article:
            approval.article.status = ArticleStatus.EDITOR

        db.commit()

        logger.info(f"Approval {approval_id} cancelled by user {user_id}")

        return {
            "message": "Approval request cancelled",
            "approval_id": approval_id,
            "article_id": approval.article_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error cancelling approval {approval_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cancelling approval: {str(e)}"
        )


# ==========================================================================
# LANGGRAPH WORKFLOW RESUME ENDPOINTS
# ==========================================================================


class WorkflowResumeRequest(BaseModel):
    """Request to resume a paused LangGraph workflow."""
    decision: str  # "approve" or "reject"
    notes: Optional[str] = None


class WorkflowResumeResponse(BaseModel):
    """Response from resuming a workflow."""
    thread_id: str
    decision: str
    response: str
    agent_type: Optional[str] = None
    article_id: Optional[int] = None
    new_status: Optional[str] = None


@router.post("/workflow/{thread_id}/resume", response_model=WorkflowResumeResponse)
async def resume_workflow(
    thread_id: str,
    request: WorkflowResumeRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    Resume a paused LangGraph workflow after HITL decision.

    This endpoint is called after a user confirms or cancels an action
    that requires human-in-the-loop approval (e.g., publishing an article).

    The workflow was checkpointed when it reached an HITL interrupt point,
    and this endpoint resumes it with the user's decision.

    Args:
        thread_id: The workflow thread ID (from the confirmation response)
        request: The user's decision (approve/reject) and optional notes

    Returns:
        The result of the resumed workflow
    """
    try:
        from agents.graph import resume_chat
        from agents.state import create_user_context

        user_id = user.get("sub")
        user_scopes = user.get("scopes", [])

        logger.info(f"Resuming workflow {thread_id} with decision: {request.decision}")

        # Validate decision
        if request.decision not in ["approve", "reject"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Decision must be 'approve' or 'reject'"
            )

        # Build user context
        user_ctx = create_user_context(
            user_id=int(user_id) if user_id else 0,
            email=user.get("email", ""),
            name=user.get("name", ""),
            scopes=user_scopes,
            surname=user.get("surname"),
        )

        # Resume workflow using singleton graph
        response = resume_chat(
            thread_id=thread_id,
            hitl_decision=request.decision,
            user_context=user_ctx,
        )

        # Convert ChatResponse to dict
        result = response.model_dump()

        logger.info(f"Workflow {thread_id} resumed: {result.get('agent_type')}")

        return WorkflowResumeResponse(
            thread_id=thread_id,
            decision=request.decision,
            response=result.get("response", "Workflow completed"),
            agent_type=result.get("agent_type"),
            article_id=result.get("article_id"),
            new_status=result.get("new_status"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming workflow {thread_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error resuming workflow: {str(e)}"
        )


@router.get("/workflow/{thread_id}/status")
async def get_workflow_status(
    thread_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Get the status of a LangGraph workflow.

    Returns whether the workflow is pending HITL approval, completed, or not found.
    """
    try:
        from langgraph.checkpoint.memory import MemorySaver
        import os

        # Try to get checkpointer status
        redis_url = os.getenv("REDIS_URL")

        if redis_url:
            try:
                from langgraph.checkpoint.redis import RedisSaver
                checkpointer = RedisSaver.from_conn_string(redis_url)
                checkpointer.setup()
            except Exception:
                checkpointer = MemorySaver()
        else:
            checkpointer = MemorySaver()

        # Check if thread exists in checkpointer
        # Note: This is a simplified check - actual implementation depends on checkpointer API
        config = {"configurable": {"thread_id": thread_id}}

        return {
            "thread_id": thread_id,
            "status": "unknown",  # Would need to check checkpointer state
            "message": "Workflow status check - checkpointer integration pending"
        }

    except Exception as e:
        logger.warning(f"Could not check workflow status: {e}")
        return {
            "thread_id": thread_id,
            "status": "unknown",
            "error": str(e)
        }
