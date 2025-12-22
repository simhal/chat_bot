#!/usr/bin/env python3
"""Management script to regenerate article resources for all published articles.

Run with: uv run python regenerate_article_resources.py
"""

import os
import sys

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import ContentArticle, User
from services.article_resource_service import ArticleResourceService
from services.vector_service import VectorService


def main():
    db = SessionLocal()
    try:
        # Get admin user - check groups for admin role
        from models import Group, user_groups
        admin_group = db.query(Group).filter(Group.name.like("%:admin")).first()
        if admin_group:
            admin_user = db.query(User).join(user_groups).filter(user_groups.c.group_id == admin_group.id).first()
        else:
            # Fallback: get the first user
            admin_user = db.query(User).first()

        if not admin_user:
            print("ERROR: No user found in database")
            return

        print(f"Using admin user: {admin_user.email}")

        # Get all published articles
        articles = db.query(ContentArticle).filter(ContentArticle.status == "published").all()
        print(f"\nFound {len(articles)} published articles")

        for article_model in articles:
            article_id = article_model.id
            print(f"\n--- Processing article {article_id}: {article_model.headline[:60]}...")

            # Check if resources already exist
            existing = ArticleResourceService.get_article_publication_resources(db, article_id)
            if existing.get("html") or existing.get("pdf"):
                print(f"  SKIPPED: Resources already exist")
                continue

            # Get article content from ChromaDB
            content = VectorService.get_article_content(article_id)
            if not content:
                print(f"  ERROR: Could not retrieve content from vector database")
                continue

            try:
                ArticleResourceService.create_article_resources(db, article_model, content, admin_user.id)
                resources = ArticleResourceService.get_article_publication_resources(db, article_id)
                print(f"  SUCCESS: HTML={resources.get('html')}, PDF={resources.get('pdf')}")
            except Exception as e:
                print(f"  ERROR: {str(e)}")

        print("\n=== Done ===")

    finally:
        db.close()


if __name__ == "__main__":
    main()
