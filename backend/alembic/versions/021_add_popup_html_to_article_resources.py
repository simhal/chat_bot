"""Add popup HTML files to existing article resources.

Revision ID: 021_popup_html
Revises: 020_add_article_priority_and_topic_order
Create Date: 2024-12-21

This is a data migration that generates popup HTML files for all existing
ARTICLE type resources that don't have a FileResource attached.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy import text
import os
import uuid
import hashlib
from datetime import datetime


# revision identifiers, used by Alembic.
revision = '021_popup_html'
down_revision = '020_add_article_priority'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Generate popup HTML for existing article resources."""
    # Import here to avoid circular imports
    from models import Resource, ResourceType, FileResource, TextResource, ContentArticle, article_resources
    from services.article_resource_service import ArticleResourceService
    from services.storage_service import get_storage

    bind = op.get_bind()
    session = Session(bind=bind)
    storage = get_storage()

    try:
        # Find all ARTICLE type resources that don't have a FileResource
        article_resources_without_file = session.execute(text("""
            SELECT r.id, r.hash_id
            FROM resources r
            LEFT JOIN file_resources fr ON r.id = fr.resource_id
            WHERE r.resource_type = 'article'
            AND r.is_active = true
            AND fr.id IS NULL
        """)).fetchall()

        print(f"Found {len(article_resources_without_file)} article resources without popup HTML")

        base_url = os.environ.get("API_BASE_URL", "")
        date_dir = datetime.now().strftime("%Y/%m")

        for row in article_resources_without_file:
            resource_id = row[0]
            resource_hash_id = row[1]

            # Get the resource
            resource = session.query(Resource).filter(Resource.id == resource_id).first()
            if not resource:
                print(f"  Skipping resource {resource_id}: not found")
                continue

            # Get markdown content from TextResource
            text_resource = session.query(TextResource).filter(
                TextResource.resource_id == resource_id
            ).first()

            if not text_resource:
                print(f"  Skipping resource {resource_id}: no text content")
                continue

            content = text_resource.content

            # Find linked article
            article_link = session.execute(
                article_resources.select().where(
                    article_resources.c.resource_id == resource_id
                )
            ).first()

            if not article_link:
                print(f"  Skipping resource {resource_id}: no linked article")
                continue

            article = session.query(ContentArticle).filter(
                ContentArticle.id == article_link.article_id
            ).first()

            if not article:
                print(f"  Skipping resource {resource_id}: article not found")
                continue

            # Get child resources for PDF and HTML links
            children = session.query(Resource).filter(
                Resource.parent_id == resource_id,
                Resource.is_active == True
            ).all()

            pdf_hash_id = None
            html_hash_id = None
            for child in children:
                if child.resource_type == ResourceType.PDF:
                    pdf_hash_id = child.hash_id
                elif child.resource_type == ResourceType.TEXT:
                    html_hash_id = child.hash_id

            # Generate popup HTML
            created_at_str = article.created_at.isoformat() if article.created_at else ""

            popup_html = ArticleResourceService._generate_article_popup_html(
                article_id=article.id,
                headline=article.headline,
                content=content,
                topic=article.topic or "",
                created_at=created_at_str,
                keywords=article.keywords,
                readership_count=article.readership_count or 0,
                rating=article.rating,
                rating_count=article.rating_count or 0,
                author=article.author,
                editor=article.editor,
                pdf_hash_id=pdf_hash_id,
                html_hash_id=html_hash_id,
                db=session,
                base_url=base_url
            )

            # Save popup HTML to storage
            popup_bytes = popup_html.encode('utf-8')
            popup_filename = f"{uuid.uuid4().hex}.html"
            popup_path = f"{date_dir}/{popup_filename}"

            # Create safe filename for the article
            safe_headline = "".join(
                c for c in article.headline if c.isalnum() or c in (' ', '-', '_')
            ).rstrip()
            safe_headline = safe_headline.replace(' ', '_')[:50]

            if storage.save_file_with_metadata(
                popup_path, popup_bytes, "text/html",
                {"article_id": str(article.id), "type": "article_popup"}
            ):
                # Create FileResource for the popup HTML
                file_resource = FileResource(
                    resource_id=resource_id,
                    filename=f"{safe_headline}.html",
                    file_path=popup_path,
                    file_size=len(popup_bytes),
                    mime_type="text/html",
                    checksum=hashlib.sha256(popup_bytes).hexdigest()
                )
                session.add(file_resource)
                print(f"  Created popup HTML for resource {resource_id} ({article.headline[:30]}...)")
            else:
                print(f"  Failed to save popup HTML for resource {resource_id}")

        session.commit()
        print("Migration complete!")

    except Exception as e:
        session.rollback()
        print(f"Migration failed: {e}")
        raise


def downgrade() -> None:
    """Remove popup HTML files from article resources."""
    # This would require deleting the FileResource entries and S3 files
    # For safety, we don't automatically delete files
    print("Downgrade: FileResource entries for article popups should be manually removed if needed")
    pass
