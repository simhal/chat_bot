"""Service for managing content articles with Redis caching."""

from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
from models import ContentArticle, ContentRating
from services.content_cache import ContentCache
from services.vector_service import VectorService
import logging

logger = logging.getLogger("uvicorn")


class ContentService:
    """
    Service for content article operations.
    Provides Redis caching layer on top of database queries.
    """

    @staticmethod
    def _article_to_dict(article: ContentArticle, include_content: bool = True) -> Dict:
        """
        Convert article model to dictionary.
        Fetches content and metadata from ChromaDB (source of truth).
        PostgreSQL data is used as fallback for metadata.

        Args:
            article: ContentArticle model from PostgreSQL (used for relationships/counters)
            include_content: Whether to fetch content from ChromaDB

        Returns:
            Article dictionary with metadata and optionally content
        """
        # Base dict from PostgreSQL (for relationships and counters)
        article_dict = {
            "id": article.id,
            "topic": article.topic,
            "readership_count": article.readership_count,
            "rating": article.rating,
            "rating_count": article.rating_count,
            "created_at": article.created_at.isoformat(),
            "updated_at": article.updated_at.isoformat(),
            "created_by_agent": article.created_by_agent,
            "is_active": article.is_active,
            "status": article.status.value if hasattr(article.status, 'value') else article.status
        }

        # Fetch full article data from ChromaDB (source of truth for content + metadata)
        if include_content:
            chroma_data = VectorService.get_article_data(article.id)
            if chroma_data:
                # Use ChromaDB metadata as primary source
                metadata = chroma_data.get("metadata", {})
                article_dict.update({
                    "content": chroma_data.get("content", ""),
                    "headline": metadata.get("headline", article.headline or ""),
                    "author": metadata.get("author", article.author or ""),
                    "editor": metadata.get("editor", article.editor or ""),
                    "keywords": metadata.get("keywords", article.keywords or "")
                })
                # Update status from ChromaDB if available (PostgreSQL is primary for status)
                if "status" in metadata:
                    article_dict["status"] = metadata["status"]
            else:
                # Fallback to PostgreSQL if ChromaDB unavailable
                logger.warning(f"ChromaDB data unavailable for article {article.id}, using PostgreSQL fallback")
                article_dict.update({
                    "content": "",
                    "headline": article.headline or "",
                    "author": article.author or "",
                    "editor": article.editor or "",
                    "keywords": article.keywords or ""
                })
        else:
            # If content not requested, use PostgreSQL metadata (faster)
            article_dict.update({
                "headline": article.headline or "",
                "author": article.author or "",
                "editor": article.editor or "",
                "keywords": article.keywords or ""
            })

        return article_dict

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
    def search_articles(
        db: Session,
        topic: Optional[str] = None,
        query: Optional[str] = None,
        headline: Optional[str] = None,
        keywords: Optional[str] = None,
        author: Optional[str] = None,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Search articles using hybrid search (keyword + semantic) with multiple criteria.
        Falls back to keyword-only if vector DB unavailable.

        Args:
            db: Database session
            topic: Topic name (None means search across all topics)
            query: General search query (searches headline, keywords, and content via vector)
            headline: Filter by headline (partial match)
            keywords: Filter by keywords (partial match)
            author: Filter by author (partial match)
            created_after: Filter articles created after this date (ISO format)
            created_before: Filter articles created before this date (ISO format)
            limit: Maximum number of results (default 10)

        Returns:
            List of matching article dicts
        """
        # Build cache key from all parameters
        cache_key_parts = [topic or "all", query or "", headline or "", keywords or "", author or "",
                          created_after or "", created_before or "", str(limit)]
        cache_key = ":".join(cache_key_parts)

        # Try cache first (simplified - can enhance with proper cache key)
        if topic and query and not any([headline, keywords, author, created_after, created_before]):
            cached = ContentCache.search_cached_content(topic, query)
            if cached:
                return cached

        # Build filter conditions
        filters = [
            ContentArticle.is_active == True
        ]

        # Add topic filter only if topic is specified
        if topic:
            filters.append(ContentArticle.topic == topic)

        # Add specific field filters
        if headline:
            filters.append(func.lower(ContentArticle.headline).like(f"%{headline.lower()}%"))

        if keywords:
            filters.append(func.lower(ContentArticle.keywords).like(f"%{keywords.lower()}%"))

        if author:
            filters.append(func.lower(ContentArticle.author).like(f"%{author.lower()}%"))

        if created_after:
            from datetime import datetime
            date_after = datetime.fromisoformat(created_after.replace('Z', '+00:00'))
            filters.append(ContentArticle.created_at >= date_after)

        if created_before:
            from datetime import datetime
            date_before = datetime.fromisoformat(created_before.replace('Z', '+00:00'))
            filters.append(ContentArticle.created_at <= date_before)

        # Add general query search (headline and keywords)
        if query:
            search_term = f"%{query.lower()}%"
            filters.append(
                or_(
                    func.lower(ContentArticle.headline).like(search_term),
                    func.lower(ContentArticle.keywords).like(search_term)
                )
            )

        # Perform database query
        keyword_articles = db.query(ContentArticle).filter(
            *filters
        ).order_by(desc(ContentArticle.created_at)).limit(limit * 2).all()

        keyword_dicts = [ContentService._article_to_dict(a) for a in keyword_articles]

        # Try hybrid search if vector DB available
        try:
            ranked_results = VectorService.hybrid_search(
                query=query,
                keyword_results=keyword_dicts,
                topic=topic,  # Can be None for all topics
                limit=limit,
                semantic_weight=0.6  # 60% semantic, 40% keyword
            )

            # Get full article data for ranked results
            if ranked_results:
                # Map article IDs to articles
                article_map = {a['id']: a for a in keyword_dicts}

                # Add semantic results not in keyword results
                semantic_only = VectorService.semantic_search(query, topic, limit)
                for sem_result in semantic_only:
                    aid = sem_result['article_id']
                    if aid not in article_map:
                        article = db.query(ContentArticle).filter(
                            ContentArticle.id == aid,
                            ContentArticle.is_active == True
                        ).first()
                        if article:
                            article_map[aid] = ContentService._article_to_dict(article)

                # Build final result list
                final_results = []
                for ranked in ranked_results:
                    if ranked['article_id'] in article_map:
                        final_results.append(article_map[ranked['article_id']])

                # Cache and return (only cache if topic-specific)
                if topic and query:
                    ContentCache.set_search_results(topic, query, final_results)
                return final_results
        except Exception as e:
            logger.warning(f"Hybrid search failed, using keyword-only: {e}")

        # Fallback to keyword-only results
        article_dicts = keyword_dicts[:limit]
        if topic and query:
            ContentCache.set_search_results(topic, query, article_dicts)
        return article_dicts

    @staticmethod
    def create_article(
        db: Session,
        topic: str,
        headline: str,
        content: str,
        keywords: Optional[str],
        agent_name: str,
        author: Optional[str] = None,
        editor: Optional[str] = None,
        status: str = "draft"
    ) -> Dict:
        """
        Create a new article. Metadata stored in PostgreSQL, content in ChromaDB.

        Args:
            db: Database session
            topic: Topic name
            headline: Article headline
            content: Article content (1000-2000 words) - stored in ChromaDB only
            keywords: Comma-separated keywords
            agent_name: Name of the agent creating the article
            author: Author name
            editor: Editor name
            status: Article status (draft, editor, or published)

        Returns:
            Created article dict
        """
        from models import ArticleStatus

        # Create article metadata in PostgreSQL (no content field)
        article = ContentArticle(
            topic=topic,
            headline=headline,
            keywords=keywords,
            created_by_agent=agent_name,
            author=author,
            editor=editor,
            status=ArticleStatus(status)
        )

        db.add(article)
        db.commit()
        db.refresh(article)

        # Invalidate topic cache since new article was added
        ContentCache.invalidate_topic(topic)

        # Store content in ChromaDB (source of truth for content and metadata)
        success = VectorService.add_article(
            article_id=article.id,
            headline=headline,
            content=content,
            metadata={
                "topic": topic,
                "author": author,
                "editor": editor,
                "keywords": keywords,
                "status": status,
                "created_at": article.created_at,
                "updated_at": article.updated_at
            }
        )

        if not success:
            logger.error(f"Failed to store content in ChromaDB for article {article.id}")
            # Could optionally rollback or handle error differently

        # Return article dict with content from ChromaDB
        article_dict = ContentService._article_to_dict(article, include_content=True)
        return article_dict

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
        Admin-only: Soft delete an article (set inactive).
        Does NOT change status or delete content from ChromaDB.

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

        # Soft delete - only set inactive, do NOT change status or delete content
        article.is_active = False
        db.commit()

        # Invalidate cache
        ContentCache.invalidate_article(article_id)
        ContentCache.invalidate_topic(article.topic)

    @staticmethod
    def reactivate_article(db: Session, article_id: int) -> None:
        """
        Admin-only: Reactivate a soft-deleted article.

        Args:
            db: Database session
            article_id: Article ID to reactivate

        Raises:
            ValueError: If article not found
        """
        article = db.query(ContentArticle).filter(
            ContentArticle.id == article_id
        ).first()

        if not article:
            raise ValueError("Article not found")

        # Reactivate
        article.is_active = True
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
        keywords: Optional[str] = None,
        author: Optional[str] = None,
        editor: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict:
        """
        Update an article. Metadata in PostgreSQL, content in ChromaDB.

        Args:
            db: Database session
            article_id: Article ID to update
            headline: New headline (optional) - updates PostgreSQL
            content: New content (optional) - updates ChromaDB only
            keywords: New keywords (optional) - updates PostgreSQL
            author: New author (optional) - updates PostgreSQL
            editor: New editor (optional) - updates PostgreSQL
            status: New status (optional) - updates PostgreSQL

        Returns:
            Updated article dict

        Raises:
            ValueError: If article not found or no fields provided
        """
        from models import ArticleStatus

        article = db.query(ContentArticle).filter(
            ContentArticle.id == article_id,
            ContentArticle.is_active == True
        ).first()

        if not article:
            raise ValueError("Article not found")

        # Check that at least one field is provided
        if all(v is None for v in [headline, content, keywords, author, editor, status]):
            raise ValueError("At least one field must be provided for update")

        # Update metadata fields in PostgreSQL
        metadata_updated = False
        if headline is not None:
            article.headline = headline
            metadata_updated = True
        if keywords is not None:
            article.keywords = keywords
            metadata_updated = True
        if author is not None:
            article.author = author
            metadata_updated = True
        if editor is not None:
            article.editor = editor
            metadata_updated = True
        if status is not None:
            article.status = ArticleStatus(status)
            metadata_updated = True

        if metadata_updated:
            db.commit()
            db.refresh(article)

        # Invalidate cache
        ContentCache.invalidate_article(article_id)
        ContentCache.invalidate_topic(article.topic)

        # Update ChromaDB if content or headline changed
        if content is not None or headline is not None:
            # Get current content from ChromaDB if not updating it
            if content is None:
                content = VectorService.get_article_content(article_id)
                if content is None:
                    logger.error(f"Cannot update article {article_id}: content not found in ChromaDB")
                    content = ""

            VectorService.update_article(
                article_id=article.id,
                headline=article.headline,
                content=content,
                metadata={
                    "topic": article.topic,
                    "author": article.author,
                    "editor": article.editor,
                    "keywords": article.keywords,
                    "status": article.status.value if hasattr(article.status, 'value') else article.status,
                    "created_at": article.created_at,
                    "updated_at": article.updated_at
                }
            )

        # Return article dict with content from ChromaDB
        article_dict = ContentService._article_to_dict(article, include_content=True)
        return article_dict

    @staticmethod
    def get_articles_by_status(
        db: Session,
        topic: str,
        status: str,
        offset: int = 0,
        limit: int = 20
    ) -> List[Dict]:
        """
        Get articles for a topic filtered by status.
        Includes inactive (deleted) articles so they can be shown grayed out.

        Args:
            db: Database session
            topic: Topic name (macro, equity, fixed_income, esg)
            status: Article status (draft, editor, published)
            offset: Number of articles to skip
            limit: Maximum number of articles

        Returns:
            List of article dicts (both active and inactive)
        """
        from models import ArticleStatus
        
        # Include both active and inactive articles - inactive will be shown grayed out
        articles = db.query(ContentArticle).filter(
            ContentArticle.topic == topic,
            ContentArticle.status == ArticleStatus(status)
        ).order_by(desc(ContentArticle.created_at)).offset(offset).limit(limit).all()

        return [ContentService._article_to_dict(a) for a in articles]

    @staticmethod
    def update_article_status(db: Session, article_id: int, new_status: str) -> Dict:
        """
        Update article status (for editorial workflow).

        Args:
            db: Database session
            article_id: Article ID
            new_status: New status (draft, editor, published)

        Returns:
            Updated article dict

        Raises:
            ValueError: If article not found
        """
        from models import ArticleStatus
        
        article = db.query(ContentArticle).filter(
            ContentArticle.id == article_id,
            ContentArticle.is_active == True
        ).first()

        if not article:
            raise ValueError("Article not found")

        article.status = ArticleStatus(new_status)
        db.commit()
        db.refresh(article)

        # Invalidate cache
        ContentCache.invalidate_article(article_id)
        ContentCache.invalidate_topic(article.topic)

        return ContentService._article_to_dict(article)

    @staticmethod
    def get_published_articles(db: Session, topic: str, limit: int = 10) -> List[Dict]:
        """
        Get only published articles for a topic (for public display).

        Args:
            db: Database session
            topic: Topic name
            limit: Maximum number of articles

        Returns:
            List of published article dicts
        """
        from models import ArticleStatus
        
        articles = db.query(ContentArticle).filter(
            ContentArticle.topic == topic,
            ContentArticle.is_active == True,
            ContentArticle.status == ArticleStatus.PUBLISHED
        ).order_by(desc(ContentArticle.created_at)).limit(limit).all()

        return [ContentService._article_to_dict(a) for a in articles]

    @staticmethod
    def recall_article(db: Session, article_id: int) -> Dict:
        """
        Recall a published article (move back to draft status).

        Args:
            db: Database session
            article_id: Article ID to recall

        Returns:
            Updated article dict

        Raises:
            ValueError: If article not found or not in published status
        """
        from models import ArticleStatus

        article = db.query(ContentArticle).filter(
            ContentArticle.id == article_id,
            ContentArticle.is_active == True
        ).first()

        if not article:
            raise ValueError("Article not found")

        if article.status != ArticleStatus.PUBLISHED:
            raise ValueError("Only published articles can be recalled")

        article.status = ArticleStatus.DRAFT
        db.commit()
        db.refresh(article)

        # Invalidate cache
        ContentCache.invalidate_article(article_id)
        ContentCache.invalidate_topic(article.topic)

        return ContentService._article_to_dict(article)

    @staticmethod
    def purge_article(db: Session, article_id: int) -> None:
        """
        Permanently delete an article and all related data.
        This removes the article from PostgreSQL, ChromaDB, and all ratings.

        Args:
            db: Database session
            article_id: Article ID to purge

        Raises:
            ValueError: If article not found
        """
        article = db.query(ContentArticle).filter(
            ContentArticle.id == article_id
        ).first()

        if not article:
            raise ValueError("Article not found")

        topic = article.topic

        # Delete ratings first (foreign key constraint)
        db.query(ContentRating).filter(ContentRating.article_id == article_id).delete()

        # Delete from PostgreSQL
        db.delete(article)
        db.commit()

        # Delete from ChromaDB
        try:
            VectorService.delete_article(article_id)
        except Exception as e:
            logger.warning(f"Failed to delete article {article_id} from ChromaDB: {e}")

        # Invalidate cache
        ContentCache.invalidate_article(article_id)
        ContentCache.invalidate_topic(topic)

    @staticmethod
    def submit_article(db: Session, article_id: int, author_email: str) -> Dict:
        """
        Submit a draft article for review (move to editor status).
        Sets the author field to the submitter's email.

        Args:
            db: Database session
            article_id: Article ID to submit
            author_email: Email of the user submitting the article

        Returns:
            Updated article dict

        Raises:
            ValueError: If article not found or not in draft status
        """
        from models import ArticleStatus

        article = db.query(ContentArticle).filter(
            ContentArticle.id == article_id,
            ContentArticle.is_active == True
        ).first()

        if not article:
            raise ValueError("Article not found")

        if article.status != ArticleStatus.DRAFT:
            raise ValueError("Only draft articles can be submitted")

        article.status = ArticleStatus.EDITOR
        article.author = author_email
        db.commit()
        db.refresh(article)

        # Update ChromaDB metadata
        content = VectorService.get_article_content(article_id)
        if content:
            VectorService.update_article(
                article_id=article.id,
                headline=article.headline,
                content=content,
                metadata={
                    "topic": article.topic,
                    "author": article.author,
                    "editor": article.editor,
                    "keywords": article.keywords,
                    "status": article.status.value,
                    "created_at": article.created_at,
                    "updated_at": article.updated_at
                }
            )

        # Invalidate cache
        ContentCache.invalidate_article(article_id)
        ContentCache.invalidate_topic(article.topic)

        return ContentService._article_to_dict(article)

    @staticmethod
    def publish_article_with_editor(db: Session, article_id: int, editor_email: str) -> Dict:
        """
        Publish an article (move from editor to published status).
        Sets the editor field to the publisher's email.

        Args:
            db: Database session
            article_id: Article ID to publish
            editor_email: Email of the user publishing the article

        Returns:
            Updated article dict

        Raises:
            ValueError: If article not found or not in editor status
        """
        from models import ArticleStatus

        article = db.query(ContentArticle).filter(
            ContentArticle.id == article_id,
            ContentArticle.is_active == True
        ).first()

        if not article:
            raise ValueError("Article not found")

        if article.status != ArticleStatus.EDITOR:
            raise ValueError("Only articles in editor review can be published")

        article.status = ArticleStatus.PUBLISHED
        article.editor = editor_email
        db.commit()
        db.refresh(article)

        # Update ChromaDB metadata
        content = VectorService.get_article_content(article_id)
        if content:
            VectorService.update_article(
                article_id=article.id,
                headline=article.headline,
                content=content,
                metadata={
                    "topic": article.topic,
                    "author": article.author,
                    "editor": article.editor,
                    "keywords": article.keywords,
                    "status": article.status.value,
                    "created_at": article.created_at,
                    "updated_at": article.updated_at
                }
            )

        # Invalidate cache
        ContentCache.invalidate_article(article_id)
        ContentCache.invalidate_topic(article.topic)

        return ContentService._article_to_dict(article)

