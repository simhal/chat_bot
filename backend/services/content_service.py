"""Service for managing content articles with Redis caching."""

from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
from models import ContentArticle, ContentRating
from services.content_cache import ContentCache


class ContentService:
    """
    Service for content article operations.
    Provides Redis caching layer on top of database queries.
    """

    @staticmethod
    def _article_to_dict(article: ContentArticle) -> Dict:
        """Convert article model to dictionary."""
        return {
            "id": article.id,
            "topic": article.topic,
            "headline": article.headline,
            "content": article.content,
            "readership_count": article.readership_count,
            "rating": article.rating,
            "rating_count": article.rating_count,
            "keywords": article.keywords,
            "created_at": article.created_at.isoformat(),
            "updated_at": article.updated_at.isoformat(),
            "created_by_agent": article.created_by_agent,
            "is_active": article.is_active
        }

    @staticmethod
    def get_article(db: Session, article_id: int, increment_readership: bool = True) -> Optional[Dict]:
        """
        Get an article by ID with caching.

        Args:
            db: Database session
            article_id: Article ID
            increment_readership: Whether to increment the readership counter

        Returns:
            Article dict or None if not found
        """
        # Try cache first
        cached = ContentCache.get_article(article_id)
        if cached:
            if increment_readership:
                # Still need to increment in DB
                article = db.query(ContentArticle).filter(
                    ContentArticle.id == article_id,
                    ContentArticle.is_active == True
                ).first()
                if article:
                    article.readership_count += 1
                    db.commit()
                    # Invalidate cache since readership changed
                    ContentCache.invalidate_article(article_id)
            return cached

        # Cache miss - query database
        article = db.query(ContentArticle).filter(
            ContentArticle.id == article_id,
            ContentArticle.is_active == True
        ).first()

        if not article:
            return None

        # Increment readership if requested
        if increment_readership:
            article.readership_count += 1
            db.commit()
            db.refresh(article)

        # Convert to dict and cache
        article_dict = ContentService._article_to_dict(article)
        ContentCache.set_article(article_id, article_dict)

        return article_dict

    @staticmethod
    def get_recent_articles(db: Session, topic: str, limit: int = 10) -> List[Dict]:
        """
        Get recent articles for a topic with caching.

        Args:
            db: Database session
            topic: Topic name (macro, equity, fixed_income, esg)
            limit: Maximum number of articles to return

        Returns:
            List of article dicts
        """
        # Try cache first
        cached = ContentCache.get_topic_articles(topic, limit)
        if cached:
            return cached

        # Cache miss - query database
        articles = db.query(ContentArticle).filter(
            ContentArticle.topic == topic,
            ContentArticle.is_active == True
        ).order_by(desc(ContentArticle.created_at)).limit(limit).all()

        # Convert to dicts and cache
        article_dicts = [ContentService._article_to_dict(a) for a in articles]
        ContentCache.set_topic_articles(topic, article_dicts, limit)

        return article_dicts

    @staticmethod
    def search_articles(db: Session, topic: str, query: str, limit: int = 10) -> List[Dict]:
        """
        Search articles by headline and keywords with caching.

        Args:
            db: Database session
            topic: Topic name
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching article dicts
        """
        # Try cache first
        cached = ContentCache.search_cached_content(topic, query)
        if cached:
            return cached

        # Cache miss - query database
        search_term = f"%{query.lower()}%"
        articles = db.query(ContentArticle).filter(
            ContentArticle.topic == topic,
            ContentArticle.is_active == True,
            or_(
                func.lower(ContentArticle.headline).like(search_term),
                func.lower(ContentArticle.keywords).like(search_term),
                func.lower(ContentArticle.content).like(search_term)
            )
        ).order_by(desc(ContentArticle.created_at)).limit(limit).all()

        # Convert to dicts and cache
        article_dicts = [ContentService._article_to_dict(a) for a in articles]
        ContentCache.set_search_results(topic, query, article_dicts)

        return article_dicts

    @staticmethod
    def create_article(
        db: Session,
        topic: str,
        headline: str,
        content: str,
        keywords: Optional[str],
        agent_name: str
    ) -> Dict:
        """
        Create a new article and invalidate cache.

        Args:
            db: Database session
            topic: Topic name
            headline: Article headline
            content: Article content (max 1000 words)
            keywords: Comma-separated keywords
            agent_name: Name of the agent creating the article

        Returns:
            Created article dict
        """
        article = ContentArticle(
            topic=topic,
            headline=headline,
            content=content,
            keywords=keywords,
            created_by_agent=agent_name
        )

        db.add(article)
        db.commit()
        db.refresh(article)

        # Invalidate topic cache since new article was added
        ContentCache.invalidate_topic(topic)

        return ContentService._article_to_dict(article)

    @staticmethod
    def rate_article(db: Session, article_id: int, user_id: int, rating: int) -> Dict:
        """
        Rate an article (1-5 stars).

        Args:
            db: Database session
            article_id: Article ID
            user_id: User ID
            rating: Rating value (1-5)

        Returns:
            Updated article dict

        Raises:
            ValueError: If rating is out of range or article not found
        """
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        article = db.query(ContentArticle).filter(
            ContentArticle.id == article_id,
            ContentArticle.is_active == True
        ).first()

        if not article:
            raise ValueError("Article not found")

        # Check if user already rated this article
        existing_rating = db.query(ContentRating).filter(
            ContentRating.article_id == article_id,
            ContentRating.user_id == user_id
        ).first()

        if existing_rating:
            # Update existing rating
            old_rating = existing_rating.rating
            existing_rating.rating = rating
            db.commit()

            # Recalculate average rating
            total_rating = (article.rating * article.rating_count) - old_rating + rating
            article.rating = round(total_rating / article.rating_count)
        else:
            # Create new rating
            new_rating = ContentRating(
                article_id=article_id,
                user_id=user_id,
                rating=rating
            )
            db.add(new_rating)
            db.commit()

            # Update article rating
            article.rating_count += 1
            if article.rating is None:
                article.rating = rating
            else:
                total_rating = (article.rating * (article.rating_count - 1)) + rating
                article.rating = round(total_rating / article.rating_count)

        db.commit()
        db.refresh(article)

        # Invalidate cache
        ContentCache.invalidate_article(article_id)
        ContentCache.invalidate_topic(article.topic)

        return ContentService._article_to_dict(article)

    @staticmethod
    def get_top_rated_articles(db: Session, topic: str, limit: int = 10) -> List[Dict]:
        """
        Get top-rated articles for a topic.

        Args:
            db: Database session
            topic: Topic name
            limit: Maximum number of articles

        Returns:
            List of top-rated article dicts
        """
        articles = db.query(ContentArticle).filter(
            ContentArticle.topic == topic,
            ContentArticle.is_active == True,
            ContentArticle.rating.isnot(None)
        ).order_by(
            desc(ContentArticle.rating),
            desc(ContentArticle.rating_count)
        ).limit(limit).all()

        return [ContentService._article_to_dict(a) for a in articles]

    @staticmethod
    def get_most_read_articles(db: Session, topic: str, limit: int = 10) -> List[Dict]:
        """
        Get most-read articles for a topic.

        Args:
            db: Database session
            topic: Topic name
            limit: Maximum number of articles

        Returns:
            List of most-read article dicts
        """
        articles = db.query(ContentArticle).filter(
            ContentArticle.topic == topic,
            ContentArticle.is_active == True
        ).order_by(
            desc(ContentArticle.readership_count)
        ).limit(limit).all()

        return [ContentService._article_to_dict(a) for a in articles]

    @staticmethod
    def get_all_articles_admin(db: Session, topic: str, offset: int = 0, limit: int = 20) -> List[Dict]:
        """
        Admin-only: Get all articles for a topic with pagination (includes inactive).

        Args:
            db: Database session
            topic: Topic name
            offset: Number of articles to skip
            limit: Maximum number of articles

        Returns:
            List of article dicts
        """
        articles = db.query(ContentArticle).filter(
            ContentArticle.topic == topic
        ).order_by(desc(ContentArticle.created_at)).offset(offset).limit(limit).all()

        return [ContentService._article_to_dict(a) for a in articles]

    @staticmethod
    def delete_article(db: Session, article_id: int) -> None:
        """
        Admin-only: Soft delete an article.

        Args:
            db: Database session
            article_id: Article ID to delete

        Raises:
            ValueError: If article not found
        """
        article = db.query(ContentArticle).filter(
            ContentArticle.id == article_id
        ).first()

        if not article:
            raise ValueError("Article not found")

        # Soft delete
        article.is_active = False
        db.commit()

        # Invalidate cache
        ContentCache.invalidate_article(article_id)
        ContentCache.invalidate_topic(article.topic)

    @staticmethod
    def update_article(
        db: Session,
        article_id: int,
        headline: Optional[str] = None,
        content: Optional[str] = None,
        keywords: Optional[str] = None
    ) -> Dict:
        """
        Update an article. At least one field must be provided.

        Args:
            db: Database session
            article_id: Article ID to update
            headline: New headline (optional)
            content: New content (optional)
            keywords: New keywords (optional)

        Returns:
            Updated article dict

        Raises:
            ValueError: If article not found or no fields provided
        """
        article = db.query(ContentArticle).filter(
            ContentArticle.id == article_id,
            ContentArticle.is_active == True
        ).first()

        if not article:
            raise ValueError("Article not found")

        # Check that at least one field is provided
        if headline is None and content is None and keywords is None:
            raise ValueError("At least one field must be provided for update")

        # Update fields
        if headline is not None:
            article.headline = headline
        if content is not None:
            article.content = content
        if keywords is not None:
            article.keywords = keywords

        db.commit()
        db.refresh(article)

        # Invalidate cache
        ContentCache.invalidate_article(article_id)
        ContentCache.invalidate_topic(article.topic)

        return ContentService._article_to_dict(article)
