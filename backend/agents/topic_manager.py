"""
Topic Manager for dynamic topic handling.

This module manages topics dynamically from the database.
It matches user messages against topic slugs and titles.
"""

from typing import Dict, List, Optional, Any
import logging
from datetime import datetime
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Reserved keywords that should NOT be used as topic slugs
# These are navigation targets and would conflict with topic routing
# Note: "global" is NOT reserved - it's a special topic for system-wide content
RESERVED_KEYWORDS = {
    "home", "search", "analyst", "editor", "admin", "profile",
    "content", "settings", "account", "login", "logout",
    "auth", "callback", "api"
}


@dataclass
class TopicConfig:
    """Configuration for a single topic."""
    slug: str                        # URL-safe identifier (e.g., "macro")
    name: str                        # Display name (e.g., "Macro Economics")
    description: str                 # Full description
    active: bool = True              # Whether topic is active
    visible: bool = True             # Whether topic is visible in reader section
    access_mainchat: bool = True     # Whether AI agents can access this topic
    order: int = 0                   # Display order


# Module-level cache for topics (shared across all instances)
_topics_cache: Dict[str, TopicConfig] = {}
_cache_time: Optional[datetime] = None
CACHE_TIMEOUT = 60  # 1 minute cache


def _get_db_session() -> Session:
    """Get a new database session."""
    from database import SessionLocal
    return SessionLocal()


def _load_topics_from_db() -> Dict[str, TopicConfig]:
    """Load all active topics from database."""
    global _topics_cache, _cache_time

    # Check cache
    if _cache_time and _topics_cache:
        age = (datetime.utcnow() - _cache_time).total_seconds()
        if age < CACHE_TIMEOUT:
            return _topics_cache

    try:
        from models import Topic
        db = _get_db_session()
        try:
            db_topics = db.query(Topic).filter(Topic.active == True).all()

            result = {}
            for topic in db_topics:
                result[topic.slug] = TopicConfig(
                    slug=topic.slug,
                    name=topic.title,  # Use 'title' field from DB
                    description=topic.description or "",
                    active=topic.active,
                    visible=getattr(topic, "visible", True),
                    access_mainchat=getattr(topic, "access_mainchat", True),
                    order=getattr(topic, "sort_order", 0) or 0
                )

            if result:
                _topics_cache = result
                _cache_time = datetime.utcnow()
                logger.debug(f"Loaded {len(result)} topics from database: {list(result.keys())}")
                return result
        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Failed to load topics from database: {e}")

    # Return cached if available, even if expired
    if _topics_cache:
        return _topics_cache

    # No cache and no DB - return empty
    logger.warning("No topics available - database not accessible")
    return {}


def get_available_topics() -> List[str]:
    """
    Get list of available topic slugs from database.

    Returns:
        List of topic slugs
    """
    topics = _load_topics_from_db()
    return [t.slug for t in topics.values() if t.active]


def get_topic_config(topic_slug: str) -> Optional[TopicConfig]:
    """
    Get configuration for a specific topic.

    Args:
        topic_slug: The topic slug to look up

    Returns:
        TopicConfig if found, None otherwise
    """
    topics = _load_topics_from_db()
    return topics.get(topic_slug)


def get_all_topics() -> List[TopicConfig]:
    """
    Get all active topic configurations.

    Returns:
        List of TopicConfig objects sorted by order
    """
    topics = _load_topics_from_db()
    result = [t for t in topics.values() if t.active]
    result.sort(key=lambda t: t.order)
    return result


def get_visible_topics() -> List[TopicConfig]:
    """
    Get all visible topics for the reader section.

    Only returns topics where both active=True and visible=True.

    Returns:
        List of TopicConfig objects sorted by order
    """
    topics = _load_topics_from_db()
    result = [t for t in topics.values() if t.active and t.visible]
    result.sort(key=lambda t: t.order)
    return result


def get_ai_accessible_topics() -> List[TopicConfig]:
    """
    Get topics accessible by AI agents (chat and article query).

    Only returns topics where both active=True and access_mainchat=True.
    Used by chat agents and article query agents to filter which topics
    they should consider when processing user requests.

    Returns:
        List of TopicConfig objects sorted by order
    """
    topics = _load_topics_from_db()
    result = [t for t in topics.values() if t.active and t.access_mainchat]
    result.sort(key=lambda t: t.order)
    return result


