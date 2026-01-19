"""V1 Agent Build - Original multi-agent system with intent-based routing."""

from typing import Dict, Any, Optional

from agents.builds import register_build
from agents.builds.base import AgentBuildBase
from .graph import invoke_chat as _invoke_chat
from .graph import ainvoke_chat as _ainvoke_chat
from .graph import resume_chat as _resume_chat
from .state import (
    ChatResponse,
    create_user_context,
    create_navigation_context,
    UserContextModel,
    NavigationContextModel,
)


@register_build("v1")
class V1Build(AgentBuildBase):
    """
    V1 Agent Build - Intent-based routing with specialized handler nodes.

    Features:
    - LLM-powered intent classification
    - Specialized nodes: ui_action, content_generation, editor_workflow, general_chat
    - HITL support for destructive actions
    - Redis checkpointing for workflow persistence
    """

    def invoke_chat(
        self,
        message: str,
        user_context: Dict[str, Any],
        navigation_context: Dict[str, Any],
        thread_id: Optional[str] = None
    ) -> ChatResponse:
        """Synchronous chat invocation."""
        return _invoke_chat(message, user_context, navigation_context, thread_id)

    async def ainvoke_chat(
        self,
        message: str,
        user_context: Dict[str, Any],
        navigation_context: Dict[str, Any],
        thread_id: Optional[str] = None
    ) -> ChatResponse:
        """Async chat invocation."""
        return await _ainvoke_chat(message, user_context, navigation_context, thread_id)

    def resume_chat(
        self,
        thread_id: str,
        decision: str,
        user_context: Dict[str, Any]
    ) -> ChatResponse:
        """Resume HITL workflow."""
        return _resume_chat(thread_id, decision, user_context)


# Re-export for convenience
__all__ = [
    "V1Build",
    "ChatResponse",
    "create_user_context",
    "create_navigation_context",
    "UserContextModel",
    "NavigationContextModel",
]
