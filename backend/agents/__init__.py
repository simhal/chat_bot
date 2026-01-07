"""Multi-agent system components."""

from agents.state import AgentState, UserContext, WorkflowContext
from agents.base_agent import BaseSpecialistAgent
from agents.router_agent import RouterAgent
from agents.main_chat_agent import MainChatAgent
from agents.content_agent import ContentAgent
from agents.graph_builder import MultiAgentGraph
from agents.resource_query_agent import (
    ResourceQueryAgent,
    TextResourceQueryAgent,
    TableResourceQueryAgent
)
from agents.resource_processing_agent import ResourceProcessingAgent

# New multi-agent architecture
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
    "WorkflowContext",
    # Base components
    "BaseSpecialistAgent",
    "RouterAgent",
    "MainChatAgent",
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
