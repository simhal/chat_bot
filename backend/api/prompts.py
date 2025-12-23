"""API endpoints for prompt module management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from database import get_db
from models import PromptModule, PromptType, User
from services.prompt_service import PromptService, PromptValidator
from dependencies import get_current_user, require_admin, is_global_admin, has_role

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


# Pydantic models
class PromptModuleResponse(BaseModel):
    """Response model for prompt module."""
    id: int
    name: str
    prompt_type: str
    prompt_group: Optional[str]
    template_text: str
    description: Optional[str]
    is_default: bool
    sort_order: int
    is_active: bool
    version: int
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class PromptModuleUpdate(BaseModel):
    """Request model for updating a prompt module."""
    template_text: str
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class TonalityCreate(BaseModel):
    """Request model for creating a new tonality prompt."""
    name: str
    template_text: str
    description: Optional[str] = None
    prompt_group: Optional[str] = None
    sort_order: int = 99


class ContentAgentCreate(BaseModel):
    """Request model for creating a new content agent prompt."""
    name: str
    template_text: str
    prompt_group: str  # Required - the topic this agent belongs to
    description: Optional[str] = None
    sort_order: int = 99


class TonalityPreferences(BaseModel):
    """User tonality preferences."""
    chat_tonality_id: Optional[int] = None
    content_tonality_id: Optional[int] = None


class TonalityPreferencesResponse(BaseModel):
    """Response for user tonality preferences."""
    chat_tonality: Optional[dict] = None
    content_tonality: Optional[dict] = None


class TonalityOptionResponse(BaseModel):
    """Simplified response for tonality selection options."""
    id: int
    name: str
    description: Optional[str]
    prompt_group: Optional[str]
    is_default: bool

    class Config:
        from_attributes = True


# Mandatory prompt types that cannot be deleted
MANDATORY_PROMPT_TYPES = [
    PromptType.GENERAL.value,
    PromptType.CHAT_SPECIFIC.value,
    PromptType.CHAT_CONSTRAINT.value,
    PromptType.ARTICLE_CONSTRAINT.value
]


@router.get("", response_model=List[PromptModuleResponse])
async def list_prompt_modules(
    prompt_type: Optional[str] = None,
    prompt_group: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all prompt modules.
    Filter by prompt_type and prompt_group.

    Permission: global:admin or {topic}:admin (for their topic's content_topic prompts)
    """
    scopes = current_user.get("scopes", [])

    # Get modules
    modules = PromptService.get_prompt_modules(db, prompt_type, prompt_group)

    if active_only:
        modules = [m for m in modules if m['is_active']]

    # Filter based on permissions if not global admin
    if not is_global_admin(scopes):
        # Non-admin users can only see tonalities and content_topic for their topics
        filtered = []
        for m in modules:
            if m['prompt_type'] == 'tonality':
                filtered.append(m)
            elif m['prompt_type'] == 'content_topic' and m.get('prompt_group'):
                if has_role(scopes, m['prompt_group'], 'admin'):
                    filtered.append(m)
        modules = filtered

    return modules


@router.get("/tonalities", response_model=List[TonalityOptionResponse])
async def list_tonalities(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all available tonality options for user selection.
    This endpoint is accessible to all authenticated users.
    """
    tonalities = PromptService.get_available_tonalities(db)
    return tonalities


@router.get("/{module_id}", response_model=PromptModuleResponse)
async def get_prompt_module(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get specific prompt module by ID."""
    module = db.query(PromptModule).filter(PromptModule.id == module_id).first()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt module not found"
        )

    return PromptModuleResponse(
        id=module.id,
        name=module.name,
        prompt_type=module.prompt_type.value if hasattr(module.prompt_type, 'value') else module.prompt_type,
        prompt_group=module.prompt_group,
        template_text=module.template_text,
        description=module.description,
        is_default=module.is_default,
        sort_order=module.sort_order,
        is_active=module.is_active,
        version=module.version,
        created_at=module.created_at.isoformat() if module.created_at else None,
        updated_at=module.updated_at.isoformat() if module.updated_at else None
    )


