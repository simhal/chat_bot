"""
Migration script to populate ChromaDB with existing articles from PostgreSQL.

IMPORTANT: This script must be run BEFORE migration 007 (which drops the content column).

Deployment Order:
1. Run: alembic upgrade 006  (adds author/editor fields)
2. Run: python migrate_to_chromadb.py  (migrates content to ChromaDB)
3. Run: alembic upgrade head  (drops content column from PostgreSQL)

This ensures content is safely migrated to ChromaDB before being removed from PostgreSQL.

Usage:
    python migrate_to_chromadb.py
"""

import sys
from database import SessionLocal
from models import ContentArticle
from services.vector_service import VectorService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_articles():
    """Migrate all active articles from PostgreSQL to ChromaDB."""
    db = SessionLocal()

    try:
        # Get all active articles
        articles = db.query(ContentArticle).filter(
            ContentArticle.is_active == True
        ).all()

        total = len(articles)
        logger.info(f"Found {total} active articles to migrate")

        success_count = 0
        fail_count = 0

        for i, article in enumerate(articles, 1):
            logger.info(f"Processing {i}/{total}: Article ID {article.id}")

            success = VectorService.add_article(
                article_id=article.id,
                headline=article.headline,
                content=article.content,
                metadata={
                    "topic": article.topic,
                    "author": article.author,
                    "editor": article.editor,
                    "keywords": article.keywords,
                    "created_at": article.created_at
                }
            )

            if success:
                success_count += 1
            else:
                fail_count += 1
                logger.error(f"Failed to migrate article {article.id}")

        logger.info(f"\nMigration complete!")
        logger.info(f"  Successful: {success_count}")
        logger.info(f"  Failed: {fail_count}")
        logger.info(f"  Total: {total}")

        # Show final stats
        stats = VectorService.get_collection_stats()
        logger.info(f"\nChromaDB Collection Stats:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")

    except Exception as e:
        logger.error(f"Migration error: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("ChromaDB Migration Script")
    logger.info("=" * 60)
    migrate_articles()
