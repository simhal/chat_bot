"""API endpoints for resource management."""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Any
from pydantic import BaseModel
from database import get_db
from models import Resource, ResourceType, ResourceStatus, TimeseriesFrequency, TimeseriesDataType, Group, ContentArticle, article_resources
from services.resource_service import ResourceService
from services.article_resource_service import ArticleResourceService
from services.table_resource_service import TableResourceService
from services.storage_service import get_storage, StorageService
from dependencies import get_current_user, require_admin, is_global_admin, has_role, get_valid_topics
import json
import os
import uuid
from datetime import datetime
import hashlib
import io

router = APIRouter(prefix="/api/resources", tags=["resources"])

# File storage configuration
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Get storage service instance
storage = get_storage()

# Ensure upload directory exists (for local storage)
if storage.is_local:
    os.makedirs(UPLOAD_DIR, exist_ok=True)


# =============================================================================
# Pydantic Models
# =============================================================================

class ResourceResponse(BaseModel):
    """Response model for a resource."""
    id: int
    hash_id: str
    resource_type: str
    status: str = "draft"
    name: str
    description: Optional[str]
    group_id: Optional[int]
    parent_id: Optional[int] = None
    created_by: Optional[int]
    modified_by: Optional[int]
    created_at: Optional[str]
    updated_at: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


class ChildResourceInfo(BaseModel):
    """Brief info about a child resource."""
    id: int
    hash_id: str
    resource_type: str
    name: str


class ResourceDetailResponse(BaseModel):
    """Detailed response model for a resource with type-specific data."""
    id: int
    hash_id: str
    resource_type: str
    status: str = "draft"
    name: str
    description: Optional[str]
    group_id: Optional[int]
    parent_id: Optional[int] = None
    children: Optional[List[ChildResourceInfo]] = None
    created_by: Optional[int]
    modified_by: Optional[int]
    created_at: Optional[str]
    updated_at: Optional[str]
    is_active: bool
    file_data: Optional[dict] = None
    text_data: Optional[dict] = None
    table_data: Optional[dict] = None
    timeseries_data: Optional[dict] = None


class ResourceListResponse(BaseModel):
    """Response model for paginated resource list."""
    resources: List[ResourceResponse]
    total: int
    offset: int
    limit: int


class CreateTextResourceRequest(BaseModel):
    """Request to create a text resource."""
    name: str
    content: str
    description: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None  # Alternative: topic name like "macro" or "global"
    encoding: str = "utf-8"
    parent_id: Optional[int] = None  # For derived resources (e.g., text from PDF)


class CreateTableResourceRequest(BaseModel):
    """Request to create a table resource."""
    name: str
    table_data: dict  # {"columns": [...], "data": [[...], ...]}
    description: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None  # Alternative: topic name like "macro" or "global"
    column_types: Optional[dict] = None
    parent_id: Optional[int] = None  # For derived resources (e.g., table from PDF/Excel)


class CreateTimeseriesRequest(BaseModel):
    """Request to create a timeseries resource."""
    name: str
    columns: List[str]
    frequency: str  # tick, minute, hourly, daily, weekly, monthly, quarterly, yearly
    description: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None  # Alternative: topic name like "macro" or "global"
    source: Optional[str] = None
    data_type: str = "float"  # float, integer, string
    unit: Optional[str] = None
    parent_id: Optional[int] = None  # For derived resources


class AddTimeseriesDataRequest(BaseModel):
    """Request to add data points to a timeseries."""
    data_points: List[dict]  # [{"date": "...", "column_name": "...", "value": ...}, ...]


class UpdateResourceRequest(BaseModel):
    """Request to update resource metadata."""
    name: Optional[str] = None
    description: Optional[str] = None
    group_id: Optional[int] = None


class UpdateResourceStatusRequest(BaseModel):
    """Request to update resource status (editorial workflow)."""
    status: str  # draft, editor, published


class UpdateTextContentRequest(BaseModel):
    """Request to update text resource content."""
    content: str
    encoding: str = "utf-8"


class UpdateTableContentRequest(BaseModel):
    """Request to update table resource content."""
    table_data: dict  # {"columns": [...], "data": [[...], ...]}
    column_types: Optional[dict] = None


