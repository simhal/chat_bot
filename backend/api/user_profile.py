"""User profile endpoints for custom prompt management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models import User

router = APIRouter(prefix="/api/profile", tags=["profile"])


# Pydantic models
class CustomPromptRequest(BaseModel):
    """Request model for updating custom prompt."""
    custom_prompt: Optional[str] = None


class CustomPromptResponse(BaseModel):
    """Response model for custom prompt."""
    custom_prompt: Optional[str]


# Helper function to get current user
def get_current_user_func(user: dict = Depends(lambda: {})) -> dict:
    """
    Get current authenticated user.
    Note: This should be connected to the actual auth system in main.py
    """
    # TODO: Replace with actual get_current_user from main.py
    # For now, this is a placeholder
    # In production, import and use the actual get_current_user from main.py
    return user


@router.get("/custom-prompt", response_model=CustomPromptResponse)
async def get_custom_prompt(
    user: dict = Depends(get_current_user_func),
    db: Session = Depends(get_db)
):
    """
    Get user's custom prompt.
    Returns the current user's custom prompt or None if not set.
    """
    user_id = int(user.get("sub", 0))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    user_obj = db.query(User).filter(User.id == user_id).first()

    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return CustomPromptResponse(custom_prompt=user_obj.custom_prompt)


@router.put("/custom-prompt", response_model=CustomPromptResponse)
async def update_custom_prompt(
    request: CustomPromptRequest,
    user: dict = Depends(get_current_user_func),
    db: Session = Depends(get_db)
):
    """
    Update user's custom prompt.
    The custom prompt will be appended to all agent system prompts.
    """
    user_id = int(user.get("sub", 0))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    user_obj = db.query(User).filter(User.id == user_id).first()

    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Validate custom prompt length
    if request.custom_prompt and len(request.custom_prompt) > 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Custom prompt too long (maximum 2000 characters)"
        )

    user_obj.custom_prompt = request.custom_prompt
    db.commit()
    db.refresh(user_obj)

    return CustomPromptResponse(custom_prompt=user_obj.custom_prompt)


@router.delete("/custom-prompt")
async def delete_custom_prompt(
    user: dict = Depends(get_current_user_func),
    db: Session = Depends(get_db)
):
    """Clear user's custom prompt."""
    user_id = int(user.get("sub", 0))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    user_obj = db.query(User).filter(User.id == user_id).first()

    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user_obj.custom_prompt = None
    db.commit()

    return {"message": "Custom prompt cleared successfully"}
