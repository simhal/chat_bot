"""
Shared dependency functions for FastAPI endpoints.
This module provides reusable dependencies that can be imported by all API routers.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from auth import verify_access_token

security = HTTPBearer()


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
    Dependency to require admin scope.

    Args:
        user: Current authenticated user from get_current_user dependency

    Returns:
        User dict if user has admin scope

    Raises:
        HTTPException: If user does not have admin scope
    """
    scopes = user.get("scopes", [])

    if "admin" not in scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return user


def require_analyst(topic: str):
    """
    Dependency factory to require analyst scope for a specific topic.

    Args:
        topic: Topic name (macro, equity, fixed_income, esg)

    Returns:
        Dependency function that checks for appropriate analyst scope
    """
    # Map topics to required analyst groups
    topic_to_group = {
        "macro": "macro_analyst",
        "equity": "equity_analyst",
        "fixed_income": "fi_analyst",
        "esg": "esg_analyst"
    }

    def check_analyst_permission(user: dict = Depends(get_current_user)) -> dict:
        """
        Check if user has analyst permission for the topic.

        Args:
            user: Current authenticated user

        Returns:
            User dict if user has required analyst scope or admin scope

        Raises:
            HTTPException: If user does not have required analyst scope
        """
        scopes = user.get("scopes", [])

        # Admin can edit all content
        if "admin" in scopes:
            return user

        # Check for specific analyst group
        required_group = topic_to_group.get(topic)
        if not required_group:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid topic: {topic}"
            )

        if required_group not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Analyst access required. You need '{required_group}' scope to edit {topic} content."
            )

        return user

    return check_analyst_permission
