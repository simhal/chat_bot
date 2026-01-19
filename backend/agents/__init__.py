"""Multi-agent system components.

This module provides the public API for the multi-agent system.
The actual implementation is selected based on AGENT_BUILD environment variable:
- v1 (default): Uses the original agent implementation from agents/
- v2: Uses the new section-based routing from agents/builds/v2/

Usage:
    from agents import invoke_chat, UserContext, NavigationContext

    response = invoke_chat(
        message="Hello",
        user_context=user_ctx,
        navigation_context=nav_ctx
    )
"""

import os
import logging

logger = logging.getLogger(__name__)

# Determine which build to use
AGENT_BUILD = os.getenv("AGENT_BUILD", "v1")
logger.info(f"Agent build: {AGENT_BUILD}")

if AGENT_BUILD == "v2":
    # Use v2 build with section-based routing
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

    # Async and resume not yet implemented in v2
    async def ainvoke_chat(*args, **kwargs):
        """Async invoke - not implemented in v2, falls back to sync."""
        return invoke_chat(*args, **kwargs)

    def resume_chat(*args, **kwargs):
        """Resume chat - not implemented in v2."""
        raise NotImplementedError("resume_chat not yet implemented in v2 build")

    logger.info("Using v2 agent build (section-based routing)")

else:
    # Use v1 build (original implementation)
    from agents.state import (
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
    from agents.graph import invoke_chat, ainvoke_chat, resume_chat, get_graph

    logger.info("Using v1 agent build (original implementation)")

# These are still from the root level for both builds
from agents.base_agent import BaseSpecialistAgent
from agents.router_agent import RouterAgent
from agents.content_agent import ContentAgent
from agents.graph_builder import MultiAgentGraph
from agents.resource_query_agent import (
    ResourceQueryAgent,
    TextResourceQueryAgent,
    TableResourceQueryAgent
)
from agents.resource_processing_agent import ResourceProcessingAgent

# Analyst agents
from agents.analyst_agent import AnalystAgent
from agents.article_query_agent import ArticleQueryAgent
from agents.web_search_agent import WebSearchAgent
from agents.data_download_agent import DataDownloadAgent
from agents.editor_sub_agent import EditorSubAgent

# Specialized analyst subclasses
from agents.specialist_analysts import (
    EquityAnalystAgent,
    MacroAnalystAgent,
    FixedIncomeAnalystAgent,
    ESGAnalystAgent,
    get_analyst_for_topic,
)

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
    # Base components
    "BaseSpecialistAgent",
    "RouterAgent",
    "ContentAgent",
    "MultiAgentGraph",
    # Resource agents
    "ResourceQueryAgent",
    "TextResourceQueryAgent",
    "TableResourceQueryAgent",
    "ResourceProcessingAgent",
    # Base analyst (for new/custom topics)
    "AnalystAgent",
    # Specialized analysts (with topic-specific customizations)
    "EquityAnalystAgent",
    "MacroAnalystAgent",
    "FixedIncomeAnalystAgent",
    "ESGAnalystAgent",
    "get_analyst_for_topic",
    # Sub-agents
    "ArticleQueryAgent",
    "WebSearchAgent",
    "DataDownloadAgent",
    "EditorSubAgent",
]
