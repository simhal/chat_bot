"""User profile endpoints for custom prompt management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models import User
from dependencies import get_current_user

router = APIRouter(prefix="/api/profile", tags=["profile"])


# Pydantic models
class CustomPromptRequest(BaseModel):
    """Request model for updating custom prompt."""
    custom_prompt: Optional[str] = None


class CustomPromptResponse(BaseModel):
    """Response model for custom prompt."""
    custom_prompt: Optional[str]


class UserProfileResponse(BaseModel):
    """Response model for user profile."""
    id: int
    email: str
    name: Optional[str]
    surname: Optional[str]
    picture: Optional[str]
    created_at: str
    custom_prompt: Optional[str]
    groups: list[str]


@router.get("/me", response_model=UserProfileResponse)
async def get_user_profile(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's profile information."""
    user_id = int(user.get("sub"))

    user_obj = db.query(User).filter(User.id == user_id).first()

    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Get user's groups
    groups = [group.name for group in user_obj.groups]

    return UserProfileResponse(
        id=user_obj.id,
        email=user_obj.email,
        name=user_obj.name,
        surname=user_obj.surname,
        picture=user_obj.picture,
        created_at=user_obj.created_at.isoformat(),
        custom_prompt=user_obj.custom_prompt,
        groups=groups
    )


@router.get("/custom-prompt", response_model=CustomPromptResponse)
async def get_custom_prompt(
    user: dict = Depends(get_current_user),
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
    user: dict = Depends(get_current_user),
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
    user: dict = Depends(get_current_user),
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


@router.delete("/me")
async def delete_user_account(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete current user's account.
    This will permanently delete the user and all associated data including:
    - User profile
    - Group memberships
    - Custom prompts
    - Agent interactions
    - Content ratings

    This action cannot be undone.
    """
    user_id = int(user.get("sub"))

    user_obj = db.query(User).filter(User.id == user_id).first()

    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Delete the user (cascade will handle related data like group memberships, ratings, etc.)
    db.delete(user_obj)
    db.commit()

    return {
        "message": "Account deleted successfully",
        "email": user_obj.email
    }