class UpdateTimeseriesDataRequest(BaseModel):
    """Request to update timeseries data."""
    data: List[dict]  # List of {"timestamp": ..., "values": {...}}


class LinkArticleRequest(BaseModel):
    """Request to link a resource to an article."""
    article_id: int


# =============================================================================
# Helper Functions
# =============================================================================

def get_group_for_topic(db: Session, topic: str) -> Optional[int]:
    """Get the admin group ID for a topic."""
    group = db.query(Group).filter(Group.name == f"{topic}:admin").first()
    return group.id if group else None


def can_manage_resource(scopes: List[str], group_id: Optional[int], db: Session) -> bool:
    """
    Check if user can manage a resource.

    - Global admin can manage all resources
    - Topic admin can manage resources in their topic's group
    - Resources with no group can only be managed by global admin
    """
    if is_global_admin(scopes):
        return True

    if group_id is None:
        return False  # No group = global resource = needs global admin

    # Check if user is admin for the group's topic
    group = db.query(Group).filter(Group.id == group_id).first()
    if group:
        # Get topic from group name (e.g., "equity:admin" -> "equity")
        topic = group.groupname
        if has_role(scopes, topic, "admin"):
            return True

    return False


def resolve_group_id(db: Session, group_id: Optional[int], group_name: Optional[str]) -> Optional[int]:
    """
    Resolve group_id from either direct group_id or group_name.

    If group_name is provided (and group_id is not), looks up the group:
    - "global" -> the "global" group
    - topic names like "macro", "equity" -> the "{topic}:admin" group
    """
    if group_id is not None:
        return group_id

    if group_name is None:
        return None

    # Try to find group by exact name first (e.g., "global")
    group = db.query(Group).filter(Group.name == group_name).first()
    if group:
        return group.id

    # Try to find group by topic:admin pattern
    group = db.query(Group).filter(Group.name == f"{group_name}:admin").first()
    if group:
        return group.id

    return None


# =============================================================================
# List and Get Endpoints
# =============================================================================

@router.get("/", response_model=ResourceListResponse)
async def list_resources(
    resource_type: Optional[str] = None,
    group_id: Optional[int] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List resources with optional filtering.

    - Global admin sees all resources
    - Topic admin sees resources in their group
    - Pass group_id=0 to get global resources (no group)
    """
    scopes = current_user.get("scopes", [])

    # Convert resource_type string to enum if provided
    rt = None
    if resource_type:
        try:
            rt = ResourceType(resource_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid resource type: {resource_type}"
            )

    # Handle group_id=0 as "no group" (global resources)
    actual_group_id = None if group_id == 0 else group_id

    # Permission check
    if not is_global_admin(scopes):
        if actual_group_id is None:
            # Can't view global resources without global admin
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Global admin access required to view global resources"
            )
        # Check topic admin permission
        if not can_manage_resource(scopes, actual_group_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view these resources"
            )

    resources, total = ResourceService.list_resources(
        db, rt, actual_group_id, None, search, offset, limit
    )

    return ResourceListResponse(
        resources=[ResourceResponse(**r) for r in resources],
        total=total,
        offset=offset,
        limit=limit
    )


@router.get("/group/{topic}", response_model=ResourceListResponse)
async def list_group_resources(
    topic: str,
    resource_type: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List resources for a specific topic group.

    Any user with access to the topic can view resources (for attaching to articles).
    This includes:
    1. Resources with group_id matching any of the topic's groups (admin, analyst, editor, reader)
    2. ARTICLE resources linked to articles in this topic (these have group_id=NULL but are
       associated via the article_resources table)
    """
    scopes = current_user.get("scopes", [])

    valid_topics = get_valid_topics(db)
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic: {topic}"
        )

    # Permission check - user needs any role in this topic to view resources
    if not is_global_admin(scopes) and not (
        has_role(scopes, topic, "admin") or
        has_role(scopes, topic, "analyst") or
        has_role(scopes, topic, "editor") or
        has_role(scopes, topic, "reader")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You need access to '{topic}' to view its resources"
        )

    # Get ALL group IDs for this topic (admin, analyst, editor, reader groups)
    groups = db.query(Group).filter(Group.groupname == topic).all()
    group_ids = [g.id for g in groups] if groups else []

    # Convert resource_type string to enum if provided
    rt = None
    if resource_type:
        try:
            rt = ResourceType(resource_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid resource type: {resource_type}"
            )

    # Use the method that handles both group resources AND article resources for this topic
    resources, total = ResourceService.list_topic_resources(
        db, topic, rt, group_ids, search, offset, limit
    )

    return ResourceListResponse(
        resources=[ResourceResponse(**r) for r in resources],
        total=total,
        offset=offset,
        limit=limit
    )


