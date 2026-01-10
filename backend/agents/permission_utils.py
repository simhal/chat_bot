"""
Permission utilities for topic-based access control.

This module provides consistent permission checking across all agents and nodes,
enforcing that users can only access topics they have explicit permissions for.

Permission Model:
- Scopes are in format: {topic}:{role} or global:{role}
- Examples: "macro:analyst", "equity:editor", "global:admin"
- Roles: admin > analyst > editor > reader
- global:admin has access to all topics
- {topic}:{role} grants access to only that specific topic
"""

from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# Role hierarchy - higher number = more permissions
ROLE_HIERARCHY = {
    "admin": 4,
    "analyst": 3,
    "editor": 2,
    "reader": 1
}


def check_topic_permission(
    topic: str,
    required_role: str,
    user_context: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Check if user has required role for a specific topic.

    Args:
        topic: The topic slug to check (e.g., "macro", "equity")
        required_role: Minimum role required ("reader", "editor", "analyst", "admin")
        user_context: User context from JWT with scopes and topic_roles

    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    scopes = user_context.get("scopes", [])
    topic_roles = user_context.get("topic_roles", {})

    required_level = ROLE_HIERARCHY.get(required_role, 1)

    # Global admin has access to everything
    if "global:admin" in scopes:
        return True, None

    # Check topic-specific permissions
    topic_role = topic_roles.get(topic)

    if topic_role:
        user_level = ROLE_HIERARCHY.get(topic_role, 0)
        if user_level >= required_level:
            return True, None

    # Also check scopes directly in case topic_roles wasn't fully populated
    for scope in scopes:
        if ":" in scope:
            scope_topic, scope_role = scope.split(":", 1)
            if scope_topic == topic:
                user_level = ROLE_HIERARCHY.get(scope_role, 0)
                if user_level >= required_level:
                    return True, None

    # Access denied - build helpful message
    available_topics = get_topics_for_role(user_context, required_role)

    if available_topics:
        return False, (
            f"You don't have {required_role} access for **{topic}**. "
            f"You have access to: {', '.join(available_topics)}"
        )

    return False, (
        f"You need {required_role} access for **{topic}**. "
        "Contact an administrator to request access."
    )


def get_topics_for_role(user_context: Dict[str, Any], min_role: str) -> List[str]:
    """
    Get list of topics where user has at least the specified role.

    Args:
        user_context: User context with scopes and topic_roles
        min_role: Minimum role required

    Returns:
        List of topic slugs where user has sufficient permission
    """
    topic_roles = user_context.get("topic_roles", {})
    scopes = user_context.get("scopes", [])
    min_level = ROLE_HIERARCHY.get(min_role, 1)

    # Global admin has access to all topics - load dynamically from database
    if "global:admin" in scopes:
        from database import SessionLocal
        from models import Topic
        db = SessionLocal()
        try:
            all_topics = db.query(Topic).filter(Topic.active == True).all()
            return [t.slug for t in all_topics]
        finally:
            db.close()

    topics = set()

    # Check topic_roles
    for topic, role in topic_roles.items():
        if ROLE_HIERARCHY.get(role, 0) >= min_level:
            topics.add(topic)

    # Also check scopes directly
    for scope in scopes:
        if ":" in scope:
            scope_topic, scope_role = scope.split(":", 1)
            if scope_topic != "global":
                if ROLE_HIERARCHY.get(scope_role, 0) >= min_level:
                    topics.add(scope_topic)

    return sorted(list(topics))


def get_user_role_for_topic(user_context: Dict[str, Any], topic: str) -> str:
    """
    Get user's role for a specific topic.

    Args:
        user_context: User context with scopes and topic_roles
        topic: Topic slug to check

    Returns:
        User's role for the topic ("admin", "analyst", "editor", or "reader")
    """
    scopes = user_context.get("scopes", [])
    topic_roles = user_context.get("topic_roles", {})

    # Global admin
    if "global:admin" in scopes:
        return "admin"

    # Check topic_roles
    if topic in topic_roles:
        return topic_roles[topic]

    # Check scopes directly
    for scope in scopes:
        if ":" in scope:
            scope_topic, scope_role = scope.split(":", 1)
            if scope_topic == topic:
                return scope_role

    return "reader"


def is_global_admin(user_context: Dict[str, Any]) -> bool:
    """Check if user is a global admin."""
    scopes = user_context.get("scopes", [])
    return "global:admin" in scopes


def filter_topics_by_permission(
    topics: List[str],
    required_role: str,
    user_context: Dict[str, Any]
) -> List[str]:
    """
    Filter a list of topics to only those the user has permission for.

    Args:
        topics: List of topic slugs to filter
        required_role: Minimum role required
        user_context: User context with scopes

    Returns:
        Filtered list of topics user has access to
    """
    allowed_topics = get_topics_for_role(user_context, required_role)

    # Global admin gets all topics
    if is_global_admin(user_context):
        return topics

    return [t for t in topics if t in allowed_topics]


def get_available_tools_for_user(
    all_tools: List[str],
    user_context: Dict[str, Any],
    current_topic: Optional[str] = None
) -> List[str]:
    """
    Filter available tools based on user's permissions.

    This integrates with the tool registry to filter tools based on
    the user's scopes and current topic context.

    Args:
        all_tools: List of all tool names
        user_context: User context with scopes
        current_topic: Current topic context (if any)

    Returns:
        List of tools the user can access
    """
    # This would integrate with tool_registry.py
    # For now, return all tools as placeholder
    # The actual filtering happens in tool_registry.filter_tools_for_user()

    logger.debug(f"Filtering {len(all_tools)} tools for user")
    return all_tools


def build_permission_context_for_prompt(user_context: Dict[str, Any]) -> str:
    """
    Build a text description of user's permissions for LLM prompts.

    This helps the LLM understand what actions are available to the user.

    Args:
        user_context: User context with scopes and roles

    Returns:
        Text description of permissions
    """
    scopes = user_context.get("scopes", [])
    topic_roles = user_context.get("topic_roles", {})
    name = user_context.get("name", "User")

    lines = [f"User: {name}"]

    if "global:admin" in scopes:
        lines.append("Role: Global Administrator (full access)")
        return "\n".join(lines)

    lines.append("Topic permissions:")
    for topic, role in sorted(topic_roles.items()):
        lines.append(f"  - {topic}: {role}")

    if not topic_roles:
        lines.append("  - Reader access only (no topic-specific permissions)")

    return "\n".join(lines)


def get_accessible_article_statuses(user_role: str) -> List[str]:
    """
    Get article statuses accessible to a user role.

    Access rules:
    - reader: Only published articles
    - analyst: Draft or editor articles (their workflow states)
    - editor: Only articles with status "editor" (awaiting review)
    - admin: All article statuses

    Args:
        user_role: The user's role (reader, analyst, editor, admin)

    Returns:
        List of article status strings the user can access
    """
    role = user_role.lower() if user_role else "reader"

    if role == "admin":
        return ["draft", "editor", "pending_approval", "published", "deactivated"]
    elif role == "analyst":
        return ["draft", "editor"]
    elif role == "editor":
        return ["editor", "pending_approval"]
    else:  # reader or default
        return ["published"]


def validate_article_access(
    article_id: int,
    user_context: Dict[str, Any],
    db,
    topic: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Validate user can access an article based on role and article status.

    This function:
    1. Checks if the article exists
    2. Verifies the user has topic permission
    3. Validates article status matches the user's role-based access

    Args:
        article_id: The article ID to validate
        user_context: User context with scopes and topic_roles
        db: Database session
        topic: Optional topic to restrict to (if None, uses article's topic)

    Returns:
        Tuple of:
        - allowed (bool): Whether user can access the article
        - error_message (str|None): Error message if denied
        - article_info (dict|None): Article info for context update if allowed
    """
    from models import ContentArticle

    # Query the article
    article = db.query(ContentArticle).filter(ContentArticle.id == article_id).first()

    if not article:
        return False, f"Article #{article_id} not found.", None

    article_topic = article.topic
    # Handle enum properly - get .value if it's an enum
    raw_status = article.status
    if hasattr(raw_status, 'value'):
        article_status = raw_status.value.lower()
    elif raw_status:
        article_status = str(raw_status).lower()
    else:
        article_status = "draft"
    logger.debug(f"validate_article_access: article_id={article_id}, raw_status={raw_status}, article_status={article_status}")

    # If topic restriction provided, validate it matches
    if topic and article_topic != topic:
        return False, f"Article #{article_id} belongs to topic '{article_topic}', not '{topic}'.", None

    # Get user's role for this article's topic
    user_role = get_user_role_for_topic(user_context, article_topic)

    # Check topic permission (at least reader)
    allowed, error = check_topic_permission(article_topic, "reader", user_context)
    if not allowed:
        return False, error, None

    # Get accessible statuses for this role
    accessible_statuses = get_accessible_article_statuses(user_role)

    # Check if article status is accessible
    if article_status not in accessible_statuses:
        role_name = user_role.capitalize()
        status_list = ", ".join(accessible_statuses)
        return False, (
            f"As a **{role_name}** for '{article_topic}', you can only access articles with status: {status_list}. "
            f"Article #{article_id} has status '{article_status}'."
        ), None

    # Build article info for context update
    article_info = {
        "id": article.id,
        "topic": article_topic,
        "status": article_status,
        "headline": article.headline,
        "keywords": article.keywords,
        "author": article.author,
        "created_at": article.created_at.isoformat() if article.created_at else None,
        "updated_at": article.updated_at.isoformat() if article.updated_at else None
    }

    logger.debug(f"Article #{article_id} access validated for user with role '{user_role}'")
    return True, None, article_info
