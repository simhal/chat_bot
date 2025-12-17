"""
Shared dependency functions for FastAPI endpoints.
This module provides reusable dependencies that can be imported by all API routers.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth import verify_access_token
from typing import List

security = HTTPBearer()


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
    """
    Check if user has global admin role.
    """
    return has_role(scopes, "global", "admin")


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
        topic: Topic name (macro, equity, fixed_income, esg)

    Returns:
        Dependency function that checks for appropriate permissions
    """
    # Valid topic names
    valid_topics = ["macro", "equity", "fixed_income", "esg"]

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

        # Validate topic
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
        topic: Topic name (macro, equity, fixed_income, esg)

    Returns:
        Dependency function that checks for editor permissions
    """
    valid_topics = ["macro", "equity", "fixed_income", "esg"]

    def check_editor_permission(user: dict = Depends(get_current_user)) -> dict:
        """
        Check if user has editor/admin permission for the topic.
        """
        scopes = user.get("scopes", [])

        # Global admin can access all content
        if is_global_admin(scopes):
            return user

        # Validate topic
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