@router.get("/global", response_model=ResourceListResponse)
async def list_global_resources(
    resource_type: Optional[str] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    include_linked: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List global resources (resources with no group - group_id = NULL).

    Any authenticated user can view global resources for attaching to articles.

    Args:
        include_linked: If True, include resources already linked to articles (for categorization).
                       If False (default), exclude them (for import modal).
    """
    # Convert resource_type string to enum if provided
    rt = None
    if resource_type:
        try:
            rt = ResourceType(resource_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid resource type: {resource_type}"
            )

    # Get resources with no group (group_id = NULL)
    # exclude_article_linked is the opposite of include_linked
    resources, total = ResourceService.list_resources(
        db, rt, None, None, search, offset, limit, global_only=True, exclude_article_linked=not include_linked
    )

    return ResourceListResponse(
        resources=[ResourceResponse(**r) for r in resources],
        total=total,
        offset=offset,
        limit=limit
    )


@router.get("/{resource_id}", response_model=ResourceDetailResponse)
async def get_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get a specific resource by ID with all details."""
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    # Permission check
    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this resource"
        )

    return ResourceDetailResponse(**resource_data)


# =============================================================================
# Create Endpoints
# =============================================================================

@router.post("/text", response_model=ResourceDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_text_resource(
    request: CreateTextResourceRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new text resource."""
    scopes = current_user.get("scopes", [])
    user_id = int(current_user.get("sub"))

    # Resolve group_id from group_name if needed
    group_id = resolve_group_id(db, request.group_id, request.group_name)

    # Permission check
    if not can_manage_resource(scopes, group_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to create resources in this group"
        )

    try:
        resource, text_resource = ResourceService.create_text_resource(
            db=db,
            name=request.name,
            content=request.content,
            created_by=user_id,
            encoding=request.encoding,
            description=request.description,
            group_id=group_id,
            parent_id=request.parent_id
        )

        return ResourceDetailResponse(**ResourceService.get_resource(db, resource.id))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create text resource: {str(e)}"
        )


@router.post("/table", response_model=ResourceDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_table_resource(
    request: CreateTableResourceRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new table resource."""
    scopes = current_user.get("scopes", [])
    user_id = int(current_user.get("sub"))

    # Resolve group_id from group_name if needed
    group_id = resolve_group_id(db, request.group_id, request.group_name)

    # Permission check
    if not can_manage_resource(scopes, group_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to create resources in this group"
        )

    try:
        resource, table_resource = ResourceService.create_table_resource(
            db=db,
            name=request.name,
            table_data=request.table_data,
            created_by=user_id,
            description=request.description,
            group_id=group_id,
            column_types=request.column_types,
            parent_id=request.parent_id
        )

        # Note: HTML/IMAGE child resources are created on publish, not on save

        return ResourceDetailResponse(**ResourceService.get_resource(db, resource.id))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create table resource: {str(e)}"
        )


@router.post("/timeseries", response_model=ResourceDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_timeseries_resource(
    request: CreateTimeseriesRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new timeseries resource (metadata only, data added separately)."""
    scopes = current_user.get("scopes", [])
    user_id = int(current_user.get("sub"))

    # Permission check
    if not can_manage_resource(scopes, request.group_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to create resources in this group"
        )

    # Convert frequency string to enum
    try:
        frequency = TimeseriesFrequency(request.frequency)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid frequency: {request.frequency}"
        )

    # Convert data_type string to enum
    try:
        data_type = TimeseriesDataType(request.data_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid data type: {request.data_type}"
        )

    try:
        resource, ts_metadata = ResourceService.create_timeseries_resource(
            db=db,
            name=request.name,
            columns=request.columns,
            frequency=frequency,
            created_by=user_id,
            source=request.source,
            description=request.description,
            group_id=request.group_id,
            data_type=data_type,
            unit=request.unit,
            parent_id=request.parent_id
        )

        return ResourceDetailResponse(**ResourceService.get_resource(db, resource.id))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create timeseries resource: {str(e)}"
        )


def get_resource_type_from_mime(mime_type: str) -> Optional[ResourceType]:
    """Determine resource type from MIME type."""
    mime_map = {
        'image/png': ResourceType.IMAGE,
        'image/jpeg': ResourceType.IMAGE,
        'image/gif': ResourceType.IMAGE,
        'image/webp': ResourceType.IMAGE,
        'image/svg+xml': ResourceType.IMAGE,
        'application/pdf': ResourceType.PDF,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ResourceType.EXCEL,
        'application/vnd.ms-excel': ResourceType.EXCEL,
        'application/zip': ResourceType.ZIP,
        'application/x-zip-compressed': ResourceType.ZIP,
        'text/csv': ResourceType.CSV,
        'application/csv': ResourceType.CSV,
        'text/plain': ResourceType.TEXT,
    }
    return mime_map.get(mime_type)


@router.post("/file", response_model=ResourceDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_file_resource(
    file: UploadFile = File(...),
    name: str = Form(...),
    resource_type: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    group_id: Optional[int] = Form(None),
    group_name: Optional[str] = Form(None),  # Alternative: topic name like "macro" or "global"
    article_id: Optional[int] = Form(None),
    parent_id: Optional[int] = Form(None),  # For derived resources (e.g., image from PDF)
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload a file resource.

    resource_type is optional - if not provided, will be inferred from MIME type.
    If article_id is provided, the resource will be linked to that article.
    group_name can be used instead of group_id (e.g., "macro" or "global").
    parent_id can be used to link this resource as a child of another resource.
    """
    scopes = current_user.get("scopes", [])
    user_id = int(current_user.get("sub"))

    # Resolve group_id from group_name if needed
    group_id = resolve_group_id(db, group_id, group_name)

    # If no group_id provided, this is an article-level resource (needs article_id or global admin)
    if group_id is None and article_id is None and not is_global_admin(scopes):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either group_id or article_id must be provided for non-global admins"
        )

    # Permission check for group resources
    if group_id is not None and not can_manage_resource(scopes, group_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to create resources in this group"
        )

    # If article_id provided, verify article exists and user can edit it
    if article_id:
        article = db.query(ContentArticle).filter(ContentArticle.id == article_id).first()
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Article not found"
            )
        # Check if user can edit this article's topic
        if not is_global_admin(scopes):
            topic = article.topic
            if not (has_role(scopes, topic, "admin") or
                    has_role(scopes, topic, "analyst") or
                    has_role(scopes, topic, "editor")):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to add resources to this article"
                )

    # Determine resource type
    if resource_type:
        try:
            rt = ResourceType(resource_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid resource type: {resource_type}"
            )
    else:
        # Infer from MIME type
        rt = get_resource_type_from_mime(file.content_type)
        if not rt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {file.content_type}"
            )

    # Read file content
    content = await file.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
        )

    # Calculate checksum
    checksum = hashlib.sha256(content).hexdigest()

    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1] if file.filename else ''
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"

    # Create subdirectory path by date
    date_dir = datetime.now().strftime("%Y/%m")
    file_path = f"{date_dir}/{unique_filename}"

    # Handle text files specially - store content in TextResource
    if rt == ResourceType.TEXT:
        try:
            text_content = content.decode('utf-8')
            resource, text_resource = ResourceService.create_text_resource(
                db=db,
                name=name,
                content=text_content,
                created_by=user_id,
                encoding='utf-8',
                description=description,
                group_id=group_id,
                parent_id=parent_id
            )
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text file must be UTF-8 encoded"
            )
    else:
        # Save file using storage service (works with both local and S3)
        mime_type = file.content_type or 'application/octet-stream'
        if not storage.save_file_with_metadata(file_path, content, mime_type):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save file to storage"
            )

        # Create file resource in database
        try:
            resource, file_resource = ResourceService.create_file_resource(
                db=db,
                name=name,
                resource_type=rt,
                filename=file.filename or unique_filename,
                file_path=file_path,
                file_size=file_size,
                mime_type=mime_type,
                created_by=user_id,
                checksum=checksum,
                description=description,
                group_id=group_id,
                parent_id=parent_id
            )
        except Exception as e:
            # Clean up file on error
            storage.delete_file(file_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create resource: {str(e)}"
            )

    # Link to article if article_id provided
    if article_id:
        ResourceService.link_resource_to_article(db, resource.id, article_id)

    return ResourceDetailResponse(**ResourceService.get_resource(db, resource.id))


