"""
Topic Manager for dynamic topic handling.

This module manages topics dynamically from the database instead of
hardcoding them. It provides caching for performance and helpers for
topic inference from user messages.
"""

from typing import Dict, List, Optional, Any
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class TopicConfig:
    """Configuration for a single topic."""
    slug: str                        # URL-safe identifier (e.g., "macro")
    name: str                        # Display name (e.g., "Macro Economics")
    description: str                 # Full description
    keywords: List[str]              # Keywords for inference
    icon: Optional[str] = None       # Optional icon identifier
    active: bool = True              # Whether topic is active
    order: int = 0                   # Display order
    metadata: Dict[str, Any] = field(default_factory=dict)  # Extra metadata


# Default topic configurations - used when database topics not available
DEFAULT_TOPICS: Dict[str, TopicConfig] = {
    "macro": TopicConfig(
        slug="macro",
        name="Macro Economics",
        description="Macroeconomic analysis covering GDP, inflation, interest rates, monetary policy, and economic indicators",
        keywords=[
            "economy", "economic", "gdp", "inflation", "fed", "federal reserve",
            "interest rate", "unemployment", "jobs", "growth", "recession",
            "monetary policy", "fiscal", "treasury", "ecb", "central bank",
            "employment", "cpi", "ppi", "retail sales", "housing"
        ],
        order=1
    ),
    "equity": TopicConfig(
        slug="equity",
        name="Equity Markets",
        description="Equity market analysis covering stocks, valuations, earnings, and market trends",
        keywords=[
            "stock", "equity", "equities", "shares", "company", "earnings",
            "revenue", "profit", "valuation", "p/e", "market cap", "dividend",
            "nasdaq", "s&p", "dow", "ipo", "buyback", "eps", "growth stock",
            "value stock", "sector"
        ],
        order=2
    ),
    "fixed_income": TopicConfig(
        slug="fixed_income",
        name="Fixed Income",
        description="Fixed income analysis covering bonds, yields, credit markets, and debt instruments",
        keywords=[
            "bond", "bonds", "yield", "credit", "treasury", "debt", "coupon",
            "maturity", "duration", "spread", "default", "investment grade",
            "high yield", "fixed income", "sovereign", "corporate bond",
            "municipal", "junk bond", "credit rating"
        ],
        order=3
    ),
    "esg": TopicConfig(
        slug="esg",
        name="ESG",
        description="ESG analysis covering environmental, social, and governance factors in investing",
        keywords=[
            "esg", "sustainability", "climate", "environmental", "social",
            "governance", "carbon", "renewable", "green", "impact",
            "responsible", "ethical", "net zero", "emissions", "diversity",
            "stakeholder", "sustainable"
        ],
        order=4
    )
}


