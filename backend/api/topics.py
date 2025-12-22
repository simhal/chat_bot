"""API endpoints for topic management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from database import get_db
from models import Topic, Group, ContentArticle
from dependencies import get_current_user, require_admin
import logging

logger = logging.getLogger("uvicorn")

router = APIRouter(prefix="/api/topics", tags=["topics"])


# Pydantic models for request/response

class TopicCreate(BaseModel):
    """Request model for creating a topic."""
    slug: str = Field(..., min_length=2, max_length=50, pattern=r'^[a-z][a-z0-9_]*$')
    title: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    visible: bool = True
    searchable: bool = True
    active: bool = True
    agent_type: Optional[str] = None
    agent_config: Optional[Dict[str, Any]] = None
    access_mainchat: bool = True
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: int = 0
    article_order: str = "date"  # 'date', 'priority', 'title'


class TopicUpdate(BaseModel):
    """Request model for updating a topic."""
    title: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    visible: Optional[bool] = None
    searchable: Optional[bool] = None
    active: Optional[bool] = None
    agent_type: Optional[str] = None
    agent_config: Optional[Dict[str, Any]] = None
    access_mainchat: Optional[bool] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    article_order: Optional[str] = None  # 'date', 'priority', 'title'


class TopicResponse(BaseModel):
    """Response model for topic."""
    id: int
    slug: str
    title: str
    description: Optional[str]
    visible: bool
    searchable: bool
    active: bool
    reader_count: int
    rating_average: Optional[float]
    article_count: int
    agent_type: Optional[str]
    agent_config: Optional[Dict[str, Any]]
    access_mainchat: bool
    icon: Optional[str]
    color: Optional[str]
    sort_order: int
    article_order: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class TopicListResponse(BaseModel):
    """Response model for topic list (lighter version)."""
    id: int
    slug: str
    title: str
    description: Optional[str]
    visible: bool
    active: bool
    article_count: int
    access_mainchat: bool
    icon: Optional[str]
    color: Optional[str]
    sort_order: int
    article_order: str

    class Config:
        from_attributes = True


# Default group roles to create for each topic
DEFAULT_ROLES = ["admin", "analyst", "editor", "reader"]


def create_groups_for_topic(db: Session, topic: Topic) -> List[Group]:
    """Create the 4 default groups for a topic."""
    groups = []
    for role in DEFAULT_ROLES:
        group_name = f"{topic.slug}:{role}"

        # Check if group already exists
        existing = db.query(Group).filter(Group.name == group_name).first()
        if existing:
            existing.topic_id = topic.id
            groups.append(existing)
            continue

        group = Group(
            name=group_name,
            groupname=topic.slug,
            role=role,
            topic_id=topic.id,
            description=f"{role.capitalize()} role for {topic.title}"
        )
        db.add(group)
        groups.append(group)

    return groups


@router.get("/", response_model=List[TopicListResponse])
async def list_topics(
    active_only: bool = False,
    visible_only: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """
    List all topics.

    All authenticated users can list topics.
    Filter by active and visible status.
    """
    query = db.query(Topic)

    if active_only:
        query = query.filter(Topic.active == True)
    if visible_only:
        query = query.filter(Topic.visible == True)

    topics = query.order_by(Topic.sort_order, Topic.title).all()

    return [
        TopicListResponse(
            id=t.id,
            slug=t.slug,
            title=t.title,
            description=t.description,
            visible=t.visible,
            active=t.active,
            article_count=t.article_count,
            access_mainchat=t.access_mainchat,
            icon=t.icon,
            color=t.color,
            sort_order=t.sort_order,
            article_order=t.article_order
        )
        for t in topics
    ]


@router.get("/public", response_model=List[TopicListResponse])
async def list_public_topics(
    db: Session = Depends(get_db)
):
    """
    List public (visible and active) topics.

    This endpoint does not require authentication.
    Used for showing topic navigation before login.
    """
    topics = db.query(Topic).filter(
        Topic.active == True,
        Topic.visible == True
    ).order_by(Topic.sort_order, Topic.title).all()

    return [
        TopicListResponse(
            id=t.id,
            slug=t.slug,
            title=t.title,
            description=t.description,
            visible=t.visible,
            active=t.active,
            article_count=t.article_count,
            access_mainchat=t.access_mainchat,
            icon=t.icon,
            color=t.color,
            sort_order=t.sort_order,
            article_order=t.article_order
        )
        for t in topics
    ]


@router.get("/{slug}", response_model=TopicResponse)
async def get_topic(
    slug: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get a specific topic by slug."""
    topic = db.query(Topic).filter(Topic.slug == slug).first()

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{slug}' not found"
        )

    return TopicResponse(
        id=topic.id,
        slug=topic.slug,
        title=topic.title,
        description=topic.description,
        visible=topic.visible,
        searchable=topic.searchable,
        active=topic.active,
        reader_count=topic.reader_count,
        rating_average=topic.rating_average,
        article_count=topic.article_count,
        agent_type=topic.agent_type,
        agent_config=topic.agent_config,
        access_mainchat=topic.access_mainchat,
        icon=topic.icon,
        color=topic.color,
        sort_order=topic.sort_order,
        article_order=topic.article_order,
        created_at=topic.created_at.isoformat(),
        updated_at=topic.updated_at.isoformat()
    )