# =============================================================================
# Timeseries Data Endpoints
# =============================================================================

@router.post("/{resource_id}/timeseries/data")
async def add_timeseries_data(
    resource_id: int,
    request: AddTimeseriesDataRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Add data points to a timeseries resource."""
    # Get resource to check permissions and type
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    if resource_data.get("resource_type") != "timeseries":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resource is not a timeseries"
        )

    # Permission check
    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this resource"
        )

    user_id = int(current_user.get("sub"))
    tsid = resource_data.get("timeseries_data", {}).get("tsid")

    if not tsid:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Timeseries metadata not found"
        )

    try:
        count = ResourceService.add_timeseries_data(
            db=db,
            tsid=tsid,
            data_points=request.data_points,
            user_id=user_id
        )
        return {"message": f"Added {count} data points", "count": count}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{resource_id}/timeseries/data")
async def get_timeseries_data(
    resource_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    columns: Optional[str] = None,  # comma-separated
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get data points from a timeseries resource."""
    from datetime import datetime

    # Get resource to check permissions and type
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    if resource_data.get("resource_type") != "timeseries":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resource is not a timeseries"
        )

    # Permission check
    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this resource"
        )

    tsid = resource_data.get("timeseries_data", {}).get("tsid")

    if not tsid:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Timeseries metadata not found"
        )

    # Parse dates
    start = None
    end = None
    if start_date:
        try:
            start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format"
            )
    if end_date:
        try:
            end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format"
            )

    # Parse columns
    cols = columns.split(",") if columns else None

    data = ResourceService.get_timeseries_data(
        db=db,
        tsid=tsid,
        start_date=start,
        end_date=end,
        columns=cols
    )

    return {"data": data, "count": len(data)}


