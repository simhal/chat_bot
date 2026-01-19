"""
Permission-aware tool registry for multi-agent system.

This module provides a central registry for all agent tools with permission
metadata. Tools are filtered at runtime based on user scopes, ensuring
users only have access to tools appropriate for their role.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, TYPE_CHECKING
from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from agents import UserContext


@dataclass
class ToolPermission:
    """
    Permission metadata for a registered tool.

    Attributes:
        required_role: Minimum role required (admin > analyst > editor > reader)
        topic_scoped: If True, user must have role for the specific topic
        global_admin_override: If True, global:admin can always access
        requires_hitl: If True, tool triggers human-in-the-loop workflow
        description: Human-readable description of permission requirements
    """
    required_role: str = "reader"
    topic_scoped: bool = False
    global_admin_override: bool = True
    requires_hitl: bool = False
    description: str = ""


# Role hierarchy levels for comparison
ROLE_LEVELS: Dict[str, int] = {
    "admin": 4,
    "analyst": 3,
    "editor": 2,
    "reader": 1,
}


class ToolRegistry:
    """
    Singleton registry for permission-aware tool management.

    Provides:
    - Tool registration with permission metadata
    - Runtime filtering based on user scopes
    - Tool lookup by name
    - HITL tool identification
    """

    _instance: Optional["ToolRegistry"] = None
    _initialized: bool = False

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not ToolRegistry._initialized:
            self._tools: Dict[str, BaseTool] = {}
            self._permissions: Dict[str, ToolPermission] = {}
            ToolRegistry._initialized = True

    @classmethod
    def instance(cls) -> "ToolRegistry":
        """Get the singleton registry instance."""
        return cls()

    @classmethod
    def reset(cls) -> None:
        """Reset the registry (for testing)."""
        cls._instance = None
        cls._initialized = False

    def register(
        self,
        name: str,
        tool: BaseTool,
        permission: ToolPermission,
    ) -> None:
        """
        Register a tool with permission metadata.

        Args:
            name: Unique tool name
            tool: LangChain BaseTool instance
            permission: Permission requirements for the tool
        """
        self._tools[name] = tool
        self._permissions[name] = permission

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_permission(self, name: str) -> Optional[ToolPermission]:
        """Get permission metadata for a tool."""
        return self._permissions.get(name)

    def get_all_tools(self) -> Dict[str, BaseTool]:
        """Get all registered tools."""
        return self._tools.copy()

    def get_all_permissions(self) -> Dict[str, ToolPermission]:
        """Get all permission metadata."""
        return self._permissions.copy()

    def get_tools_for_user(
        self,
        user_scopes: List[str],
        topic: Optional[str] = None,
    ) -> Dict[str, BaseTool]:
        """
        Get tools filtered by user permissions.

        Args:
            user_scopes: List of user's permission scopes (e.g., ["macro:analyst"])
            topic: Optional topic to filter topic-scoped tools

        Returns:
            Dict of tool name -> BaseTool for accessible tools
        """
        accessible_tools = {}

        for name, tool in self._tools.items():
            permission = self._permissions.get(name)
            if permission and self._check_permission(user_scopes, permission, topic):
                accessible_tools[name] = tool

        return accessible_tools

    def get_tool_names_for_user(
        self,
        user_scopes: List[str],
        topic: Optional[str] = None,
    ) -> List[str]:
        """
        Get list of accessible tool names for a user.

        Args:
            user_scopes: List of user's permission scopes
            topic: Optional topic to filter topic-scoped tools

        Returns:
            List of accessible tool names
        """
        return list(self.get_tools_for_user(user_scopes, topic).keys())

    def get_hitl_tools(self) -> List[str]:
        """Get names of tools that require human-in-the-loop."""
        return [
            name for name, perm in self._permissions.items()
            if perm.requires_hitl
        ]

    def is_hitl_tool(self, name: str) -> bool:
        """Check if a tool requires human-in-the-loop."""
        permission = self._permissions.get(name)
        return permission.requires_hitl if permission else False

    def _check_permission(
        self,
        user_scopes: List[str],
        permission: ToolPermission,
        topic: Optional[str] = None,
    ) -> bool:
        """
        Check if user has permission to access a tool.

        Args:
            user_scopes: List of user's permission scopes
            permission: Tool's permission requirements
            topic: Optional topic for topic-scoped checks

        Returns:
            True if user has access, False otherwise
        """
        required_level = ROLE_LEVELS.get(permission.required_role, 0)

        # Check for global admin override
        if permission.global_admin_override and "global:admin" in user_scopes:
            return True

        for scope in user_scopes:
            if ":" not in scope:
                continue

            scope_group, scope_role = scope.split(":", 1)
            scope_level = ROLE_LEVELS.get(scope_role, 0)

            # Global scope applies to all topics
            if scope_group == "global" and scope_level >= required_level:
                return True

            # Topic-scoped tools require matching topic
            if permission.topic_scoped:
                if topic and scope_group == topic and scope_level >= required_level:
                    return True
            else:
                # Non-topic-scoped tools accept any matching role level
                if scope_level >= required_level:
                    return True

        return False

    def check_tool_access(
        self,
        tool_name: str,
        user_scopes: List[str],
        topic: Optional[str] = None,
    ) -> bool:
        """
        Check if a user can access a specific tool.

        Args:
            tool_name: Name of the tool to check
            user_scopes: List of user's permission scopes
            topic: Optional topic for topic-scoped checks

        Returns:
            True if user has access, False otherwise
        """
        permission = self._permissions.get(tool_name)
        if not permission:
            return False
        return self._check_permission(user_scopes, permission, topic)


def check_permission(
    user_scopes: List[str],
    required_role: str,
    topic: Optional[str] = None,
    global_admin_override: bool = True,
) -> bool:
    """
    Standalone permission check function.

    Args:
        user_scopes: List of user's permission scopes
        required_role: Required role level
        topic: Optional topic for topic-scoped checks
        global_admin_override: Whether global:admin bypasses checks

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
            # No topic specified, any matching role works
            if scope_level >= required_level:
                return True

    return False


def get_user_role_for_topic(
    user_scopes: List[str],
    topic: str,
) -> Optional[str]:
    """
    Get user's role for a specific topic.

    Args:
        user_scopes: List of user's permission scopes
        topic: Topic to check

    Returns:
        Role name or None if no access
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
