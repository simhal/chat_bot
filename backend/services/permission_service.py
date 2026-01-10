"""
Permission service for role-based access control.

This module provides permission checking utilities used throughout the
application to enforce role-based access to resources and operations.
"""

from typing import List, Optional, Dict

# Role hierarchy levels
ROLE_LEVELS: Dict[str, int] = {
    "admin": 4,
    "analyst": 3,
    "editor": 2,
    "reader": 1,
}


class PermissionService:
    """
    Service for permission checking and role-based access control.

    Provides methods to check user permissions against required roles,
    with support for topic-scoped permissions and global admin override.
    """

    @staticmethod
    def check_permission(
        user_scopes: List[str],
        required_role: str,
        topic: Optional[str] = None,
        global_admin_override: bool = True,
    ) -> bool:
        """
        Check if user has the required permission.

        Args:
            user_scopes: List of user's permission scopes (e.g., ["macro:analyst"])
            required_role: Required role level (admin, analyst, editor, reader)
            topic: Optional topic for topic-scoped checks
            global_admin_override: Whether global:admin bypasses all checks

        Returns:
            True if user has required permission
        """
        required_level = ROLE_LEVELS.get(required_role, 0)

        # Check for global admin override
        if global_admin_override and "global:admin" in user_scopes:
            return True

        for scope in user_scopes:
            if ":" not in scope:
                continue

            scope_group, scope_role = scope.split(":", 1)
            scope_level = ROLE_LEVELS.get(scope_role, 0)

            # Global scope applies to all topics
            if scope_group == "global" and scope_level >= required_level:
                return True

            # Topic-specific check
            if topic:
                if scope_group == topic and scope_level >= required_level:
                    return True
            else:
                # No topic specified, any matching role level works
                if scope_level >= required_level:
                    return True

        return False

    @staticmethod
    def get_user_role_for_topic(
        user_scopes: List[str],
        topic: str,
    ) -> Optional[str]:
        """
        Get user's effective role for a specific topic.

        Args:
            user_scopes: List of user's permission scopes
            topic: Topic to check

        Returns:
            Role name (admin, analyst, editor, reader) or None if no access
        """
        best_role: Optional[str] = None
        best_level = 0

        for scope in user_scopes:
            if ":" not in scope:
                continue

            scope_group, scope_role = scope.split(":", 1)
            scope_level = ROLE_LEVELS.get(scope_role, 0)

            # Global scope applies to all topics
            if scope_group == "global" and scope_level > best_level:
                best_role = scope_role
                best_level = scope_level

            # Topic-specific scope
            if scope_group == topic and scope_level > best_level:
                best_role = scope_role
                best_level = scope_level

        return best_role

    @staticmethod
    def get_highest_role(user_scopes: List[str]) -> str:
        """
        Get user's highest role across all topics.

        Args:
            user_scopes: List of user's permission scopes

        Returns:
            Highest role name, defaults to "reader"
        """
        highest_role = "reader"
        highest_level = ROLE_LEVELS.get("reader", 1)

        for scope in user_scopes:
            if ":" not in scope:
                continue

            _, scope_role = scope.split(":", 1)
            scope_level = ROLE_LEVELS.get(scope_role, 0)

            if scope_level > highest_level:
                highest_role = scope_role
                highest_level = scope_level

        return highest_role

    @staticmethod
    def get_accessible_topics(
        user_scopes: List[str],
        required_role: str = "reader",
    ) -> List[str]:
        """
        Get list of topics user can access at the EXACT specified role level.

        This uses explicit role matching - a user must have the exact role
        (e.g., {topic}:reader or global:reader) to access a topic at that level.
        Higher roles do NOT automatically grant lower role access.

        Args:
            user_scopes: List of user's permission scopes
            required_role: Exact role required (reader, analyst, editor, admin)

        Returns:
            List of accessible topic slugs, or ["*"] for global access
        """
        accessible_topics = set()

        for scope in user_scopes:
            if ":" not in scope:
                continue

            scope_group, scope_role = scope.split(":", 1)

            # Exact role match required (no hierarchy)
            if scope_role == required_role:
                if scope_group == "global":
                    # Global access at this role level
                    return ["*"]  # Indicates all topics
                else:
                    accessible_topics.add(scope_group)

        return list(accessible_topics)

    @staticmethod
    def is_global_admin(user_scopes: List[str]) -> bool:
        """Check if user is a global admin."""
        return "global:admin" in user_scopes

    @staticmethod
    def can_create_content(user_scopes: List[str], topic: str) -> bool:
        """Check if user can create content for a topic (analyst+ required)."""
        return PermissionService.check_permission(
            user_scopes, "analyst", topic=topic
        )

    @staticmethod
    def can_edit_content(user_scopes: List[str], topic: str) -> bool:
        """Check if user can edit content for a topic (editor+ required)."""
        return PermissionService.check_permission(
            user_scopes, "editor", topic=topic
        )

    @staticmethod
    def can_publish_content(user_scopes: List[str], topic: str) -> bool:
        """Check if user can publish content for a topic (editor+ required)."""
        return PermissionService.check_permission(
            user_scopes, "editor", topic=topic
        )

    @staticmethod
    def can_admin_topic(user_scopes: List[str], topic: str) -> bool:
        """Check if user has admin access to a topic."""
        return PermissionService.check_permission(
            user_scopes, "admin", topic=topic
        )