# =============================================================================
# Update and Delete Endpoints
# =============================================================================

@router.put("/{resource_id}", response_model=ResourceDetailResponse)
async def update_resource(
    resource_id: int,
    request: UpdateResourceRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update resource metadata."""
    # Get current resource
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    # Permission check for current group
    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this resource"
        )

    # If changing group, check permission for new group too
    if request.group_id is not None and request.group_id != resource_data.get("group_id"):
        if not can_manage_resource(scopes, request.group_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to move resource to this group"
            )

    user_id = int(current_user.get("sub"))

    updated = ResourceService.update_resource(
        db=db,
        resource_id=resource_id,
        user_id=user_id,
        name=request.name,
        description=request.description,
        group_id=request.group_id
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update resource"
        )

    return ResourceDetailResponse(**ResourceService.get_resource(db, resource_id))


@router.put("/{resource_id}/text-content", response_model=ResourceDetailResponse)
async def update_text_content(
    resource_id: int,
    request: UpdateTextContentRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update text resource content."""
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    if resource_data.get("resource_type") != "text":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resource is not a text resource"
        )

    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this resource"
        )

    user_id = int(current_user.get("sub"))

    updated = ResourceService.update_text_content(
        db=db,
        resource_id=resource_id,
        content=request.content,
        encoding=request.encoding,
        user_id=user_id
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update text content"
        )

    return ResourceDetailResponse(**ResourceService.get_resource(db, resource_id))


