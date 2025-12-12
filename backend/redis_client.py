import redis
from pydantic_settings import BaseSettings
from typing import Optional
import json


class RedisSettings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


redis_settings = RedisSettings()

# Create Redis client
redis_client = redis.from_url(
    redis_settings.redis_url,
    decode_responses=True
)


class TokenCache:
    """Helper class for managing token cache in Redis."""

    ACCESS_TOKEN_PREFIX = "access_token:"
    REFRESH_TOKEN_PREFIX = "refresh_token:"
    ACCESS_TOKEN_TTL = 86400  # 24 hours in seconds
    REFRESH_TOKEN_TTL = 604800  # 7 days in seconds

    @staticmethod
    def store_access_token(token_id: str, user_data: dict, ttl: int = ACCESS_TOKEN_TTL) -> None:
        """Store access token in Redis with user data."""
        key = f"{TokenCache.ACCESS_TOKEN_PREFIX}{token_id}"
        redis_client.setex(key, ttl, json.dumps(user_data))

    @staticmethod
    def get_access_token(token_id: str) -> Optional[dict]:
        """Retrieve access token data from Redis."""
        key = f"{TokenCache.ACCESS_TOKEN_PREFIX}{token_id}"
        data = redis_client.get(key)
        return json.loads(data) if data else None

    @staticmethod
    def delete_access_token(token_id: str) -> None:
        """Delete access token from Redis."""
        key = f"{TokenCache.ACCESS_TOKEN_PREFIX}{token_id}"
        redis_client.delete(key)

    @staticmethod
    def store_refresh_token(token_id: str, user_id: int, ttl: int = REFRESH_TOKEN_TTL) -> None:
        """Store refresh token in Redis."""
        key = f"{TokenCache.REFRESH_TOKEN_PREFIX}{token_id}"
        redis_client.setex(key, ttl, str(user_id))

    @staticmethod
    def get_refresh_token(token_id: str) -> Optional[int]:
        """Retrieve user_id from refresh token."""
        key = f"{TokenCache.REFRESH_TOKEN_PREFIX}{token_id}"
        user_id = redis_client.get(key)
        return int(user_id) if user_id else None

    @staticmethod
    def delete_refresh_token(token_id: str) -> None:
        """Delete refresh token from Redis."""
        key = f"{TokenCache.REFRESH_TOKEN_PREFIX}{token_id}"
        redis_client.delete(key)
