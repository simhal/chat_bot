"""
Shared dependency functions for FastAPI endpoints.
This module provides reusable dependencies that can be imported by all API routers.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth import verify_access_token
from typing import List
from sqlalchemy.orm import Session
from database import get_db

security = HTTPBearer()


def get_valid_topics(db: Session, active_only: bool = True) -> List[str]:
    """
    Get list of valid topic slugs from the database.

    Args:
        db: Database session
        active_only: If True, only return active topics

    Returns:
        List of topic slugs
    """
    from models import Topic

    query = db.query(Topic.slug)
    if active_only:
        query = query.filter(Topic.active == True)

    return [row[0] for row in query.all()]


def get_valid_topics_sync(active_only: bool = True) -> List[str]:
    """
    Get list of valid topic slugs from the database (synchronous version).
    Creates its own database session.

    Args:
        active_only: If True, only return active topics

    Returns:
        List of topic slugs
    """
    from database import SessionLocal
    from models import Topic

    db = SessionLocal()
    try:
        query = db.query(Topic.slug)
        if active_only:
            query = query.filter(Topic.active == True)
        return [row[0] for row in query.all()]
    finally:
        db.close()


def has_role(scopes: List[str], groupname: str, role: str) -> bool:
    """
    Check if user has a specific role in a group.

    Args:
        scopes: List of user scopes in format "groupname:role"
        groupname: Group name (macro, equity, fixed_income, esg, global)
        role: Role name (admin, analyst, editor, reader)

    Returns:
        True if user has the role, False otherwise
    """
    scope = f"{groupname}:{role}"
    return scope in scopes


def has_any_role_in_group(scopes: List[str], groupname: str, roles: List[str]) -> bool:
    """
    Check if user has any of the specified roles in a group.
    """
    for role in roles:
        if has_role(scopes, groupname, role):
            return True
    return False


def is_global_admin(scopes: List[str]) -> bool:
    """Check if user has global admin role."""
    return has_role(scopes, "global", "admin")


def is_global_editor(scopes: List[str]) -> bool:
    """Check if user has global editor role."""
    return has_role(scopes, "global", "editor")


def is_global_analyst(scopes: List[str]) -> bool:
    """Check if user has global analyst role."""
    return has_role(scopes, "global", "analyst")


def is_global_reader(scopes: List[str]) -> bool:
    """Check if user has global reader role."""
    return has_role(scopes, "global", "reader")


def has_global_role_or_higher(scopes: List[str], min_role: str) -> bool:
    """
    Check if user has the specified global role or higher.

    Role hierarchy: admin > editor > analyst > reader

    Args:
        scopes: User's scopes
        min_role: Minimum required role (reader, analyst, editor, admin)

    Returns:
        True if user has the role or higher in global scope
    """
    role_hierarchy = ["reader", "analyst", "editor", "admin"]

    if min_role not in role_hierarchy:
        return False

    min_index = role_hierarchy.index(min_role)

    for i in range(min_index, len(role_hierarchy)):
        if has_role(scopes, "global", role_hierarchy[i]):
            return True

    return False


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Dependency to get the current authenticated user from JWT token.

    Args:
        credentials: HTTP Bearer token from Authorization header

    Returns:
        User dict with claims from JWT token (sub, email, name, scopes, etc.)

    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials
    user = verify_access_token(token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency to require global admin role.

    Args:
        user: Current authenticated user from get_current_user dependency

    Returns:
        User dict if user has global:admin scope

    Raises:
        HTTPException: If user does not have global:admin scope
    """
    scopes = user.get("scopes", [])

    if not is_global_admin(scopes):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Global admin access required"
        )

    return user


def require_analyst(topic: str):
    """
    Dependency factory to require analyst, editor, or admin role for a specific topic.
    Global admins also have access.

    Args:
        topic: Topic name (any valid topic slug from database)

    Returns:
        Dependency function that checks for appropriate permissions
    """
    def check_analyst_permission(user: dict = Depends(get_current_user)) -> dict:
        """
        Check if user has analyst/editor/admin permission for the topic.

        Args:
            user: Current authenticated user

        Returns:
            User dict if user has required permissions

        Raises:
            HTTPException: If user does not have required permissions
        """
        scopes = user.get("scopes", [])

        # Global admin can access all content
        if is_global_admin(scopes):
            return user

        # Validate topic against database
        valid_topics = get_valid_topics_sync()
        if topic not in valid_topics:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid topic: {topic}"
            )

        # Check if user has admin, analyst, or editor role for this topic
        if has_any_role_in_group(scopes, topic, ["admin", "analyst", "editor"]):
            return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. You need '{topic}:admin', '{topic}:analyst', or '{topic}:editor' role to access {topic} content."
        )

    return check_analyst_permission


