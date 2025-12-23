"""Backfill HTML and image children for existing table resources.

Revision ID: 023_backfill_table_children
Revises: 022_add_html_resource_type
Create Date: 2025-12-22

This migration creates HTML and IMAGE child resources for all existing
TABLE resources that don't already have them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
import hashlib
from datetime import datetime
import os
import logging

logger = logging.getLogger("alembic")

# revision identifiers, used by Alembic.
revision: str = '023_backfill_table_children'
down_revision: Union[str, Sequence[str], None] = '022_add_html_resource_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create HTML and IMAGE children for existing table resources."""
    # Commit any pending changes to ensure the 'html' enum value from migration 022 is available
    # PostgreSQL requires new enum values to be committed before they can be used
    op.execute("COMMIT")

    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        # Import here to avoid circular imports
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

        from services.table_resource_service import TableResourceService
        from services.storage_service import get_storage
        from models import Resource, ResourceType, ResourceStatus, FileResource

        storage = get_storage()

        # Get a valid user ID for creating resources
        first_user = session.execute(text("SELECT id FROM users LIMIT 1")).fetchone()
        default_user_id = first_user[0] if first_user else None

        if not default_user_id:
            logger.error("No users found in database, cannot backfill")
            return

        # Find all table resources without HTML children
        tables_without_html = session.execute(text("""
            SELECT r.id, r.name, r.group_id, r.created_by
            FROM resources r
            WHERE r.resource_type = 'table'
            AND r.is_active = true
            AND NOT EXISTS (
                SELECT 1 FROM resources c
                WHERE c.parent_id = r.id
                AND c.resource_type = 'html'
                AND c.is_active = true
            )
        """)).fetchall()

        logger.info(f"Found {len(tables_without_html)} table resources without HTML children")

        for table_row in tables_without_html:
            table_id = table_row[0]
            table_name = table_row[1]
            group_id = table_row[2]
            # Verify user exists, otherwise use default
            parent_created_by = table_row[3]
            if parent_created_by:
                user_exists = session.execute(
                    text("SELECT 1 FROM users WHERE id = :uid"),
                    {"uid": parent_created_by}
                ).fetchone()
                created_by = parent_created_by if user_exists else default_user_id
            else:
                created_by = default_user_id

            # Get the table resource with its data
            table_resource = session.execute(text("""
                SELECT tr.column_names, tr.table_data
                FROM table_resources tr
                WHERE tr.resource_id = :table_id
            """), {"table_id": table_id}).fetchone()

            if not table_resource:
                logger.warning(f"No table data found for resource {table_id}")
                continue

            import json
            # Parse JSON strings
            columns = json.loads(table_resource[0]) if table_resource[0] else []
            table_data_json = json.loads(table_resource[1]) if table_resource[1] else {}
            data = table_data_json.get("data", [])

            if not columns:
                logger.warning(f"Table {table_id} has no columns, skipping")
                continue

            logger.info(f"Creating children for table {table_id}: {table_name}")

            # Generate HTML content
            html_content = TableResourceService._generate_sortable_table_html(
                name=table_name,
                columns=columns,
                data=data,
                description=""
            )

            # Save HTML to storage
            date_dir = datetime.now().strftime("%Y/%m")
            html_bytes = html_content.encode('utf-8')
            html_filename = f"{uuid.uuid4().hex}.html"
            html_path = f"{date_dir}/{html_filename}"

            # Create safe filename
            safe_name = "".join(
                c for c in table_name if c.isalnum() or c in (' ', '-', '_')
            ).rstrip()
            safe_name = safe_name.replace(' ', '_')[:50]

            if not storage.save_file_with_metadata(
                html_path, html_bytes, "text/html",
                {"table_id": str(table_id), "type": "table_html"}
            ):
                logger.error(f"Failed to save HTML for table {table_id}")
                continue

            # Generate hash_id for HTML resource
            html_hash_id = hashlib.sha256(f"html_{table_id}_{uuid.uuid4().hex}".encode()).hexdigest()[:12]

            # Create HTML child resource
            session.execute(text("""
                INSERT INTO resources (
                    hash_id, resource_type, name, description, group_id,
                    created_by, modified_by, status, is_active, parent_id,
                    created_at, updated_at
                ) VALUES (
                    :hash_id, 'html', :name, :description, :group_id,
                    :created_by, :modified_by, 'published', true, :parent_id,
                    NOW(), NOW()
                )
                RETURNING id
            """), {
                "hash_id": html_hash_id,
                "name": f"{table_name} - Interactive",
                "description": "Interactive HTML version of table with sorting",
                "group_id": group_id,
                "created_by": created_by,
                "modified_by": created_by,
                "parent_id": table_id
            })

            html_resource_id = session.execute(text("""
                SELECT id FROM resources WHERE hash_id = :hash_id
            """), {"hash_id": html_hash_id}).fetchone()[0]

            # Create file resource for HTML
            session.execute(text("""
                INSERT INTO file_resources (
                    resource_id, filename, file_path, file_size, mime_type, checksum
                ) VALUES (
                    :resource_id, :filename, :file_path, :file_size, :mime_type, :checksum
                )
            """), {
                "resource_id": html_resource_id,
                "filename": f"{safe_name}_table.html",
                "file_path": html_path,
                "file_size": len(html_bytes),
                "mime_type": "text/html",
                "checksum": hashlib.sha256(html_bytes).hexdigest()
            })

            # Generate image
            from services.table_resource_service import _generate_table_image
            image_bytes = _generate_table_image(
                name=table_name,
                columns=columns,
                data=data
            )

            if image_bytes:
                image_filename = f"{uuid.uuid4().hex}.png"
                image_path = f"{date_dir}/{image_filename}"

                if storage.save_file_with_metadata(
                    image_path, image_bytes, "image/png",
                    {"table_id": str(table_id), "type": "table_image"}
                ):
                    # Generate hash_id for image resource
                    image_hash_id = hashlib.sha256(f"img_{table_id}_{uuid.uuid4().hex}".encode()).hexdigest()[:12]

                    # Create image child resource
                    session.execute(text("""
                        INSERT INTO resources (
                            hash_id, resource_type, name, description, group_id,
                            created_by, modified_by, status, is_active, parent_id,
                            created_at, updated_at
                        ) VALUES (
                            :hash_id, 'image', :name, :description, :group_id,
                            :created_by, :modified_by, 'published', true, :parent_id,
                            NOW(), NOW()
                        )
                        RETURNING id
                    """), {
                        "hash_id": image_hash_id,
                        "name": f"{table_name} - Image",
                        "description": "Static image of table for PDF embedding",
                        "group_id": group_id,
                        "created_by": created_by,
                        "modified_by": created_by,
                        "parent_id": table_id
                    })

                    image_resource_id = session.execute(text("""
                        SELECT id FROM resources WHERE hash_id = :hash_id
                    """), {"hash_id": image_hash_id}).fetchone()[0]

                    # Create file resource for image
                    session.execute(text("""
                        INSERT INTO file_resources (
                            resource_id, filename, file_path, file_size, mime_type, checksum
                        ) VALUES (
                            :resource_id, :filename, :file_path, :file_size, :mime_type, :checksum
                        )
                    """), {
                        "resource_id": image_resource_id,
                        "filename": f"{safe_name}_table.png",
                        "file_path": image_path,
                        "file_size": len(image_bytes),
                        "mime_type": "image/png",
                        "checksum": hashlib.sha256(image_bytes).hexdigest()
                    })

                    logger.info(f"Created HTML ({html_resource_id}) and image ({image_resource_id}) for table {table_id}")
                else:
                    logger.warning(f"Failed to save image for table {table_id}")
            else:
                logger.warning(f"Failed to generate image for table {table_id}")

        session.commit()
        logger.info("Backfill complete")

    except Exception as e:
        session.rollback()
        logger.error(f"Error during backfill: {e}")
        raise
    finally:
        session.close()


def downgrade() -> None:
    """Remove backfilled HTML and IMAGE children.

    Note: This would need to identify which resources were created by this
    migration, which is complex. For safety, we leave this as a no-op.
    """
    pass
