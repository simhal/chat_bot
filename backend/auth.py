from datetime import datetime, timedelta
from jose import jwt, JWTError
from pydantic_settings import BaseSettings
from typing import Optional, List
import secrets
from models import User
from redis_client import TokenCache


class AuthSettings(BaseSettings):
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours
    refresh_token_expire_days: int = 7

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


auth_settings = AuthSettings()


def create_access_token(user: User, groups: List[str]) -> tuple[str, str]:
    """
    Create a JWT access token with user information and groups/scopes.
    Returns (token, token_id) where token_id is stored in Redis.
    """
    token_id = secrets.token_urlsafe(32)

    # Calculate expiration
    expire = datetime.utcnow() + timedelta(minutes=auth_settings.access_token_expire_minutes)

    # Prepare token data
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "surname": user.surname,
        "picture": user.picture,
        "scopes": groups,  # OAuth2 standard field for permissions/groups
        "jti": token_id,  # JWT ID for Redis cache lookup
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    }

    # Create JWT token
    encoded_jwt = jwt.encode(token_data, auth_settings.jwt_secret_key, algorithm=auth_settings.jwt_algorithm)

    # Store in Redis cache for quick validation
    cache_data = {
        "user_id": user.id,
        "email": user.email,
        "scopes": groups
    }
    TokenCache.store_access_token(token_id, cache_data)

    return encoded_jwt, token_id


def create_refresh_token(user_id: int) -> str:
    """
    Create a refresh token for renewing access tokens.
    Returns the refresh token.
    """
    token_id = secrets.token_urlsafe(32)

    # Calculate expiration
    expire = datetime.utcnow() + timedelta(days=auth_settings.refresh_token_expire_days)

    # Prepare token data
    token_data = {
        "sub": str(user_id),
        "jti": token_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    }

    # Create JWT token
    encoded_jwt = jwt.encode(token_data, auth_settings.jwt_secret_key, algorithm=auth_settings.jwt_algorithm)

    # Store in Redis cache
    TokenCache.store_refresh_token(token_id, user_id)

    return encoded_jwt


def verify_access_token(token: str) -> Optional[dict]:
    """
    Verify and decode access token.
    First checks Redis cache, then validates JWT signature.
    Returns token payload if valid, None otherwise.
    """
    try:
        # Decode the token (this validates signature and expiration)
        payload = jwt.decode(
            token,
            auth_settings.jwt_secret_key,
            algorithms=[auth_settings.jwt_algorithm]
        )

        # Verify it's an access token
        if payload.get("type") != "access":
            return None

        # Check if token exists in Redis cache
        token_id = payload.get("jti")
        if not token_id:
            return None

        cached_data = TokenCache.get_access_token(token_id)
        if not cached_data:
            # Token has been invalidated or expired in cache
            return None

        return payload

    except JWTError:
        return None


def verify_refresh_token(token: str) -> Optional[int]:
    """
    Verify refresh token and return user_id if valid.
    Returns None if invalid.
    """
    try:
        # Decode the token
        payload = jwt.decode(
            token,
            auth_settings.jwt_secret_key,
            algorithms=[auth_settings.jwt_algorithm]
        )

        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            return None

        # Check if token exists in Redis cache
        token_id = payload.get("jti")
        if not token_id:
            return None

        user_id = TokenCache.get_refresh_token(token_id)
        return user_id

    except JWTError:
        return None


def revoke_access_token(token: str) -> bool:
    """
    Revoke an access token by removing it from Redis cache.
    """
    try:
        payload = jwt.decode(
            token,
            auth_settings.jwt_secret_key,
            algorithms=[auth_settings.jwt_algorithm],
            options={"verify_exp": False}  # Allow revoking expired tokens
        )

        token_id = payload.get("jti")
        if token_id:
            TokenCache.delete_access_token(token_id)
            return True
        return False

    except JWTError:
        return False


def revoke_refresh_token(token: str) -> bool:
    """
    Revoke a refresh token by removing it from Redis cache.
    """
    try:
        payload = jwt.decode(
            token,
            auth_settings.jwt_secret_key,
            algorithms=[auth_settings.jwt_algorithm],
            options={"verify_exp": False}
        )

        token_id = payload.get("jti")
        if token_id:
            TokenCache.delete_refresh_token(token_id)
            return True
        return False

    except JWTError:
        return False
