"""API endpoints for Celery task management."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from dependencies import get_current_user, require_admin
import logging

logger = logging.getLogger("uvicorn")


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# Pydantic models for API
class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    task_type: Optional[str] = None
    progress: Optional[dict] = None


class TaskListResponse(BaseModel):
    tasks: List[TaskStatusResponse]
    total_count: int


class CancelTaskResponse(BaseModel):
    task_id: str
    cancelled: bool
    message: str


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Get the status of a Celery task.

    Returns the current status, result (if complete), or error (if failed).
    Users can only view their own tasks unless they are global admin.
    """
    try:
        from celery.result import AsyncResult
        from celery_app import celery_app

        result = AsyncResult(task_id, app=celery_app)

        # Get task metadata if available
        task_info = result.info or {}

        # Check if user owns this task (stored in task metadata)
        user_id = user.get("sub")
        task_user_id = task_info.get("user_id") if isinstance(task_info, dict) else None

        # Only allow viewing own tasks unless admin
        scopes = user.get("scopes", [])
        if "global:admin" not in scopes and task_user_id and str(task_user_id) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own tasks"
            )

        response = TaskStatusResponse(
            task_id=task_id,
            status=result.status,
            task_type=task_info.get("task_type") if isinstance(task_info, dict) else None,
        )

        if result.successful():
            response.result = result.result
            response.completed_at = datetime.utcnow().isoformat()
        elif result.failed():
            response.error = str(result.result) if result.result else "Unknown error"
        elif result.status == "PROGRESS":
            response.progress = task_info if isinstance(task_info, dict) else None

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status for {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting task status: {str(e)}"
        )


@router.get("", response_model=TaskListResponse)
async def list_user_tasks(
    status_filter: Optional[str] = None,
    limit: int = 50,
    user: dict = Depends(get_current_user)
):
    """
    List recent tasks for the current user.

    Admin users can see all tasks. Regular users see only their own.
    """
    try:
        from celery_app import celery_app
        from database import SessionLocal
        from models import User

        user_id = user.get("sub")
        scopes = user.get("scopes", [])
        is_admin = "global:admin" in scopes

        # Get task info from Redis (Celery result backend)
        # Note: This is a simplified implementation. Production would use
        # a dedicated task tracking table in the database.

        tasks = []

        # For now, return empty list - in production you would track tasks in DB
        # and query them here. Celery's result backend doesn't support listing.

        return TaskListResponse(
            tasks=tasks,
            total_count=len(tasks)
        )

    except Exception as e:
        logger.error(f"Error listing tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing tasks: {str(e)}"
        )


@router.post("/{task_id}/cancel", response_model=CancelTaskResponse)
async def cancel_task(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Cancel a pending or running task.

    Users can only cancel their own tasks unless they are global admin.
    """
    try:
        from celery.result import AsyncResult
        from celery_app import celery_app

        result = AsyncResult(task_id, app=celery_app)

        # Check ownership
        task_info = result.info or {}
        user_id = user.get("sub")
        task_user_id = task_info.get("user_id") if isinstance(task_info, dict) else None

        scopes = user.get("scopes", [])
        if "global:admin" not in scopes and task_user_id and str(task_user_id) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only cancel your own tasks"
            )

        # Revoke the task
        if result.status in ["PENDING", "STARTED", "RETRY"]:
            result.revoke(terminate=True)
            logger.info(f"Task {task_id} cancelled by user {user_id}")
            return CancelTaskResponse(
                task_id=task_id,
                cancelled=True,
                message="Task has been cancelled"
            )
        else:
            return CancelTaskResponse(
                task_id=task_id,
                cancelled=False,
                message=f"Task cannot be cancelled - current status: {result.status}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling task {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cancelling task: {str(e)}"
        )


@router.post("/{task_id}/retry", response_model=TaskStatusResponse)
async def retry_task(
    task_id: str,
    admin: dict = Depends(require_admin)
):
    """
    Retry a failed task. Admin only.
    """
    try:
        from celery.result import AsyncResult
        from celery_app import celery_app

        result = AsyncResult(task_id, app=celery_app)

        if result.status != "FAILURE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Can only retry failed tasks. Current status: {result.status}"
            )

        # Note: Celery doesn't support direct retry of arbitrary tasks.
        # In production, you would store task arguments and re-dispatch.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Task retry requires task arguments to be stored separately"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying task {task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrying task: {str(e)}"
        )
