"""Admin endpoints for prompt template management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from database import get_db
from models import PromptTemplate, User
from services.prompt_service import PromptService, PromptValidator

router = APIRouter(prefix="/api/admin/prompts", tags=["admin-prompts"])


# Pydantic models for request/response
class PromptTemplateCreate(BaseModel):
    """Request model for creating a prompt template."""
    agent_type: str  # router, equity, economist, fixed_income
    template_name: str = "default"
    template_text: str
    description: Optional[str] = None


class PromptTemplateUpdate(BaseModel):
    """Request model for updating a prompt template."""
    template_text: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PromptTemplateResponse(BaseModel):
    """Response model for prompt template."""
    id: int
    agent_type: str
    template_name: str
    template_text: str
    version: int
    is_active: bool
    created_at: str
    created_by: Optional[int]
    description: Optional[str]

    class Config:
        from_attributes = True


# Helper function to check admin access
def require_admin(user: dict = Depends(lambda: {})) -> dict:
    """
    Require admin scope for access.
    Note: This should be connected to the actual auth system in main.py
    """
    # TODO: Replace with actual admin check from main.py auth system
    # For now, this is a placeholder
    # In production, import and use the actual require_admin from main.py
    return user


@router.post("/", response_model=PromptTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template: PromptTemplateCreate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Create new prompt template. Requires admin scope.

    - Validates agent_type and template content
    - Deactivates existing active templates with same agent_type + name
    - Creates new versioned template
    - Invalidates prompt cache
    """
    # Validate agent_type
    valid_types = ["router", "equity", "economist", "fixed_income"]
    if template.agent_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid agent_type. Must be one of: {valid_types}"
        )

    # Validate template content
    is_valid, error_msg = PromptValidator.validate_template(
        template.agent_type,
        template.template_text
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # Deactivate existing active templates with same agent_type + name
    db.query(PromptTemplate).filter(
        PromptTemplate.agent_type == template.agent_type,
        PromptTemplate.template_name == template.template_name,
        PromptTemplate.is_active == True
    ).update({"is_active": False})

    # Get next version number
    max_version = db.query(func.max(PromptTemplate.version)).filter(
        PromptTemplate.agent_type == template.agent_type,
        PromptTemplate.template_name == template.template_name
    ).scalar() or 0

    # Create new template
    new_template = PromptTemplate(
        agent_type=template.agent_type,
        template_name=template.template_name,
        template_text=template.template_text,
        description=template.description,
        version=max_version + 1,
        created_by=admin.get("sub") if admin.get("sub") else None
    )

    db.add(new_template)
    db.commit()
    db.refresh(new_template)

    # Invalidate cache
    PromptService.invalidate_cache(template.agent_type, template.template_name)

    return PromptTemplateResponse(
        id=new_template.id,
        agent_type=new_template.agent_type,
        template_name=new_template.template_name,
        template_text=new_template.template_text,
        version=new_template.version,
        is_active=new_template.is_active,
        created_at=new_template.created_at.isoformat(),
        created_by=new_template.created_by,
        description=new_template.description
    )


@router.get("/", response_model=List[PromptTemplateResponse])
async def list_templates(
    agent_type: Optional[str] = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    List all prompt templates.
    Filter by agent_type and active status.
    """
    query = db.query(PromptTemplate)

    if agent_type:
        query = query.filter(PromptTemplate.agent_type == agent_type)
    if active_only:
        query = query.filter(PromptTemplate.is_active == True)

    templates = query.order_by(
        PromptTemplate.agent_type,
        PromptTemplate.template_name,
        PromptTemplate.version.desc()
    ).all()

    return [
        PromptTemplateResponse(
            id=t.id,
            agent_type=t.agent_type,
            template_name=t.template_name,
            template_text=t.template_text,
            version=t.version,
            is_active=t.is_active,
            created_at=t.created_at.isoformat(),
            created_by=t.created_by,
            description=t.description
        )
        for t in templates
    ]


@router.get("/{template_id}", response_model=PromptTemplateResponse)
async def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Get specific prompt template by ID."""
    template = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    return PromptTemplateResponse(
        id=template.id,
        agent_type=template.agent_type,
        template_name=template.template_name,
        template_text=template.template_text,
        version=template.version,
        is_active=template.is_active,
        created_at=template.created_at.isoformat(),
        created_by=template.created_by,
        description=template.description
    )


@router.patch("/{template_id}", response_model=PromptTemplateResponse)
async def update_template(
    template_id: int,
    updates: PromptTemplateUpdate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Update prompt template.
    Creates new version if template_text changes.
    """
    template = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    # If template_text changes, create new version
    if updates.template_text and updates.template_text != template.template_text:
        # Validate new template content
        is_valid, error_msg = PromptValidator.validate_template(
            template.agent_type,
            updates.template_text
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )

        # Deactivate old version
        template.is_active = False
        db.commit()

        # Create new version
        new_template = PromptTemplate(
            agent_type=template.agent_type,
            template_name=template.template_name,
            template_text=updates.template_text,
            description=updates.description or template.description,
            version=template.version + 1,
            created_by=admin.get("sub") if admin.get("sub") else None
        )
        db.add(new_template)
        db.commit()
        db.refresh(new_template)

        # Invalidate cache
        PromptService.invalidate_cache(new_template.agent_type, new_template.template_name)

        return PromptTemplateResponse(
            id=new_template.id,
            agent_type=new_template.agent_type,
            template_name=new_template.template_name,
            template_text=new_template.template_text,
            version=new_template.version,
            is_active=new_template.is_active,
            created_at=new_template.created_at.isoformat(),
            created_by=new_template.created_by,
            description=new_template.description
        )

    # Otherwise just update metadata
    if updates.description is not None:
        template.description = updates.description
    if updates.is_active is not None:
        template.is_active = updates.is_active

    db.commit()
    db.refresh(template)

    # Invalidate cache if activation status changed
    if updates.is_active is not None:
        PromptService.invalidate_cache(template.agent_type, template.template_name)

    return PromptTemplateResponse(
        id=template.id,
        agent_type=template.agent_type,
        template_name=template.template_name,
        template_text=template.template_text,
        version=template.version,
        is_active=template.is_active,
        created_at=template.created_at.isoformat(),
        created_by=template.created_by,
        description=template.description
    )


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Soft delete: deactivate template."""
    template = db.query(PromptTemplate).filter(PromptTemplate.id == template_id).first()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    template.is_active = False
    db.commit()

    # Invalidate cache
    PromptService.invalidate_cache(template.agent_type, template.template_name)

    return {"message": "Template deactivated successfully", "template_id": template_id}
