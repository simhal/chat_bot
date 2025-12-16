"""Redis caching service for content articles."""

import redis
import json
from typing import Optional, List, Dict
from pydantic_settings import BaseSettings
import logging

logger = logging.getLogger("uvicorn")


class CacheSettings(BaseSettings):
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 1  # Use different DB than auth cache
    redis_password: Optional[str] = None
    cache_ttl: int = 3600  # 1 hour default TTL

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


cache_settings = CacheSettings()

# Redis client - initialized lazily on first use
_content_cache = None
_cache_initialized = False
_cache_failed = False


def _get_cache():
    """
    Lazy initialization of Redis client.
    Returns None if Redis is unavailable.
    """
    global _content_cache, _cache_initialized, _cache_failed

    if _cache_initialized:
        return _content_cache

    if _cache_failed:
        return None

    try:
        logger.info(f"Content Cache: Initializing Redis connection")
        logger.info(f"  Host: {cache_settings.redis_host}")
        logger.info(f"  Port: {cache_settings.redis_port}")
        logger.info(f"  DB: {cache_settings.redis_db}")

        _content_cache = redis.Redis(
            host=cache_settings.redis_host,
            port=cache_settings.redis_port,
            db=cache_settings.redis_db,
            password=cache_settings.redis_password,
            decode_responses=True,
            socket_connect_timeout=5
        )
        # Test connection
        _content_cache.ping()
        _cache_initialized = True
        logger.info(f"✓ Content Cache: Redis connected successfully")
        return _content_cache
    except Exception as e:
        logger.error(f"✗ Content Cache: Redis connection failed: {e}")
        logger.warning(f"  Content caching will be disabled")
        _cache_failed = True
        _cache_initialized = True
        return None


class ContentCache:
    """
    Redis caching layer for content articles.
    Provides topic-specific caching to speed up queries.
    """

    @staticmethod
    def _make_key(prefix: str, identifier: str) -> str:
        """Create a namespaced cache key."""
        return f"content:{prefix}:{identifier}"

    @staticmethod
    def get_article(article_id: int) -> Optional[Dict]:
        """
        Get a cached article by ID.

        Args:
            article_id: Article ID

        Returns:
            Article dict or None if not cached
        """
        cache = _get_cache()
        if cache is None:
            return None
        try:
            key = ContentCache._make_key("article", str(article_id))
            cached = cache.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
        return None

    @staticmethod
    def set_article(article_id: int, article_data: Dict, ttl: Optional[int] = None):
        """
        Cache an article.

        Args:
            article_id: Article ID
            article_data: Article data dictionary
            ttl: Time to live in seconds (default: from settings)
        """
        cache = _get_cache()
        if cache is None:
            return
        try:
            key = ContentCache._make_key("article", str(article_id))
            ttl = ttl or cache_settings.cache_ttl
            cache.setex(key, ttl, json.dumps(article_data))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    @staticmethod
    def get_topic_articles(topic: str, limit: int = 10) -> Optional[List[Dict]]:
        """
        Get cached articles for a specific topic.

        Args:
            topic: Topic name (macro, equity, fixed_income, esg)
            limit: Maximum number of articles to return

        Returns:
            List of article dicts or None if not cached
        """
        cache = _get_cache()
        if cache is None:
            return None
        try:
            key = ContentCache._make_key("topic", f"{topic}:{limit}")
            cached = cache.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
        return None

    @staticmethod
    def set_topic_articles(topic: str, articles: List[Dict], limit: int = 10, ttl: Optional[int] = None):
        """
        Cache articles for a specific topic.

        Args:
            topic: Topic name
            articles: List of article data dictionaries
            limit: Number of articles (for cache key)
            ttl: Time to live in seconds (default: from settings)
        """
        cache = _get_cache()
        if cache is None:
            return
        try:
            key = ContentCache._make_key("topic", f"{topic}:{limit}")
            ttl = ttl or cache_settings.cache_ttl
            cache.setex(key, ttl, json.dumps(articles))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    @staticmethod
    def search_cached_content(topic: str, query: str) -> Optional[List[Dict]]:
        """
        Get cached search results for a topic and query.

        Args:
            topic: Topic name
            query: Search query (lowercased for consistency)

        Returns:
            List of matching article dicts or None if not cached
        """
        cache = _get_cache()
        if cache is None:
            return None
        try:
            # Normalize query for cache key
            query_key = query.lower().strip()
            key = ContentCache._make_key("search", f"{topic}:{query_key}")
            cached = cache.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
        return None

    @staticmethod
    def set_search_results(topic: str, query: str, results: List[Dict], ttl: Optional[int] = None):
        """
        Cache search results.

        Args:
            topic: Topic name
            query: Search query
            results: List of matching article dicts
            ttl: Time to live in seconds (default: from settings)
        """
        cache = _get_cache()
        if cache is None:
            return
        try:
            query_key = query.lower().strip()
            key = ContentCache._make_key("search", f"{topic}:{query_key}")
            ttl = ttl or cache_settings.cache_ttl
            cache.setex(key, ttl, json.dumps(results))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    @staticmethod
    def invalidate_topic(topic: str):
        """
        Invalidate all cached data for a specific topic.

        Args:
            topic: Topic name
        """
        cache = _get_cache()
        if cache is None:
            return
        try:
            # Find and delete all keys matching the topic
            pattern = ContentCache._make_key("topic", f"{topic}:*")
            for key in cache.scan_iter(match=pattern):
                cache.delete(key)

            # Also invalidate search cache for this topic
            search_pattern = ContentCache._make_key("search", f"{topic}:*")
            for key in cache.scan_iter(match=search_pattern):
                cache.delete(key)
        except Exception as e:
            logger.warning(f"Cache invalidate error: {e}")

    @staticmethod
    def invalidate_article(article_id: int):
        """
        Invalidate cached data for a specific article.

        Args:
            article_id: Article ID
        """
        cache = _get_cache()
        if cache is None:
            return
        try:
            key = ContentCache._make_key("article", str(article_id))
            cache.delete(key)
        except Exception as e:
            logger.warning(f"Cache invalidate error: {e}")

    @staticmethod
    def clear_all():
        """Clear all content cache."""
        cache = _get_cache()
        if cache is None:
            return
        try:
            cache.flushdb()
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
