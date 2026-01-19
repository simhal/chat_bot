"""Shared utilities and sub-agents used across all builds."""

from .permission_utils import (
    check_topic_permission,
    get_topics_for_role,
    get_user_role_for_topic,
    is_global_admin,
    filter_topics_by_permission,
    validate_article_access,
)
from .topic_manager import (
    TopicManager,
    TopicConfig,
    get_available_topics,
    get_topic_config,
    get_all_topics,
    get_visible_topics,
    get_ai_accessible_topics,
    get_ai_accessible_topic_slugs,
    infer_topic,
    is_valid_topic,
    refresh_cache,
    get_topic_manager,
)
from .analyst_agent import AnalystAgent
from .article_query_agent import ArticleQueryAgent
from .content_agent import ContentAgent
from .data_download_agent import DataDownloadAgent
from .editor_sub_agent import EditorSubAgent
from .resource_processing_agent import ResourceProcessingAgent
from .resource_query_agent import ResourceQueryAgent
from .web_search_agent import WebSearchAgent

__all__ = [
    # Permission utilities
    "check_topic_permission",
    "get_topics_for_role",
    "get_user_role_for_topic",
    "is_global_admin",
    "filter_topics_by_permission",
    "validate_article_access",
    # Topic manager
    "TopicManager",
    "TopicConfig",
    "get_available_topics",
    "get_topic_config",
    "get_all_topics",
    "get_visible_topics",
    "get_ai_accessible_topics",
    "get_ai_accessible_topic_slugs",
    "infer_topic",
    "is_valid_topic",
    "refresh_cache",
    "get_topic_manager",
    # Sub-agents
    "AnalystAgent",
    "ArticleQueryAgent",
    "ContentAgent",
    "DataDownloadAgent",
    "EditorSubAgent",
    "ResourceProcessingAgent",
    "ResourceQueryAgent",
    "WebSearchAgent",
]