@router.put("/{resource_id}/table-content", response_model=ResourceDetailResponse)
async def update_table_content(
    resource_id: int,
    request: UpdateTableContentRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update table resource content."""
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    if resource_data.get("resource_type") != "table":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resource is not a table resource"
        )

    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this resource"
        )

    user_id = int(current_user.get("sub"))

    updated = ResourceService.update_table_content(
        db=db,
        resource_id=resource_id,
        table_data=request.table_data,
        column_types=request.column_types,
        user_id=user_id
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update table content"
        )

    # Note: HTML/IMAGE child resources are regenerated on publish, not on save
    # If the table was already published, user must re-publish to update child resources

    return ResourceDetailResponse(**ResourceService.get_resource(db, resource_id))


@router.put("/{resource_id}/timeseries-data", response_model=ResourceDetailResponse)
async def update_timeseries_data(
    resource_id: int,
    request: UpdateTimeseriesDataRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update timeseries data."""
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    if resource_data.get("resource_type") != "timeseries":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resource is not a timeseries resource"
        )

    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this resource"
        )

    user_id = int(current_user.get("sub"))

    updated = ResourceService.update_timeseries_data(
        db=db,
        resource_id=resource_id,
        data=request.data,
        user_id=user_id
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update timeseries data"
        )

    return ResourceDetailResponse(**ResourceService.get_resource(db, resource_id))


@router.delete("/{resource_id}")
async def delete_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete (deactivate) a resource."""
    # Get current resource
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    # Permission check
    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this resource"
        )

    user_id = int(current_user.get("sub"))

    success = ResourceService.delete_resource(db, resource_id, user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete resource"
        )

    return {"message": "Resource deleted successfully", "id": resource_id}


# =============================================================================
# Article Linking Endpoints
# =============================================================================

@router.get("/article/{article_id}")
async def get_article_resources(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all resources linked to an article."""
    # Verify article exists
    article = db.query(ContentArticle).filter(ContentArticle.id == article_id).first()
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )

    # Permission check - user must be able to view this article's topic
    scopes = current_user.get("scopes", [])
    if not is_global_admin(scopes):
        topic = article.topic
        if not (has_role(scopes, topic, "admin") or
                has_role(scopes, topic, "analyst") or
                has_role(scopes, topic, "editor") or
                has_role(scopes, topic, "reader")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this article's resources"
            )

    resources = ResourceService.get_article_resources(db, article_id)
    return {"resources": resources, "count": len(resources)}


@router.post("/{resource_id}/link")
async def link_resource_to_article(
    resource_id: int,
    request: LinkArticleRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Link a resource to an article."""
    # Get resource to check it exists
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    # Permission check
    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to link this resource"
        )

    success = ResourceService.link_resource_to_article(db, resource_id, request.article_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to link resource to article"
        )

    return {"message": "Resource linked to article", "resource_id": resource_id, "article_id": request.article_id}


@router.delete("/{resource_id}/link/{article_id}")
async def unlink_resource_from_article(
    resource_id: int,
    article_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Unlink a resource from an article."""
    # Get resource to check it exists
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    # Permission check
    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to unlink this resource"
        )

    success = ResourceService.unlink_resource_from_article(db, resource_id, article_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link not found"
        )

    return {"message": "Resource unlinked from article", "resource_id": resource_id, "article_id": article_id}


@router.get("/{resource_id}/articles")
async def get_resource_articles(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all articles linked to a resource."""
    # Get resource to check it exists
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    # Permission check
    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view this resource"
        )

    articles = ResourceService.get_resource_articles(db, resource_id)

    return {"articles": articles, "count": len(articles)}


# =============================================================================
# Status Management Endpoints
# =============================================================================

@router.put("/{resource_id}/status", response_model=ResourceDetailResponse)
async def update_resource_status(
    resource_id: int,
    request: UpdateResourceStatusRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update resource status (editorial workflow).

    Status transitions: draft -> editor -> published
    Same workflow as articles.

    Note: For tables, use /{resource_id}/publish and /{resource_id}/recall
    endpoints instead, which also manage child resources (HTML, IMAGE).
    This endpoint only changes the status flag without creating children.
    """
    # Get current resource
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    # Permission check
    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this resource"
        )

    # Validate status
    try:
        new_status = ResourceStatus(request.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {request.status}. Must be one of: draft, editor, published"
        )

    user_id = int(current_user.get("sub"))

    updated = ResourceService.update_resource_status(
        db=db,
        resource_id=resource_id,
        status=new_status,
        user_id=user_id
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update resource status"
        )

    return ResourceDetailResponse(**ResourceService.get_resource(db, resource_id))


