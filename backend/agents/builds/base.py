"""Abstract base class for agent builds."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from agents import ChatResponse


class AgentBuildBase(ABC):
    """Abstract base class that all agent builds must implement."""

    @abstractmethod
    def invoke_chat(
        self,
        message: str,
        user_context: Dict[str, Any],
        navigation_context: Dict[str, Any],
        thread_id: Optional[str] = None
    ) -> "ChatResponse":
        """
        Synchronous chat invocation.

        Args:
            message: User's chat message
            user_context: User information (id, email, scopes, roles)
            navigation_context: Current UI state (section, topic, article_id)
            thread_id: Optional thread ID for conversation continuity

        Returns:
            ChatResponse with response text and optional UI actions
        """
        pass

    @abstractmethod
    async def ainvoke_chat(
        self,
        message: str,
        user_context: Dict[str, Any],
        navigation_context: Dict[str, Any],
        thread_id: Optional[str] = None
    ) -> "ChatResponse":
        """
        Async chat invocation.

        Args:
            message: User's chat message
            user_context: User information (id, email, scopes, roles)
            navigation_context: Current UI state (section, topic, article_id)
            thread_id: Optional thread ID for conversation continuity

        Returns:
            ChatResponse with response text and optional UI actions
        """
        pass

    @abstractmethod
    def resume_chat(
        self,
        thread_id: str,
        decision: str,
        user_context: Dict[str, Any]
    ) -> "ChatResponse":
        """
        Resume a paused HITL (Human-in-the-Loop) workflow.

        Args:
            thread_id: Thread ID of the paused workflow
            decision: User's decision (e.g., "approve", "reject")
            user_context: User information for permission validation

        Returns:
            ChatResponse with workflow result
        """
        pass
