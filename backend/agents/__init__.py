"""Multi-agent system components.

This module provides the public API for the v2 multi-agent system.
The v2 build uses section-based routing with LLM-powered intent classification.

Usage:
    from agents import invoke_chat, UserContext, NavigationContext

    response = invoke_chat(
        message="Hello",
        user_context=user_ctx,
        navigation_context=nav_ctx
    )
"""

import logging

logger = logging.getLogger(__name__)

# Import from v2 build
from agents.builds.v2.state import (
    AgentState,
    UserContext,
    NavigationContext,
    ChatResponse,
    NavigationContextModel,
    UserContextModel,
    create_initial_state,
    create_user_context,
    create_navigation_context,
)
from agents.builds.v2.graph import invoke_chat, get_graph

logger.info("Using v2 agent build (section-based routing)")


# Async invoke - wraps sync invoke for compatibility
async def ainvoke_chat(*args, **kwargs):
    """Async invoke - wraps sync invoke for compatibility."""
    return invoke_chat(*args, **kwargs)


def resume_chat(*args, **kwargs):
    """Resume chat - not implemented in v2."""
    raise NotImplementedError("resume_chat not yet implemented in v2 build")


__all__ = [
    # Core state
    "AgentState",
    "UserContext",
    "NavigationContext",
    "ChatResponse",
    "NavigationContextModel",
    "UserContextModel",
    "create_initial_state",
    "create_user_context",
    "create_navigation_context",
    # Main graph API
    "invoke_chat",
    "ainvoke_chat",
    "resume_chat",
    "get_graph",
]