def require_editor(topic: str):
    """
    Dependency factory to require editor or admin role for a specific topic.
    Global admins also have access.

    Args:
        topic: Topic name (any valid topic slug from database)

    Returns:
        Dependency function that checks for editor permissions
    """
    def check_editor_permission(user: dict = Depends(get_current_user)) -> dict:
        """
        Check if user has editor/admin permission for the topic.
        """
        scopes = user.get("scopes", [])

        # Global admin can access all content
        if is_global_admin(scopes):
            return user

        # Validate topic against database
        valid_topics = get_valid_topics_sync()
        if topic not in valid_topics:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid topic: {topic}"
            )

        # Check if user has admin or editor role for this topic
        if has_any_role_in_group(scopes, topic, ["admin", "editor"]):
            return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. You need '{topic}:admin' or '{topic}:editor' role to edit {topic} content."
        )

    return check_editor_permission


def require_topic_admin(topic: str):
    """
    Dependency factory to require admin role for a specific topic.
    Global admins also have access.

    Args:
        topic: Topic name (any valid topic slug from database)

    Returns:
        Dependency function that checks for topic admin permissions
    """
    def check_topic_admin_permission(user: dict = Depends(get_current_user)) -> dict:
        """
        Check if user has admin permission for the topic.
        """
        scopes = user.get("scopes", [])

        # Global admin can access all content
        if is_global_admin(scopes):
            return user

        # Validate topic against database
        valid_topics = get_valid_topics_sync()
        if topic not in valid_topics:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid topic: {topic}"
            )

        # Check if user has admin role for this topic
        if has_role(scopes, topic, "admin"):
            return user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. You need '{topic}:admin' role to manage {topic} prompts."
        )

    return check_topic_admin_permission


def can_edit_prompt(prompt_type: str, prompt_group: str = None):
    """
    Dependency factory to check if user can edit a specific prompt type.

    Permission rules:
    - global:admin can edit all prompts
    - {topic}:admin can edit content_topic prompts for their topic only
    - Users cannot edit any prompts

    Args:
        prompt_type: Type of prompt (general, chat_specific, content_topic, tonality, etc.)
        prompt_group: For content_topic, the topic name (macro, equity, etc.)

    Returns:
        Dependency function that checks for edit permissions
    """
    def check_prompt_edit_permission(user: dict = Depends(get_current_user)) -> dict:
        scopes = user.get("scopes", [])

        # Global admin can edit all prompts
        if is_global_admin(scopes):
            return user

        # For content_topic prompts, topic admin can edit their topic
        if prompt_type == "content_topic" and prompt_group:
            if has_role(scopes, prompt_group, "admin"):
                return user

        # All other cases require global admin
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this prompt"
        )

    return check_prompt_edit_permission


# =============================================================================
# Path-based Topic Permission Dependencies
# =============================================================================
# These dependencies extract the topic from URL path and validate permissions.
# Used with routers that have {topic} in their prefix.
#
# Permission hierarchy (higher includes lower):
#   admin > editor > analyst > reader
#
# Global roles (global:X) grant access to ALL topics for that role level.
# Topic roles ({topic}:X) grant access only to that specific topic.

from typing import Tuple


async def require_reader_for_topic(
    topic: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Tuple[dict, str]:
    """
    Dependency for /api/reader/{topic}/ routes.

    Requires: Any authenticated user. Topic must exist (or be "all" for cross-topic search).

    Args:
        topic: Topic slug from URL path (or "all" for all topics)
        user: Current authenticated user
        db: Database session

    Returns:
        Tuple of (user dict, validated topic slug or "all")

    Raises:
        HTTPException 400: Invalid topic
    """
    # Allow "all" as a special value for cross-topic search
    if topic == "all":
        return user, "all"

    # Validate topic exists
    valid_topics = get_valid_topics(db)
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic: {topic}"
        )

    # Any authenticated user can read - no role check needed
    return user, topic