@router.post("/", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def create_topic(
    topic_data: TopicCreate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Create a new topic. Requires global:admin scope.

    Automatically creates 4 groups: {slug}:admin, {slug}:analyst, {slug}:editor, {slug}:reader
    """
    # Check if slug already exists
    existing = db.query(Topic).filter(Topic.slug == topic_data.slug).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Topic with slug '{topic_data.slug}' already exists"
        )

    # Create topic
    topic = Topic(
        slug=topic_data.slug,
        title=topic_data.title,
        description=topic_data.description,
        visible=topic_data.visible,
        searchable=topic_data.searchable,
        active=topic_data.active,
        agent_type=topic_data.agent_type,
        agent_config=topic_data.agent_config,
        access_mainchat=topic_data.access_mainchat,
        icon=topic_data.icon,
        color=topic_data.color,
        sort_order=topic_data.sort_order,
        article_order=topic_data.article_order
    )
    db.add(topic)
    db.flush()  # Get the topic ID

    # Create 4 default groups for this topic
    groups = create_groups_for_topic(db, topic)

    db.commit()
    db.refresh(topic)

    logger.info(f"Created topic '{topic.slug}' with {len(groups)} groups")

    return TopicResponse(
        id=topic.id,
        slug=topic.slug,
        title=topic.title,
        description=topic.description,
        visible=topic.visible,
        searchable=topic.searchable,
        active=topic.active,
        reader_count=topic.reader_count,
        rating_average=topic.rating_average,
        article_count=topic.article_count,
        agent_type=topic.agent_type,
        agent_config=topic.agent_config,
        access_mainchat=topic.access_mainchat,
        icon=topic.icon,
        color=topic.color,
        sort_order=topic.sort_order,
        article_order=topic.article_order,
        created_at=topic.created_at.isoformat(),
        updated_at=topic.updated_at.isoformat()
    )


@router.patch("/{slug}", response_model=TopicResponse)
async def update_topic(
    slug: str,
    topic_data: TopicUpdate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Update a topic. Requires global:admin scope.

    Note: slug cannot be changed after creation.
    """
    topic = db.query(Topic).filter(Topic.slug == slug).first()

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{slug}' not found"
        )

    # Update fields
    update_data = topic_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(topic, field, value)

    db.commit()
    db.refresh(topic)

    logger.info(f"Updated topic '{topic.slug}'")

    return TopicResponse(
        id=topic.id,
        slug=topic.slug,
        title=topic.title,
        description=topic.description,
        visible=topic.visible,
        searchable=topic.searchable,
        active=topic.active,
        reader_count=topic.reader_count,
        rating_average=topic.rating_average,
        article_count=topic.article_count,
        agent_type=topic.agent_type,
        agent_config=topic.agent_config,
        access_mainchat=topic.access_mainchat,
        icon=topic.icon,
        color=topic.color,
        sort_order=topic.sort_order,
        article_order=topic.article_order,
        created_at=topic.created_at.isoformat(),
        updated_at=topic.updated_at.isoformat()
    )


@router.delete("/{slug}")
async def delete_topic(
    slug: str,
    force: bool = False,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Delete a topic. Requires global:admin scope.

    By default, cannot delete topics that have articles.
    Use force=true to delete anyway (articles will have topic_id set to NULL).

    Note: Associated groups will be deleted due to CASCADE.
    """
    topic = db.query(Topic).filter(Topic.slug == slug).first()

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{slug}' not found"
        )

    # Check for articles
    article_count = db.query(ContentArticle).filter(
        ContentArticle.topic_id == topic.id
    ).count()

    if article_count > 0 and not force:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Topic '{slug}' has {article_count} articles. Use force=true to delete anyway."
        )

    topic_id = topic.id
    db.delete(topic)
    db.commit()

    logger.info(f"Deleted topic '{slug}' (id={topic_id})")

    return {"message": f"Topic '{slug}' deleted successfully", "deleted_id": topic_id}


@router.post("/{slug}/recalculate-stats")
async def recalculate_topic_stats(
    slug: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Recalculate article_count, reader_count, and rating_average for a topic.
    Requires global:admin scope.
    """
    topic = db.query(Topic).filter(Topic.slug == slug).first()

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{slug}' not found"
        )

    _recalculate_topic_stats(db, topic)

    return {
        "message": f"Stats recalculated for topic '{slug}'",
        "article_count": topic.article_count,
        "reader_count": topic.reader_count,
        "rating_average": topic.rating_average
    }


def _recalculate_topic_stats(db: Session, topic: Topic):
    """Internal helper to recalculate stats for a single topic."""
    from sqlalchemy import func

    article_count = db.query(ContentArticle).filter(
        ContentArticle.topic_id == topic.id,
        ContentArticle.is_active == True
    ).count()

    reader_count_result = db.query(func.sum(ContentArticle.readership_count)).filter(
        ContentArticle.topic_id == topic.id,
        ContentArticle.is_active == True
    ).scalar()
    reader_count = reader_count_result or 0

    rating_avg_result = db.query(func.avg(ContentArticle.rating)).filter(
        ContentArticle.topic_id == topic.id,
        ContentArticle.is_active == True,
        ContentArticle.rating.isnot(None)
    ).scalar()
    rating_average = float(rating_avg_result) if rating_avg_result else None

    topic.article_count = article_count
    topic.reader_count = reader_count
    topic.rating_average = rating_average


class TopicReorderItem(BaseModel):
    """Item for reordering topics."""
    slug: str
    sort_order: int


class TopicReorderRequest(BaseModel):
    """Request model for bulk reordering topics."""
    topics: List[TopicReorderItem]


@router.post("/reorder")
async def reorder_topics(
    reorder_data: TopicReorderRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Bulk update sort_order for multiple topics.
    Requires global:admin scope.

    Accepts a list of {slug, sort_order} pairs and updates each topic's sort_order.
    """
    updated = []
    for item in reorder_data.topics:
        topic = db.query(Topic).filter(Topic.slug == item.slug).first()
        if topic:
            topic.sort_order = item.sort_order
            updated.append(item.slug)

    db.commit()

    logger.info(f"Reordered {len(updated)} topics")

    return {
        "message": f"Reordered {len(updated)} topics",
        "updated": updated
    }


@router.post("/recalculate-all")
async def recalculate_all_topic_stats(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Recalculate stats for all topics.
    Requires global:admin scope.
    """
    topics = db.query(Topic).all()

    for topic in topics:
        _recalculate_topic_stats(db, topic)

    db.commit()

    logger.info(f"Recalculated stats for {len(topics)} topics")

    return {
        "message": f"Stats recalculated for {len(topics)} topics",
        "count": len(topics)
    }


@router.get("/{slug}/groups")
async def get_topic_groups(
    slug: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Get all groups for a topic. Requires global:admin scope.
    """
    topic = db.query(Topic).filter(Topic.slug == slug).first()

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic '{slug}' not found"
        )

    groups = db.query(Group).filter(Group.topic_id == topic.id).all()

    return [
        {
            "id": g.id,
            "name": g.name,
            "groupname": g.groupname,
            "role": g.role,
            "description": g.description,
            "user_count": len(g.users)
        }
        for g in groups
    ]