@router.put("/{module_id}", response_model=PromptModuleResponse)
async def update_prompt_module(
    module_id: int,
    updates: PromptModuleUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update a prompt module.

    Permission requirements:
    - global:admin can update all prompts
    - {topic}:admin can update content_topic prompts for their topic only
    """
    module = db.query(PromptModule).filter(PromptModule.id == module_id).first()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt module not found"
        )

    scopes = current_user.get("scopes", [])
    prompt_type = module.prompt_type.value if hasattr(module.prompt_type, 'value') else module.prompt_type

    # Permission check
    if not is_global_admin(scopes):
        # Non-global-admin can only edit content_topic for their topic
        if prompt_type == 'content_topic' and module.prompt_group:
            if not has_role(scopes, module.prompt_group, 'admin'):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"You need '{module.prompt_group}:admin' role to edit this prompt"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only global:admin can edit this prompt type"
            )

    # Validate template
    is_valid, error_msg = PromptValidator.validate_template(
        prompt_type,
        updates.template_text,
        module.prompt_group
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # Get user_id from current_user
    user_id = current_user.get('sub') if current_user else None

    result = PromptService.update_prompt_module(
        db,
        module_id,
        updates.template_text,
        updates.name,
        updates.description,
        updates.is_active,
        user_id
    )

    return result


@router.post("/tonality", response_model=PromptModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_tonality(
    tonality: TonalityCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Create a new tonality prompt.
    Only global:admin can create new tonalities.
    """
    # Validate
    is_valid, error_msg = PromptValidator.validate_template(
        PromptType.TONALITY,
        tonality.template_text,
        tonality.prompt_group
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # Check for duplicate name
    existing = db.query(PromptModule).filter(
        PromptModule.prompt_type == PromptType.TONALITY,
        PromptModule.name == tonality.name,
        PromptModule.is_active == True
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tonality with name '{tonality.name}' already exists"
        )

    user_id = int(current_user.get('sub')) if current_user and current_user.get('sub') else None

    new_module = PromptModule(
        name=tonality.name,
        prompt_type=PromptType.TONALITY,
        prompt_group=tonality.prompt_group,
        template_text=tonality.template_text,
        description=tonality.description,
        is_default=False,
        sort_order=tonality.sort_order,
        is_active=True,
        version=1,
        created_by=user_id
    )

    db.add(new_module)
    db.commit()
    db.refresh(new_module)

    # Invalidate cache
    PromptService.invalidate_cache()

    return PromptModuleResponse(
        id=new_module.id,
        name=new_module.name,
        prompt_type=new_module.prompt_type.value if hasattr(new_module.prompt_type, 'value') else new_module.prompt_type,
        prompt_group=new_module.prompt_group,
        template_text=new_module.template_text,
        description=new_module.description,
        is_default=new_module.is_default,
        sort_order=new_module.sort_order,
        is_active=new_module.is_active,
        version=new_module.version,
        created_at=new_module.created_at.isoformat() if new_module.created_at else None,
        updated_at=new_module.updated_at.isoformat() if new_module.updated_at else None
    )


@router.post("/content-agent", response_model=PromptModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_content_agent(
    agent: ContentAgentCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Create a new content agent prompt for a topic.
    Only global:admin can create new content agents.
    """
    # Validate
    is_valid, error_msg = PromptValidator.validate_template(
        PromptType.CONTENT_TOPIC,
        agent.template_text,
        agent.prompt_group
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # Check for duplicate - only one content_topic per prompt_group
    existing = db.query(PromptModule).filter(
        PromptModule.prompt_type == PromptType.CONTENT_TOPIC,
        PromptModule.prompt_group == agent.prompt_group,
        PromptModule.is_active == True
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Content agent for topic '{agent.prompt_group}' already exists"
        )

    user_id = int(current_user.get('sub')) if current_user and current_user.get('sub') else None

    new_module = PromptModule(
        name=agent.name,
        prompt_type=PromptType.CONTENT_TOPIC,
        prompt_group=agent.prompt_group,
        template_text=agent.template_text,
        description=agent.description,
        is_default=False,
        sort_order=agent.sort_order,
        is_active=True,
        version=1,
        created_by=user_id
    )

    db.add(new_module)
    db.commit()
    db.refresh(new_module)

    # Invalidate cache
    PromptService.invalidate_cache()

    return PromptModuleResponse(
        id=new_module.id,
        name=new_module.name,
        prompt_type=new_module.prompt_type.value if hasattr(new_module.prompt_type, 'value') else new_module.prompt_type,
        prompt_group=new_module.prompt_group,
        template_text=new_module.template_text,
        description=new_module.description,
        is_default=new_module.is_default,
        sort_order=new_module.sort_order,
        is_active=new_module.is_active,
        version=new_module.version,
        created_at=new_module.created_at.isoformat() if new_module.created_at else None,
        updated_at=new_module.updated_at.isoformat() if new_module.updated_at else None
    )


@router.delete("/{module_id}")
async def delete_prompt_module(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Delete (deactivate) a prompt module.

    Only tonality prompts can be deleted.
    Mandatory prompts (general, chat_specific, chat_constraint, article_constraint) cannot be deleted.
    Only global:admin can delete prompts.
    """
    module = db.query(PromptModule).filter(PromptModule.id == module_id).first()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt module not found"
        )

    prompt_type = module.prompt_type.value if hasattr(module.prompt_type, 'value') else module.prompt_type

    # Check if this is a mandatory prompt type
    if prompt_type in MANDATORY_PROMPT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot delete mandatory prompt type: {prompt_type}"
        )

    # Check if this is a content_topic prompt (only one per topic)
    if prompt_type == PromptType.CONTENT_TOPIC.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete content topic prompts. Each topic must have exactly one prompt."
        )

    # Only tonality prompts can be deleted
    if prompt_type != PromptType.TONALITY.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tonality prompts can be deleted"
        )

    # Check if this is the default tonality
    if module.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete the default tonality. Set another tonality as default first."
        )

    # Soft delete
    module.is_active = False
    db.commit()

    # Invalidate cache
    PromptService.invalidate_cache()

    return {"message": "Tonality deleted successfully", "id": module_id}