@router.post("/{resource_id}/publish", response_model=ResourceDetailResponse)
async def publish_table_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Publish a table resource.

    Creates HTML and IMAGE child resources for the published table.
    Changes status from draft/editor to published.

    Only applicable to table resources.
    """
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    if resource_data.get("resource_type") != "table":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only table resources can be published via this endpoint"
        )

    # Permission check
    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to publish this resource"
        )

    user_id = int(current_user.get("sub"))

    # Get the table resource
    table_resource = db.query(Resource).filter(Resource.id == resource_id).first()

    # Create publication resources (HTML + IMAGE children)
    html_resource, image_resource = TableResourceService.create_table_publication_resources(
        db=db,
        table_resource=table_resource,
        user_id=user_id
    )

    if not html_resource:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create publication resources"
        )

    # Update status to published
    ResourceService.update_resource_status(
        db=db,
        resource_id=resource_id,
        status=ResourceStatus.PUBLISHED,
        user_id=user_id
    )

    logger.info(f"Published table resource {resource_id} with HTML child {html_resource.id}")

    return ResourceDetailResponse(**ResourceService.get_resource(db, resource_id))


@router.post("/{resource_id}/recall", response_model=ResourceDetailResponse)
async def recall_table_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Recall a published table resource.

    Deletes HTML and IMAGE child resources.
    Changes status from published back to draft.

    Only applicable to table resources.
    """
    resource_data = ResourceService.get_resource(db, resource_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    if resource_data.get("resource_type") != "table":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only table resources can be recalled via this endpoint"
        )

    if resource_data.get("status") != "published":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only published resources can be recalled"
        )

    # Permission check
    scopes = current_user.get("scopes", [])
    if not can_manage_resource(scopes, resource_data.get("group_id"), db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to recall this resource"
        )

    user_id = int(current_user.get("sub"))

    # Delete publication resources (HTML + IMAGE children)
    deleted_count = TableResourceService.delete_table_publication_resources(db, resource_id)
    logger.info(f"Deleted {deleted_count} publication resources for table {resource_id}")

    # Update status to draft
    ResourceService.update_resource_status(
        db=db,
        resource_id=resource_id,
        status=ResourceStatus.DRAFT,
        user_id=user_id
    )

    return ResourceDetailResponse(**ResourceService.get_resource(db, resource_id))


# =============================================================================
# Public Content Endpoints (No Authentication Required)
# These use hash_id for security through obscurity - no auth needed
# URL pattern: /api/r/{hash_id} (short public URL)
# =============================================================================

# Create a separate public router with shorter prefix
public_router = APIRouter(prefix="/api/r", tags=["public-resources"])


@public_router.get("/{hash_id}")
async def serve_public_resource(
    hash_id: str,
    db: Session = Depends(get_db)
):
    """
    Serve resource content by public hash_id.

    This endpoint is PUBLIC (no authentication required) to allow
    use in HTML img tags and other static content references.

    For file-based resources (images, PDFs, etc.), returns the file content
    with appropriate Content-Type headers.

    For text resources, returns the text content as plain text.

    For table resources, returns the table data as JSON.

    Example usage in HTML:
        <img src="/api/r/abc123xyz" />
    """
    # Get file path info (returns relative path, mime_type, filename)
    file_info = ResourceService.get_resource_file_path(db, hash_id)

    if file_info:
        # This is a file-based resource
        relative_path, mime_type, filename = file_info

        # Get file content using storage service (works with both local and S3)
        file_content = storage.get_file(relative_path)

        if file_content is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resource file not found"
            )

        # Determine cache duration based on content type
        # HTML files (article popups) can be republished, so use shorter cache
        # Images and PDFs are immutable, so use long cache
        if mime_type and mime_type.startswith("text/html"):
            cache_control = "public, max-age=60"  # 1 minute for HTML (can be republished)
        else:
            cache_control = "public, max-age=31536000"  # 1 year for images/PDFs

        # Return file as streaming response
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=mime_type,
            headers={
                "Cache-Control": cache_control,
                "Content-Disposition": f"inline; filename=\"{filename}\""
            }
        )

    # Not a file resource - try getting resource data
    resource_data = ResourceService.get_resource_by_hash_id(db, hash_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    resource_type = resource_data.get("resource_type")

    # Handle text resources
    if resource_type == "text":
        text_data = resource_data.get("text_data", {})
        content = text_data.get("content", "")

        # Check if content is HTML (for article HTML resources)
        content_stripped = content.strip().lower()
        if content_stripped.startswith("<!doctype html") or content_stripped.startswith("<html"):
            return Response(
                content=content,
                media_type="text/html; charset=utf-8",
                headers={
                    "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                }
            )

        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            }
        )

    # Handle table resources
    if resource_type == "table":
        table_data = resource_data.get("table_data", {})
        return Response(
            content=json.dumps(table_data.get("data", {})),
            media_type="application/json",
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            }
        )

    # Handle HTML resources (article HTML children)
    if resource_type == "html":
        text_data = resource_data.get("text_data", {})
        content = text_data.get("content", "")

        return Response(
            content=content,
            media_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            }
        )

    # Handle article resources - serve stored text content as HTML if available
    if resource_type == "article":
        text_data = resource_data.get("text_data", {})
        content = text_data.get("content", "")

        if content:
            # Serve stored content as HTML
            return Response(
                content=content,
                media_type="text/html; charset=utf-8",
                headers={
                    "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Article resource has no stored content"
            )

    # Unsupported resource type for direct content serving
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Resource type '{resource_type}' cannot be served as content"
    )