async def require_analyst_for_topic(
    topic: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Tuple[dict, str]:
    """
    Dependency for /api/analyst/{topic}/ routes.

    Requires: global:analyst+ OR {topic}:analyst+

    Args:
        topic: Topic slug from URL path
        user: Current authenticated user
        db: Database session

    Returns:
        Tuple of (user dict, validated topic slug)

    Raises:
        HTTPException 400: Invalid topic
        HTTPException 403: Insufficient permissions
    """
    scopes = user.get("scopes", [])

    # Validate topic exists
    valid_topics = get_valid_topics(db)
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic: {topic}"
        )

    # Global analyst or higher can access all topics
    if has_global_role_or_higher(scopes, "analyst"):
        return user, topic

    # Check for analyst+ role in specific topic
    if has_any_role_in_group(scopes, topic, ["admin", "editor", "analyst"]):
        return user, topic

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Analyst access required for topic '{topic}'. "
               f"You need 'global:analyst' or '{topic}:analyst' role (or higher)."
    )


async def require_editor_for_topic(
    topic: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Tuple[dict, str]:
    """
    Dependency for /api/editor/{topic}/ routes.

    Requires: global:editor+ OR {topic}:editor+

    Args:
        topic: Topic slug from URL path
        user: Current authenticated user
        db: Database session

    Returns:
        Tuple of (user dict, validated topic slug)

    Raises:
        HTTPException 400: Invalid topic
        HTTPException 403: Insufficient permissions
    """
    scopes = user.get("scopes", [])

    # Validate topic exists
    valid_topics = get_valid_topics(db)
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic: {topic}"
        )

    # Global editor or higher can access all topics
    if has_global_role_or_higher(scopes, "editor"):
        return user, topic

    # Check for editor+ role in specific topic
    if has_any_role_in_group(scopes, topic, ["admin", "editor"]):
        return user, topic

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Editor access required for topic '{topic}'. "
               f"You need 'global:editor' or '{topic}:editor' role (or higher)."
    )


async def require_admin_for_topic(
    topic: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Tuple[dict, str]:
    """
    Dependency for /api/admin/{topic}/ routes.

    Requires: global:admin OR {topic}:admin

    Args:
        topic: Topic slug from URL path
        user: Current authenticated user
        db: Database session

    Returns:
        Tuple of (user dict, validated topic slug)

    Raises:
        HTTPException 400: Invalid topic
        HTTPException 403: Insufficient permissions
    """
    scopes = user.get("scopes", [])

    # Validate topic exists
    valid_topics = get_valid_topics(db)
    if topic not in valid_topics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid topic: {topic}"
        )

    # Global admin can access all topics
    if is_global_admin(scopes):
        return user, topic

    # Check for admin role in specific topic
    if has_role(scopes, topic, "admin"):
        return user, topic

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Admin access required for topic '{topic}'. "
               f"You need 'global:admin' or '{topic}:admin' role."
    )


def validate_article_topic(topic: str, article_id: int, db: Session):
    """
    Validate that an article belongs to the specified topic.

    Used when URL contains both topic and article_id to prevent
    cross-topic access via URL manipulation.

    Args:
        topic: Expected topic slug from URL
        article_id: Article ID from URL
        db: Database session

    Returns:
        The article object if validation passes

    Raises:
        HTTPException 404: Article not found
        HTTPException 400: Article belongs to different topic
    """
    from models import ContentArticle, Topic

    article = db.query(ContentArticle).filter(ContentArticle.id == article_id).first()
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article {article_id} not found"
        )

    # Get the article's topic slug - try topic_id first, fallback to legacy topic field
    if article.topic_id:
        article_topic = db.query(Topic).filter(Topic.id == article.topic_id).first()
        article_topic_slug = article_topic.slug if article_topic else None
    else:
        # Fallback to legacy topic field for articles created before topic_id was set
        article_topic_slug = article.topic

    if article_topic_slug != topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Article {article_id} belongs to topic '{article_topic_slug}', not '{topic}'"
        )

    return article
