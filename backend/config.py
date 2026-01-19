"""
Centralized configuration management using Pydantic Settings.

All application settings are defined here and loaded from environment variables.
Import settings from this module rather than using os.getenv() directly.

Usage:
    from config import settings

    # Access settings
    db_url = settings.database_url
    openai_key = settings.openai_api_key
    agent_build = settings.agent_build
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Required settings (no defaults) will raise an error if not set.
    Optional settings have sensible defaults for local development.
    """

    # -------------------------------------------------------------------------
    # General
    # -------------------------------------------------------------------------
    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql://chatbot_user:chatbot_password@localhost:5432/chatbot",
        description="PostgreSQL connection URL"
    )

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )

    # -------------------------------------------------------------------------
    # JWT Authentication
    # -------------------------------------------------------------------------
    jwt_secret_key: str = Field(
        default="",  # Required for auth - will fail at runtime if not set
        description="Secret key for signing JWT tokens"
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm"
    )
    access_token_expire_minutes: int = Field(
        default=1440,  # 24 hours
        description="Access token expiration in minutes"
    )
    refresh_token_expire_days: int = Field(
        default=7,
        description="Refresh token expiration in days"
    )

    # -------------------------------------------------------------------------
    # LinkedIn OAuth
    # -------------------------------------------------------------------------
    linkedin_client_id: str = Field(
        default="",  # Required for OAuth - will fail at runtime if not set
        description="LinkedIn OAuth client ID"
    )
    linkedin_client_secret: str = Field(
        default="",  # Required for OAuth - will fail at runtime if not set
        description="LinkedIn OAuth client secret"
    )

    # -------------------------------------------------------------------------
    # OpenAI
    # -------------------------------------------------------------------------
    openai_api_key: str = Field(
        default="",  # Required for AI features - will fail at runtime if not set
        description="OpenAI API key"
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="Default OpenAI chat model"
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model"
    )

    # -------------------------------------------------------------------------
    # Google Search (Optional)
    # -------------------------------------------------------------------------
    google_api_key: Optional[str] = Field(
        default=None,
        description="Google API key for Custom Search"
    )
    google_search_engine_id: Optional[str] = Field(
        default=None,
        description="Google Custom Search Engine ID"
    )

    # -------------------------------------------------------------------------
    # ChromaDB
    # -------------------------------------------------------------------------
    chroma_host: str = Field(
        default="localhost",
        description="ChromaDB host"
    )
    chroma_port: int = Field(
        default=8000,
        description="ChromaDB port"
    )
    chroma_collection_name: str = Field(
        default="research_articles",
        description="ChromaDB collection name"
    )

    # -------------------------------------------------------------------------
    # Agent System
    # -------------------------------------------------------------------------
    agent_build: str = Field(
        default="v1",
        description="Agent build version (v1, v2, etc.)"
    )
    intent_classifier_use_llm: bool = Field(
        default=True,
        description="Use LLM for intent classification"
    )
    intent_classifier_model: Optional[str] = Field(
        default=None,
        description="Model for intent classification (defaults to openai_model)"
    )
    intent_classifier_temperature: float = Field(
        default=0.1,
        description="Temperature for intent classifier"
    )

    # -------------------------------------------------------------------------
    # Storage
    # -------------------------------------------------------------------------
    upload_dir: str = Field(
        default="/app/uploads",
        description="Local directory for file uploads"
    )
    api_base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL for API resource links"
    )
    s3_bucket: Optional[str] = Field(
        default=None,
        description="S3 bucket name (optional)"
    )
    aws_region: str = Field(
        default="eu-central-1",
        description="AWS region"
    )

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        description="Comma-separated allowed CORS origins"
    )

    # -------------------------------------------------------------------------
    # LangSmith (Optional)
    # -------------------------------------------------------------------------
    langchain_tracing_v2: bool = Field(
        default=False,
        description="Enable LangSmith tracing"
    )
    langchain_api_key: Optional[str] = Field(
        default=None,
        description="LangSmith API key"
    )
    langchain_project: str = Field(
        default="chatbot-multiagent",
        description="LangSmith project name"
    )
    langchain_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        description="LangSmith API endpoint"
    )

    class Config:
        case_sensitive = False
        extra = "ignore"

    # -------------------------------------------------------------------------
    # Computed Properties
    # -------------------------------------------------------------------------

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS origins as a list."""
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def effective_intent_classifier_model(self) -> str:
        """Intent classifier model (falls back to openai_model)."""
        return self.intent_classifier_model or self.openai_model

    @property
    def google_search_enabled(self) -> bool:
        """Check if Google Search is configured."""
        return bool(self.google_api_key and self.google_search_engine_id)

    @property
    def s3_enabled(self) -> bool:
        """Check if S3 storage is configured."""
        return bool(self.s3_bucket)

    @property
    def langsmith_enabled(self) -> bool:
        """Check if LangSmith is configured and enabled."""
        return self.langchain_tracing_v2 and bool(self.langchain_api_key)


# =============================================================================
# Singleton Instance
# =============================================================================

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Singleton settings instance
# All settings have defaults, so this will always succeed.
# Missing credentials will cause runtime errors when actually used.
settings = Settings()