def get_ai_accessible_topic_slugs() -> List[str]:
    """
    Get list of topic slugs accessible by AI agents.

    Returns:
        List of topic slugs where access_mainchat=True
    """
    return [t.slug for t in get_ai_accessible_topics()]


def infer_topic(message: str, db: Optional[Session] = None, ai_only: bool = True) -> Optional[str]:
    """
    Infer topic from a user message by matching against slugs and titles.

    Matching priority:
    1. Exact slug match (e.g., "macro" matches topic with slug "macro")
    2. Slug with underscores/hyphens (e.g., "fixed income" matches "fixed_income")
    3. Title word match (e.g., "economics" matches "Macro Economics")

    Args:
        message: User message
        db: Optional database session (not used, loads its own)
        ai_only: If True, only consider topics with access_mainchat=True (default True)

    Returns:
        Inferred topic slug or None
    """
    message_lower = message.lower()
    topics = _load_topics_from_db()

    if not topics:
        logger.warning("No topics loaded, cannot infer topic")
        return None

    # Build match candidates for each topic
    # Score: higher = better match
    scores: Dict[str, int] = {}

    for slug, config in topics.items():
        if not config.active:
            continue

        # Skip topics not accessible by AI when ai_only is True
        if ai_only and not config.access_mainchat:
            continue

        score = 0
        title_lower = config.name.lower()

        # 1. Exact slug match (highest priority)
        if slug in message_lower:
            score += 100

        # 2. Slug variations (with spaces instead of underscores)
        slug_spaced = slug.replace("_", " ").replace("-", " ")
        if slug_spaced in message_lower:
            score += 90

        # 3. Full title match (e.g., "ESG Research", "Fixed Income Research")
        if title_lower in message_lower:
            score += 95

        # 4. Title without common suffixes (e.g., "ESG" from "ESG Research")
        title_cleaned = title_lower
        for suffix in [" research", " analysis", " documentation"]:
            if title_cleaned.endswith(suffix):
                title_cleaned = title_cleaned[:-len(suffix)]
                break
        if title_cleaned and title_cleaned in message_lower:
            score += 85

        # 5. Title words match
        title_words = title_lower.split()
        for word in title_words:
            # Skip common words
            if word in ["research", "analysis", "the", "and", "of", "for", "documentation"]:
                continue
            if len(word) >= 3 and word in message_lower:
                score += 10

        if score > 0:
            scores[slug] = score

    # Return highest scoring topic (excluding reserved keywords)
    if scores:
        # Filter out reserved keywords from candidates
        valid_scores = {k: v for k, v in scores.items() if k.lower() not in RESERVED_KEYWORDS}
        if valid_scores:
            best_topic = max(valid_scores, key=valid_scores.get)
            logger.debug(f"Inferred topic '{best_topic}' from message (score: {valid_scores[best_topic]})")
            return best_topic

    return None


def is_valid_topic(topic_slug: str) -> bool:
    """
    Check if a topic slug is valid and active.

    Args:
        topic_slug: The topic slug to check

    Returns:
        True if valid and active and not a reserved keyword, False otherwise
    """
    # Reserved keywords cannot be valid topic slugs
    if topic_slug.lower() in RESERVED_KEYWORDS:
        return False
    config = get_topic_config(topic_slug)
    return config is not None and config.active


def refresh_cache():
    """Force refresh of topic cache."""
    global _topics_cache, _cache_time
    _topics_cache = {}
    _cache_time = None
    _load_topics_from_db()


# Legacy compatibility - these are no longer needed but kept for imports
class TopicManager:
    """Legacy class - use module-level functions instead."""

    def __init__(self, db: Optional[Session] = None):
        pass

    def get_available_topics(self) -> List[str]:
        return get_available_topics()

    def get_topic_config(self, topic_slug: str) -> Optional[TopicConfig]:
        return get_topic_config(topic_slug)

    def get_all_topics(self) -> List[TopicConfig]:
        return get_all_topics()

    def infer_topic_from_message(self, message: str) -> Optional[str]:
        return infer_topic(message)

    def is_valid_topic(self, topic_slug: str) -> bool:
        return is_valid_topic(topic_slug)


def get_topic_manager(db: Optional[Session] = None) -> TopicManager:
    """Legacy function - returns a TopicManager instance."""
    return TopicManager(db)