@public_router.get("/{hash_id}/info")
async def get_resource_content_info(
    hash_id: str,
    db: Session = Depends(get_db)
):
    """
    Get basic info about a resource by hash_id (public endpoint).

    Returns minimal metadata without requiring authentication.
    Useful for checking if a resource exists and its type.

    For table resources, also returns html_child_hash_id for embedding.
    """
    resource_data = ResourceService.get_resource_by_hash_id(db, hash_id)

    if not resource_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    result = {
        "hash_id": hash_id,
        "name": resource_data.get("name"),
        "resource_type": resource_data.get("resource_type"),
        "status": resource_data.get("status")
    }

    # For table resources, find the HTML child for embedding
    if resource_data.get("resource_type") == "table":
        resource = db.query(Resource).filter(Resource.hash_id == hash_id).first()
        if resource:
            html_child = db.query(Resource).filter(
                Resource.parent_id == resource.id,
                Resource.resource_type == ResourceType.HTML,
                Resource.is_active == True
            ).first()
            if html_child:
                result["html_child_hash_id"] = html_child.hash_id
            # Also include image child hash for PDF embedding
            image_child = db.query(Resource).filter(
                Resource.parent_id == resource.id,
                Resource.resource_type == ResourceType.IMAGE,
                Resource.is_active == True
            ).first()
            if image_child:
                result["image_child_hash_id"] = image_child.hash_id

    return result


@public_router.get("/{hash_id}/embed")
async def get_resource_embed_html(
    hash_id: str,
    db: Session = Depends(get_db)
):
    """
    Get embeddable HTML fragment for a table resource.

    Returns the table as an HTML fragment (styles + table + script) that can be
    directly embedded into another HTML document without an iframe.

    For table resources, generates an interactive table with:
    - Column sorting (click header)
    - Column reordering (drag & drop headers)
    - Row selection (click rows, Ctrl+click for multi-select, Shift+click for range)
    - Column selection (Ctrl+click header)
    - Copy to clipboard (Ctrl+C on selected rows/column)
    """
    from services.table_resource_service import TableResourceService

    resource = db.query(Resource).filter(Resource.hash_id == hash_id).first()
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )

    if resource.resource_type != ResourceType.TABLE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Embed endpoint only supports table resources"
        )

    if not resource.table_resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table data not found"
        )

    # Generate unique table ID based on hash
    table_id = f"table-{hash_id}"

    # Get table data
    columns = resource.table_resource.columns or []
    data = resource.table_resource.data or []

    # Generate embeddable HTML fragment
    embed_html = TableResourceService._generate_embeddable_table_html(
        table_id=table_id,
        name=resource.name,
        columns=columns,
        data=data
    )

    return Response(
        content=embed_html,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
        }
    )
