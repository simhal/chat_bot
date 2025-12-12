"""Redis-backed conversation memory for LangGraph agents."""

from langchain_community.chat_message_histories import RedisChatMessageHistory
from redis_client import redis_settings


def get_redis_url() -> str:
    """Get Redis URL from settings."""
    return redis_settings.redis_url


def create_conversation_memory(user_id: int) -> RedisChatMessageHistory:
    """
    Create a Redis-backed message history for per-user isolation.

    Args:
        user_id: User ID for conversation context isolation

    Returns:
        RedisChatMessageHistory instance backed by Redis
    """
    # Create Redis-backed message history with user-specific session
    session_id = f"user_{user_id}"

    message_history = RedisChatMessageHistory(
        session_id=session_id,
        url=get_redis_url(),
        ttl=86400  # 24 hours TTL
    )

    return message_history


def clear_conversation_history(user_id: int) -> None:
    """
    Clear conversation history for a specific user.

    Args:
        user_id: User ID whose conversation history to clear
    """
    session_id = f"user_{user_id}"
    message_history = RedisChatMessageHistory(
        session_id=session_id,
        url=get_redis_url()
    )
    message_history.clear()
