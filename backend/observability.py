"""
LangSmith observability configuration for LangChain agents.

This module provides centralized configuration for LangSmith tracing,
including environment setup, metadata helpers, and optional callbacks.

Usage:
    from observability import configure_langsmith, get_run_metadata

    # Initialize LangSmith at startup
    configure_langsmith()

    # Add metadata to agent runs
    metadata = get_run_metadata(user_id=123, agent_type="analyst")
"""

import os
import logging
from typing import Optional, Dict, Any, List
from functools import lru_cache

logger = logging.getLogger("uvicorn")


@lru_cache(maxsize=1)
def is_langsmith_enabled() -> bool:
    """
    Check if LangSmith tracing is enabled.

    Returns:
        True if LANGCHAIN_TRACING_V2 is set to 'true' and API key is configured
    """
    tracing_enabled = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    api_key_set = bool(os.getenv("LANGCHAIN_API_KEY"))
    return tracing_enabled and api_key_set


def configure_langsmith(
    project_name: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> bool:
    """
    Configure LangSmith tracing by setting environment variables.

    LangChain automatically picks up these environment variables when
    making LLM calls, so no explicit callbacks are needed.

    Args:
        project_name: Override the project name (default from LANGCHAIN_PROJECT env var)
        endpoint: Override the LangSmith endpoint (default from LANGCHAIN_ENDPOINT env var)

    Returns:
        True if LangSmith was configured successfully
    """
    # Check if already configured
    if not os.getenv("LANGCHAIN_API_KEY"):
        logger.debug("LangSmith: No API key found, tracing disabled")
        return False

    # Enable tracing v2 (required for LangSmith)
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() != "true":
        logger.debug("LangSmith: LANGCHAIN_TRACING_V2 not enabled")
        return False

    # Set project name if provided
    if project_name:
        os.environ["LANGCHAIN_PROJECT"] = project_name
    elif not os.getenv("LANGCHAIN_PROJECT"):
        os.environ["LANGCHAIN_PROJECT"] = "chatbot-multiagent"

    # Set endpoint if provided (default to EU endpoint)
    if endpoint:
        os.environ["LANGCHAIN_ENDPOINT"] = endpoint
    elif not os.getenv("LANGCHAIN_ENDPOINT"):
        os.environ["LANGCHAIN_ENDPOINT"] = "https://eu.api.smith.langchain.com"

    project = os.getenv("LANGCHAIN_PROJECT")
    logger.info(f"LangSmith tracing enabled for project: {project}")

    return True


def get_run_metadata(
    user_id: Optional[int] = None,
    agent_type: Optional[str] = None,
    topic: Optional[str] = None,
    session_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    **extra_metadata: Any,
) -> Dict[str, Any]:
    """
    Build metadata dict for LangSmith run tracing.

    This metadata is attached to runs and can be used for filtering
    and searching in the LangSmith dashboard.

    Args:
        user_id: User ID making the request
        agent_type: Type of agent (main_chat, analyst, equity, macro, etc.)
        topic: Topic being processed (macro, equity, fixed_income, esg)
        session_id: Session ID for conversation tracking
        workflow_id: Workflow ID for multi-step workflows
        **extra_metadata: Additional metadata key-value pairs

    Returns:
        Dict of metadata for LangSmith
    """
    metadata = {}

    if user_id is not None:
        metadata["user_id"] = user_id

    if agent_type:
        metadata["agent_type"] = agent_type

    if topic:
        metadata["topic"] = topic

    if session_id:
        metadata["session_id"] = session_id

    if workflow_id:
        metadata["workflow_id"] = workflow_id

    # Add extra metadata
    metadata.update(extra_metadata)

    return metadata


def get_run_tags(
    agent_type: Optional[str] = None,
    topic: Optional[str] = None,
    is_streaming: bool = False,
    **extra_tags: bool,
) -> List[str]:
    """
    Build tags list for LangSmith run tracing.

    Tags are used for quick filtering in the LangSmith dashboard.

    Args:
        agent_type: Type of agent
        topic: Topic being processed
        is_streaming: Whether this is a streaming response
        **extra_tags: Additional tags (key=True to include)

    Returns:
        List of tag strings
    """
    tags = []

    if agent_type:
        tags.append(f"agent:{agent_type}")

    if topic:
        tags.append(f"topic:{topic}")

    if is_streaming:
        tags.append("streaming")

    # Add extra tags where value is True
    for tag, include in extra_tags.items():
        if include:
            tags.append(tag)

    return tags


def get_langsmith_config(
    run_name: Optional[str] = None,
    user_id: Optional[int] = None,
    agent_type: Optional[str] = None,
    topic: Optional[str] = None,
    **extra_metadata: Any,
) -> Dict[str, Any]:
    """
    Get a config dict for LangChain runnable with LangSmith settings.

    This can be passed to .invoke(), .stream(), or other runnable methods
    to configure the run.

    Args:
        run_name: Name for the run in LangSmith
        user_id: User ID for metadata
        agent_type: Agent type for metadata and tags
        topic: Topic for metadata and tags
        **extra_metadata: Additional metadata

    Returns:
        Config dict for LangChain runnables

    Example:
        config = get_langsmith_config(
            run_name="Chat with user",
            user_id=123,
            agent_type="main_chat"
        )
        response = llm.invoke(messages, config=config)
    """
    if not is_langsmith_enabled():
        return {}

    config: Dict[str, Any] = {}

    if run_name:
        config["run_name"] = run_name

    # Add metadata
    metadata = get_run_metadata(
        user_id=user_id,
        agent_type=agent_type,
        topic=topic,
        **extra_metadata,
    )
    if metadata:
        config["metadata"] = metadata

    # Add tags
    tags = get_run_tags(agent_type=agent_type, topic=topic)
    if tags:
        config["tags"] = tags

    return config


def log_langsmith_status():
    """Log the current LangSmith configuration status."""
    if is_langsmith_enabled():
        project = os.getenv("LANGCHAIN_PROJECT", "default")
        endpoint = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
        logger.info(f"LangSmith: ENABLED | Project: {project} | Endpoint: {endpoint}")
    else:
        tracing = os.getenv("LANGCHAIN_TRACING_V2", "false")
        has_key = "Yes" if os.getenv("LANGCHAIN_API_KEY") else "No"
        logger.info(f"LangSmith: DISABLED | TRACING_V2: {tracing} | API Key: {has_key}")