class TopicManager:
    """
    Manages topics dynamically from the database.

    Features:
    - Loads topics from database with caching
    - Falls back to defaults if database unavailable
    - Provides topic inference from user messages
    - Caches for performance (refreshes periodically)
    """

    # Cache timeout in seconds
    CACHE_TIMEOUT = 300  # 5 minutes

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize the topic manager.

        Args:
            db: Optional database session. If not provided, uses defaults.
        """
        self.db = db
        self._cache: Dict[str, TopicConfig] = {}
        self._cache_time: Optional[datetime] = None

    def get_available_topics(self, force_refresh: bool = False) -> List[str]:
        """
        Get list of available topic slugs.

        Args:
            force_refresh: Force reload from database

        Returns:
            List of topic slugs
        """
        topics = self._get_topics(force_refresh)
        return [t.slug for t in topics.values() if t.active]

    def get_topic_config(self, topic_slug: str) -> Optional[TopicConfig]:
        """
        Get configuration for a specific topic.

        Args:
            topic_slug: The topic slug to look up

        Returns:
            TopicConfig if found, None otherwise
        """
        topics = self._get_topics()
        return topics.get(topic_slug)

    def get_all_topics(self, include_inactive: bool = False) -> List[TopicConfig]:
        """
        Get all topic configurations.

        Args:
            include_inactive: Whether to include inactive topics

        Returns:
            List of TopicConfig objects
        """
        topics = self._get_topics()
        result = list(topics.values())

        if not include_inactive:
            result = [t for t in result if t.active]

        # Sort by order
        result.sort(key=lambda t: t.order)

        return result

    def infer_topic_from_message(self, message: str) -> Optional[str]:
        """
        Infer topic from a user message using keyword matching.

        Args:
            message: The user's message

        Returns:
            Topic slug if matched, None otherwise
        """
        message_lower = message.lower()
        topics = self._get_topics()

        # Score each topic based on keyword matches
        scores: Dict[str, int] = {}

        for slug, config in topics.items():
            if not config.active:
                continue

            score = 0
            for keyword in config.keywords:
                if keyword.lower() in message_lower:
                    # Longer keywords get higher weight
                    score += len(keyword.split())

            if score > 0:
                scores[slug] = score

        # Return highest scoring topic
        if scores:
            best_topic = max(scores, key=scores.get)
            logger.debug(f"Inferred topic '{best_topic}' from message (score: {scores[best_topic]})")
            return best_topic

        return None

    def get_topic_keywords(self, topic_slug: str) -> List[str]:
        """
        Get keywords for a specific topic.

        Args:
            topic_slug: The topic slug

        Returns:
            List of keywords for the topic
        """
        config = self.get_topic_config(topic_slug)
        return config.keywords if config else []

    def is_valid_topic(self, topic_slug: str) -> bool:
        """
        Check if a topic slug is valid and active.

        Args:
            topic_slug: The topic slug to check

        Returns:
            True if valid and active, False otherwise
        """
        config = self.get_topic_config(topic_slug)
        return config is not None and config.active

    def _get_topics(self, force_refresh: bool = False) -> Dict[str, TopicConfig]:
        """Get topics from cache or load from database."""
        # Check cache validity
        if not force_refresh and self._is_cache_valid():
            return self._cache

        # Try to load from database
        if self.db:
            try:
                db_topics = self._load_from_database()
                if db_topics:
                    self._cache = db_topics
                    self._cache_time = datetime.utcnow()
                    logger.debug(f"Loaded {len(db_topics)} topics from database")
                    return self._cache
            except Exception as e:
                logger.warning(f"Failed to load topics from database: {e}")

        # Fall back to defaults
        if not self._cache:
            logger.debug("Using default topics")
            self._cache = DEFAULT_TOPICS.copy()
            self._cache_time = datetime.utcnow()

        return self._cache

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._cache or not self._cache_time:
            return False

        age = datetime.utcnow() - self._cache_time
        return age.total_seconds() < self.CACHE_TIMEOUT

    def _load_from_database(self) -> Optional[Dict[str, TopicConfig]]:
        """
        Load topics from database.

        Expected database model:
        - Topic table with: slug, name, description, keywords (JSON), active, order
        """
        if not self.db:
            return None

        try:
            # Import here to avoid circular imports
            from models import Topic

            db_topics = self.db.query(Topic).filter(Topic.active == True).all()

            result = {}
            for topic in db_topics:
                # Parse keywords - could be JSON array or comma-separated
                keywords = topic.keywords if isinstance(topic.keywords, list) else []
                if isinstance(topic.keywords, str):
                    keywords = [k.strip() for k in topic.keywords.split(",")]

                result[topic.slug] = TopicConfig(
                    slug=topic.slug,
                    name=topic.name,
                    description=topic.description or "",
                    keywords=keywords,
                    icon=getattr(topic, "icon", None),
                    active=topic.active,
                    order=getattr(topic, "order", 0),
                    metadata=getattr(topic, "metadata", {}) or {}
                )

            return result if result else None

        except Exception as e:
            logger.warning(f"Database topic load failed: {e}")
            return None

    def refresh(self):
        """Force refresh of topic cache."""
        self._cache = {}
        self._cache_time = None
        self._get_topics(force_refresh=True)


# Global instance for convenience
_global_manager: Optional[TopicManager] = None


def get_topic_manager(db: Optional[Session] = None) -> TopicManager:
    """
    Get the global topic manager instance.

    Args:
        db: Optional database session

    Returns:
        TopicManager instance
    """
    global _global_manager

    if _global_manager is None or db is not None:
        _global_manager = TopicManager(db)

    return _global_manager


def get_available_topics(db: Optional[Session] = None) -> List[str]:
    """
    Convenience function to get available topics.

    Args:
        db: Optional database session

    Returns:
        List of topic slugs
    """
    return get_topic_manager(db).get_available_topics()


def infer_topic(message: str, db: Optional[Session] = None) -> Optional[str]:
    """
    Convenience function to infer topic from message.

    Args:
        message: User message
        db: Optional database session

    Returns:
        Inferred topic slug or None
    """
    return get_topic_manager(db).infer_topic_from_message(message)
