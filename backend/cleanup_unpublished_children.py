"""
Cleanup script to remove child resources for non-published articles and tables.

This script:
1. Finds all ARTICLE resources that are not published and deletes their HTML/PDF children
2. Finds all TABLE resources that are not published and deletes their HTML/IMAGE children
3. Cleans up associated files from storage

Run with: python cleanup_unpublished_children.py
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from models import Resource, ResourceType, ResourceStatus, FileResource
from services.storage_service import get_storage

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def cleanup_unpublished_children():
    """Remove child resources for non-published articles and tables."""

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    storage = get_storage()

    try:
        # Find all non-published ARTICLE resources with children
        print("Finding non-published ARTICLE resources with children...")
        article_parents = session.execute(text("""
            SELECT DISTINCT r.id, r.name, r.status
            FROM resources r
            WHERE r.resource_type = 'article'
            AND r.status != 'published'
            AND r.is_active = true
            AND EXISTS (
                SELECT 1 FROM resources c
                WHERE c.parent_id = r.id
                AND c.is_active = true
            )
        """)).fetchall()

        print(f"Found {len(article_parents)} non-published articles with children")

        article_children_deleted = 0
        for parent in article_parents:
            parent_id, name, status = parent
            print(f"  Processing article '{name}' (id={parent_id}, status={status})")

            # Find children (HTML/TEXT and PDF)
            children = session.query(Resource).filter(
                Resource.parent_id == parent_id,
                Resource.is_active == True,
                Resource.resource_type.in_([ResourceType.TEXT, ResourceType.PDF, ResourceType.HTML])
            ).all()

            for child in children:
                print(f"    Deleting child: {child.name} (type={child.resource_type.value})")

                # Delete file from storage if exists
                if child.file_resource and child.file_resource.file_path:
                    try:
                        storage.delete_file(child.file_resource.file_path)
                        print(f"      Deleted file: {child.file_resource.file_path}")
                    except Exception as e:
                        print(f"      Warning: Could not delete file: {e}")

                # Mark as inactive
                child.is_active = False
                article_children_deleted += 1

        # Find all non-published TABLE resources with children
        print("\nFinding non-published TABLE resources with children...")
        table_parents = session.execute(text("""
            SELECT DISTINCT r.id, r.name, r.status
            FROM resources r
            WHERE r.resource_type = 'table'
            AND r.status != 'published'
            AND r.is_active = true
            AND EXISTS (
                SELECT 1 FROM resources c
                WHERE c.parent_id = r.id
                AND c.is_active = true
            )
        """)).fetchall()

        print(f"Found {len(table_parents)} non-published tables with children")

        table_children_deleted = 0
        for parent in table_parents:
            parent_id, name, status = parent
            print(f"  Processing table '{name}' (id={parent_id}, status={status})")

            # Find children (HTML and IMAGE)
            children = session.query(Resource).filter(
                Resource.parent_id == parent_id,
                Resource.is_active == True,
                Resource.resource_type.in_([ResourceType.HTML, ResourceType.IMAGE])
            ).all()

            for child in children:
                print(f"    Deleting child: {child.name} (type={child.resource_type.value})")

                # Delete file from storage if exists
                if child.file_resource and child.file_resource.file_path:
                    try:
                        storage.delete_file(child.file_resource.file_path)
                        print(f"      Deleted file: {child.file_resource.file_path}")
                    except Exception as e:
                        print(f"      Warning: Could not delete file: {e}")

                # Mark as inactive
                child.is_active = False
                table_children_deleted += 1

        # Commit changes
        session.commit()

        print("\n" + "=" * 50)
        print("CLEANUP COMPLETE")
        print("=" * 50)
        print(f"Article children deleted: {article_children_deleted}")
        print(f"Table children deleted: {table_children_deleted}")
        print(f"Total children deleted: {article_children_deleted + table_children_deleted}")

    except Exception as e:
        session.rollback()
        print(f"Error during cleanup: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    print("=" * 50)
    print("CLEANUP UNPUBLISHED CHILD RESOURCES")
    print("=" * 50)
    print()

    confirm = input("This will delete child resources for non-published articles and tables. Continue? (yes/no): ")
    if confirm.lower() == 'yes':
        cleanup_unpublished_children()
    else:
        print("Aborted.")