@router.post("/tonality/{module_id}/set-default")
async def set_default_tonality(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Set a tonality as the default.
    Only global:admin can do this.
    """
    module = db.query(PromptModule).filter(PromptModule.id == module_id).first()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt module not found"
        )

    prompt_type = module.prompt_type.value if hasattr(module.prompt_type, 'value') else module.prompt_type

    if prompt_type != PromptType.TONALITY.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only tonality prompts can be set as default"
        )

    # Remove default from all other tonalities
    db.query(PromptModule).filter(
        PromptModule.prompt_type == PromptType.TONALITY,
        PromptModule.is_default == True
    ).update({"is_default": False})

    # Set this one as default
    module.is_default = True
    db.commit()

    # Invalidate cache
    PromptService.invalidate_cache()

    return {"message": "Default tonality updated", "id": module_id}


# User tonality preference endpoints
@router.get("/user/tonality", response_model=TonalityPreferencesResponse)
async def get_user_tonality(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get current user's tonality preferences."""
    user_id = current_user.get('sub')
    preferences = PromptService.get_user_tonality_preferences(db, int(user_id))
    return preferences


@router.put("/user/tonality", response_model=TonalityPreferencesResponse)
async def update_user_tonality(
    preferences: TonalityPreferences,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update current user's tonality preferences."""
    user_id = current_user.get('sub')

    try:
        PromptService.set_user_tonality(
            db,
            int(user_id),
            preferences.chat_tonality_id,
            preferences.content_tonality_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Return updated preferences
    return PromptService.get_user_tonality_preferences(db, int(user_id))


# Admin endpoint to set any user's tonality
@router.put("/admin/user/{user_id}/tonality", response_model=TonalityPreferencesResponse)
async def admin_update_user_tonality(
    user_id: int,
    preferences: TonalityPreferences,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Admin endpoint to update any user's tonality preferences.
    Only global:admin can use this endpoint.
    """
    # Verify user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    try:
        PromptService.set_user_tonality(
            db,
            user_id,
            preferences.chat_tonality_id,
            preferences.content_tonality_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Return updated preferences
    return PromptService.get_user_tonality_preferences(db, user_id)


@router.get("/admin/user/{user_id}/tonality", response_model=TonalityPreferencesResponse)
async def admin_get_user_tonality(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    Admin endpoint to get any user's tonality preferences.
    Only global:admin can use this endpoint.
    """
    # Verify user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return PromptService.get_user_tonality_preferences(db, user_id)
