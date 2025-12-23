"""Service for managing article resources on publish/recall/purge."""

import os
import uuid
import hashlib
import html
import markdown2
from datetime import datetime
from io import BytesIO
from typing import Optional, Tuple, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging

import re

from models import (
    Resource, ResourceType, ResourceStatus, FileResource, TextResource,
    ContentArticle, article_resources
)
from services.pdf_service import PDFService
from services.storage_service import get_storage

logger = logging.getLogger("uvicorn")


def _get_resource_by_hash_id_simple(db: Session, hash_id: str) -> Optional[Dict[str, Any]]:
    """Get basic resource info by hash_id for resource link processing."""
    resource = db.query(Resource).filter(Resource.hash_id == hash_id).first()
    if resource:
        return {
            'hash_id': resource.hash_id,
            'name': resource.name,
            'resource_type': resource.resource_type.value if resource.resource_type else 'unknown'
        }
    return None


class ArticleResourceService:
    """
    Service for creating, deleting, and managing article publication resources.

    On publish: Creates parent ARTICLE resource with HTML and PDF children
    On recall/purge: Deletes all article resources and children
    """

    @staticmethod
    def _get_resource_embed_html(
        hash_id: str,
        name: str,
        resource_type: str,
        base_url: str,
        db: Session = None
    ) -> str:
        """
        Generate HTML embed for a resource based on its type.

        Args:
            hash_id: Resource hash_id
            name: Resource display name
            resource_type: Type of resource (image, pdf, text, table, etc.)
            base_url: Base URL for resource content
            db: Database session (needed for table embeds to find HTML child)

        Returns:
            HTML string for embedding the resource
        """
        content_url = f"{base_url}/api/resources/content/{hash_id}"
        safe_name = html.escape(name)

        if resource_type == 'image':
            return f'<img src="{content_url}" alt="{safe_name}" style="max-width:100%;height:auto;border-radius:8px;margin:1rem 0;box-shadow:0 2px 8px rgba(0,0,0,0.1);" />'

        elif resource_type == 'pdf':
            return f'''<div style="padding:1rem;background:#f8f9fa;border-radius:8px;border-left:4px solid #3b82f6;margin:1rem 0;">
                <a href="{content_url}" target="_blank" style="color:#3b82f6;text-decoration:none;font-weight:500;">{safe_name}</a>
            </div>'''

        elif resource_type == 'table':
            # For tables, embed as simple HTML table (no interactivity)
            if db:
                table_resource = db.query(Resource).filter(Resource.hash_id == hash_id).first()
                if table_resource and table_resource.table_resource:
                    columns = table_resource.table_resource.columns or []
                    data = table_resource.table_resource.data or []
                    return ArticleResourceService._generate_simple_table_html(safe_name, columns, data)

            # Fallback: link to table resource
            return f'''<div style="border:1px solid #e5e7eb;border-radius:8px;padding:1rem;margin:1rem 0;background:#f9fafb;">
                <a href="{content_url}" target="_blank" style="color:#3b82f6;text-decoration:none;font-weight:500;">{safe_name}</a>
            </div>'''

        elif resource_type == 'text':
            return f'''<blockquote style="background:#f8f9fa;border-left:4px solid #6b7280;padding:1rem;margin:1rem 0;font-style:normal;">
                <cite style="display:block;font-weight:600;margin-bottom:0.5rem;font-style:normal;">{safe_name}</cite>
                <a href="{content_url}" target="_blank" style="color:#3b82f6;text-decoration:none;">View Full Text</a>
            </blockquote>'''

        else:
            return f'''<a href="{content_url}" target="_blank" style="color:#3b82f6;text-decoration:none;padding:0.25rem 0.5rem;background:#eff6ff;border-radius:4px;">{safe_name}</a>'''

    @staticmethod
    def _generate_simple_table_html(name: str, columns: list, data: list) -> str:
        """
        Generate a simple HTML table from table data.
        No interactivity - just static HTML table for article embedding.

        Args:
            name: Table caption/title
            columns: List of column names
            data: List of rows (each row is a list of values)

        Returns:
            Simple styled HTML table
        """
        safe_name = html.escape(name)

        # Generate header cells
        header_cells = ''.join(
            f'<th style="padding:0.5rem 0.75rem;text-align:left;font-weight:600;border-bottom:2px solid #e5e7eb;background:#f9fafb;">{html.escape(str(col))}</th>'
            for col in columns
        )

        # Generate data rows
        rows_html = ''
        for i, row in enumerate(data):
            bg_color = '#ffffff' if i % 2 == 0 else '#f9fafb'
            cells = ''.join(
                f'<td style="padding:0.5rem 0.75rem;border-bottom:1px solid #e5e7eb;">{html.escape(str(cell)) if cell is not None else ""}</td>'
                for cell in row
            )
            rows_html += f'<tr style="background:{bg_color};">{cells}</tr>\n'

        return f'''<div style="margin:1rem 0;overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;font-size:0.875rem;border:1px solid #e5e7eb;border-radius:8px;">
                <caption style="text-align:left;font-weight:600;padding:0.75rem;background:#f3f4f6;border:1px solid #e5e7eb;border-bottom:none;border-radius:8px 8px 0 0;">{safe_name}</caption>
                <thead>
                    <tr>{header_cells}</tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>'''

    @staticmethod
    def _process_resource_links(content: str, db: Session, base_url: str = "") -> str:
        """
        Process [name](resource:hash_id) links in markdown content.

        Replaces resource links with appropriate HTML embeds before markdown conversion.

        Args:
            content: Markdown content with resource links
            db: Database session for looking up resources
            base_url: Base URL for resource content (e.g., https://api.example.com)

        Returns:
            Content with resource links replaced by HTML embeds
        """
        # Pattern: [name](resource:hash_id)
        pattern = r'\[([^\]]+)\]\(resource:([a-zA-Z0-9]+)\)'

        def replace_resource(match):
            name = match.group(1)
            hash_id = match.group(2)

            # Look up resource to get type
            resource_data = _get_resource_by_hash_id_simple(db, hash_id)

            if not resource_data:
                # Resource not found - leave as simple text link
                safe_name = html.escape(name)
                return f'<a href="{base_url}/api/resources/content/{hash_id}" target="_blank">{safe_name}</a>'

            resource_type = resource_data.get('resource_type', 'unknown')
            return ArticleResourceService._get_resource_embed_html(
                hash_id, name, resource_type, base_url, db
            )

        return re.sub(pattern, replace_resource, content)

    @staticmethod
    def _generate_article_html(
        headline: str,
        content: str,
        topic: str,
        created_at: str,
        keywords: Optional[str] = None,
        db: Session = None,
        base_url: str = ""
    ) -> str:
        """
        Convert markdown article to embeddable HTML.

        Args:
            headline: Article headline
            content: Markdown content
            topic: Topic slug/name
            created_at: Publication date string
            keywords: Optional comma-separated keywords
            db: Database session for resolving resource links
            base_url: Base URL for resource content

        Returns:
            Embeddable HTML document
        """
        # Process resource links before markdown conversion
        if db:
            content = ArticleResourceService._process_resource_links(content, db, base_url)

        # Convert markdown to HTML using markdown2
        html_content = markdown2.markdown(
            content,
            extras=["fenced-code-blocks", "tables", "header-ids", "strike"]
        )

        # Escape headline for safe HTML insertion
        safe_headline = html.escape(headline)
        topic_display = html.escape(topic.replace('_', ' ').title())

        # Format date nicely if possible
        try:
            if isinstance(created_at, str) and created_at:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                date_display = dt.strftime("%B %d, %Y")
            else:
                date_display = str(created_at) if created_at else ""
        except:
            date_display = str(created_at) if created_at else ""

        keywords_html = ""
        if keywords:
            safe_keywords = html.escape(keywords)
            keywords_html = f'<div class="keywords">Keywords: {safe_keywords}</div>'

        # Create embeddable HTML with inline styles
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_headline}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            color: #1a1a1a;
        }}
        h1 {{
            color: #1a1a1a;
            margin-bottom: 0.5rem;
            font-size: 2rem;
            line-height: 1.2;
        }}
        h2, h3, h4, h5, h6 {{
            color: #374151;
            margin-top: 1.5rem;
            margin-bottom: 0.75rem;
        }}
        .meta {{
            color: #6b7280;
            font-size: 0.875rem;
            margin-bottom: 1.5rem;
        }}
        .topic {{
            display: inline-block;
            background: #3b82f6;
            color: white;
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
            margin-bottom: 0.75rem;
        }}
        article {{
            margin-top: 1rem;
        }}
        article p {{
            margin-bottom: 1rem;
        }}
        article ul, article ol {{
            margin-bottom: 1rem;
            padding-left: 1.5rem;
        }}
        article li {{
            margin-bottom: 0.5rem;
        }}
        article blockquote {{
            border-left: 4px solid #e5e7eb;
            padding-left: 1rem;
            margin: 1rem 0;
            color: #6b7280;
            font-style: italic;
        }}
        article code {{
            background: #f3f4f6;
            padding: 0.125rem 0.375rem;
            border-radius: 4px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.875em;
        }}
        article pre {{
            background: #1f2937;
            color: #f9fafb;
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            margin: 1rem 0;
        }}
        article pre code {{
            background: transparent;
            padding: 0;
            color: inherit;
        }}
        article table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
        }}
        article th, article td {{
            border: 1px solid #e5e7eb;
            padding: 0.5rem 0.75rem;
            text-align: left;
        }}
        article th {{
            background: #f9fafb;
            font-weight: 600;
        }}
        article a {{
            color: #3b82f6;
            text-decoration: none;
        }}
        article a:hover {{
            text-decoration: underline;
        }}
        article img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
        }}
        .keywords {{
            color: #6b7280;
            font-size: 0.875rem;
            font-style: italic;
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #e5e7eb;
        }}
    </style>
</head>
<body>
    <span class="topic">{topic_display}</span>
    <h1>{safe_headline}</h1>
    <div class="meta">Published: {date_display}</div>
    <article>{html_content}</article>
    {keywords_html}
</body>
</html>"""

    @staticmethod
    def _generate_article_popup_html(
        article_id: int,
        headline: str,
        content: str,
        topic: str,
        created_at: str,
        keywords: Optional[str] = None,
        readership_count: int = 0,
        rating: Optional[float] = None,
        rating_count: int = 0,
        author: Optional[str] = None,
        editor: Optional[str] = None,
        pdf_hash_id: Optional[str] = None,
        html_hash_id: Optional[str] = None,
        db: Session = None,
        base_url: str = ""
    ) -> str:
        """
        Generate a complete popup HTML that matches the frontend article popup.

        This HTML can be displayed in an iframe or new tab, showing the article
        exactly as it appears in the main navigation popup.

        Args:
            article_id: Article ID for rating link
            headline: Article headline
            content: Markdown content
            topic: Topic slug/name
            created_at: Publication date string
            keywords: Optional comma-separated keywords
            readership_count: Number of reads
            rating: Average rating
            rating_count: Number of ratings
            author: Article author
            editor: Article editor
            pdf_hash_id: Hash ID of PDF resource for download link
            html_hash_id: Hash ID of HTML resource for view link
            db: Database session for resolving resource links
            base_url: Base URL for resource content

        Returns:
            Complete popup HTML document
        """
        # Process resource links before markdown conversion
        processed_content = content
        if db:
            processed_content = ArticleResourceService._process_resource_links(content, db, base_url)

        # Convert markdown to HTML
        html_content = markdown2.markdown(
            processed_content,
            extras=["fenced-code-blocks", "tables", "header-ids", "strike"]
        )

        # Escape values for safe HTML insertion
        safe_headline = html.escape(headline)
        topic_display = html.escape(topic.replace('_', ' ').title())

        # Format date
        try:
            if isinstance(created_at, str) and created_at:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                date_display = dt.strftime("%B %d, %Y")
            else:
                date_display = str(created_at) if created_at else ""
        except:
            date_display = str(created_at) if created_at else ""

        # Build metadata items
        meta_items = [f"<span><strong>Published:</strong> {date_display}</span>"]
        meta_items.append(f"<span><strong>Readership:</strong> {readership_count}</span>")
        if rating:
            meta_items.append(f"<span><strong>Rating:</strong> {rating:.1f}/5 ({rating_count} ratings)</span>")
        if author:
            meta_items.append(f"<span><strong>Author:</strong> {html.escape(author)}</span>")
        if editor:
            meta_items.append(f"<span><strong>Editor:</strong> {html.escape(editor)}</span>")
        meta_html = " ".join(meta_items)

        # Keywords section
        keywords_html = ""
        if keywords:
            safe_keywords = html.escape(keywords)
            keywords_html = f'<div class="modal-keywords"><strong>Keywords:</strong> {safe_keywords}</div>'

        # Action buttons - use history.back() to return to calling page
        action_buttons = ['<button onclick="goBack()" class="back-btn">← Back</button>']
        if pdf_hash_id:
            action_buttons.append(f'<a href="{base_url}/api/resources/content/{pdf_hash_id}" download class="download-pdf-btn">Download PDF</a>')
        actions_html = "\n                    ".join(action_buttons)

        # Content section - use iframe to embed HTML child resource, or fallback to generated content
        if html_hash_id:
            content_html = f'<iframe id="article-frame" src="{base_url}/api/resources/content/{html_hash_id}" style="width:100%;border:none;min-height:500px;"></iframe>'
        else:
            content_html = html_content

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_headline}</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f5f5;
            min-height: 100vh;
        }}
        .modal-container {{
            background: white;
            max-width: 900px;
            margin: 0 auto;
            min-height: 100vh;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }}
        .modal-header-fixed {{
            position: sticky;
            top: 0;
            background: white;
            border-bottom: 1px solid #e5e7eb;
            z-index: 100;
        }}
        .modal-title-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            padding: 1.5rem 2rem 1rem;
        }}
        .modal-title-row h2 {{
            font-size: 1.5rem;
            color: #1a1a1a;
            flex: 1;
            margin-right: 1rem;
            line-height: 1.3;
        }}
        .topic-badge {{
            display: inline-block;
            background: #3b82f6;
            color: white;
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
            margin-bottom: 0.5rem;
        }}
        .close-btn {{
            background: none;
            border: none;
            font-size: 1.75rem;
            color: #6b7280;
            cursor: pointer;
            padding: 0;
            line-height: 1;
        }}
        .close-btn:hover {{
            color: #1a1a1a;
        }}
        .modal-actions-fixed {{
            display: flex;
            gap: 0.75rem;
            padding: 0 2rem 1rem;
            flex-wrap: wrap;
        }}
        .modal-actions-fixed button,
        .modal-actions-fixed a {{
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-size: 0.875rem;
            font-weight: 500;
            text-decoration: none;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
        }}
        .back-btn {{
            background: #f3f4f6;
            color: #374151;
            border: 1px solid #d1d5db;
        }}
        .back-btn:hover {{
            background: #e5e7eb;
        }}
        .download-pdf-btn {{
            background: #3b82f6;
            color: white;
            border: none;
        }}
        .download-pdf-btn:hover {{
            background: #2563eb;
        }}
        .modal-body {{
            padding: 1.5rem 2rem 2rem;
        }}
        .modal-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            color: #6b7280;
            font-size: 0.875rem;
            margin-bottom: 1rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid #f3f4f6;
        }}
        .modal-keywords {{
            color: #6b7280;
            font-size: 0.875rem;
            margin-bottom: 1.5rem;
        }}
        .modal-content {{
            color: #1a1a1a;
            line-height: 1.7;
        }}
        .modal-content h1, .modal-content h2, .modal-content h3,
        .modal-content h4, .modal-content h5, .modal-content h6 {{
            color: #1a1a1a;
            margin-top: 1.5rem;
            margin-bottom: 0.75rem;
        }}
        .modal-content p {{
            margin-bottom: 1rem;
        }}
        .modal-content ul, .modal-content ol {{
            margin-bottom: 1rem;
            padding-left: 1.5rem;
        }}
        .modal-content li {{
            margin-bottom: 0.5rem;
        }}
        .modal-content blockquote {{
            border-left: 4px solid #e5e7eb;
            padding-left: 1rem;
            margin: 1rem 0;
            color: #6b7280;
            font-style: italic;
        }}
        .modal-content code {{
            background: #f3f4f6;
            padding: 0.125rem 0.375rem;
            border-radius: 4px;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.875em;
        }}
        .modal-content pre {{
            background: #1f2937;
            color: #f9fafb;
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            margin: 1rem 0;
        }}
        .modal-content pre code {{
            background: transparent;
            padding: 0;
            color: inherit;
        }}
        .modal-content table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
        }}
        .modal-content th, .modal-content td {{
            border: 1px solid #e5e7eb;
            padding: 0.5rem 0.75rem;
            text-align: left;
        }}
        .modal-content th {{
            background: #f9fafb;
            font-weight: 600;
        }}
        .modal-content a {{
            color: #3b82f6;
            text-decoration: none;
        }}
        .modal-content a:hover {{
            text-decoration: underline;
        }}
        .modal-content img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            margin: 1rem 0;
        }}
    </style>
</head>
<body>
    <div class="modal-container">
        <div class="modal-header-fixed">
            <div class="modal-title-row">
                <div>
                    <span class="topic-badge">{topic_display}</span>
                    <h2>{safe_headline}</h2>
                </div>
                <button class="close-btn" onclick="goBack()">×</button>
            </div>
            <div class="modal-actions-fixed">
                {actions_html}
            </div>
        </div>
        <div class="modal-body">
            <div class="modal-meta">
                {meta_html}
            </div>
            {keywords_html}
            <div class="modal-content">
                {content_html}
            </div>
        </div>
    </div>
    <script>
        function goBack() {{
            // Try to go back in history
            if (window.history.length > 1) {{
                window.history.back();
            }} else {{
                // If no history, try to close the window (works if opened via JS)
                window.close();
                // If close didn't work, redirect to home
                setTimeout(function() {{
                    window.location.href = '/';
                }}, 100);
            }}
        }}
    </script>
</body>
</html>"""

    @staticmethod
    def create_article_resources(
        db: Session,
        article: ContentArticle,
        content: str,
        editor_user_id: int
    ) -> Tuple[Optional[Resource], Optional[Resource], Optional[Resource]]:
        """
        Create parent ARTICLE resource with HTML and PDF children.

        The parent ARTICLE resource stores a popup HTML file in S3 that can be
        served directly to display the article in a popup/iframe format.

        If resources already exist for this article (re-publish), they are deleted first.

        Args:
            db: Database session
            article: ContentArticle being published
            content: Article content from ChromaDB (markdown)
            editor_user_id: User ID of the editor publishing

        Returns:
            Tuple of (parent_resource, html_resource, pdf_resource) or (None, None, None) on error
        """
        storage = get_storage()

        try:
            # First, delete any existing article resources (for re-publish)
            ArticleResourceService.delete_article_resources(db, article.id)

            # Get topic for display
            topic = article.topic or ""
            created_at_str = article.created_at.isoformat() if article.created_at else ""
            base_url = os.environ.get("API_BASE_URL", "")
            date_dir = datetime.now().strftime("%Y/%m")

            # Create safe filename base
            safe_headline = "".join(
                c for c in article.headline if c.isalnum() or c in (' ', '-', '_')
            ).rstrip()
            safe_headline = safe_headline.replace(' ', '_')[:50]

            # 1. Create parent ARTICLE resource first (to get ID for children)
            parent_resource = Resource(
                resource_type=ResourceType.ARTICLE,
                name=article.headline,
                description=f"Published article: {article.headline}",
                group_id=None,
                created_by=editor_user_id,
                modified_by=editor_user_id,
                status=ResourceStatus.PUBLISHED,
                is_active=True,
                parent_id=None
            )
            db.add(parent_resource)
            db.flush()  # Get parent ID and hash_id

            # 2. Create HTML child resource (for "View as HTML" button)
            html_content = ArticleResourceService._generate_article_html(
                headline=article.headline,
                content=content,
                topic=topic,
                created_at=created_at_str,
                keywords=article.keywords,
                db=db,
                base_url=base_url
            )

            html_resource = Resource(
                resource_type=ResourceType.HTML,
                name=f"{article.headline} - HTML",
                description="HTML version of published article",
                group_id=None,
                created_by=editor_user_id,
                modified_by=editor_user_id,
                status=ResourceStatus.PUBLISHED,
                is_active=True,
                parent_id=parent_resource.id
            )
            db.add(html_resource)
            db.flush()

            html_text = TextResource(
                resource_id=html_resource.id,
                content=html_content,
                encoding='utf-8',
                char_count=len(html_content),
                word_count=len(html_content.split())
            )
            db.add(html_text)
            db.flush()

            # 3. Create PDF child resource
            pdf_buffer = PDFService.generate_article_pdf(
                headline=article.headline,
                content=content,
                topic=topic,
                created_at=created_at_str,
                keywords=article.keywords,
                readership_count=article.readership_count or 0,
                rating=article.rating,
                rating_count=article.rating_count or 0,
                base_url=base_url,
                db=db
            )

            pdf_bytes = pdf_buffer.getvalue()
            pdf_filename = f"{uuid.uuid4().hex}.pdf"
            pdf_path = f"{date_dir}/{pdf_filename}"
            download_filename = f"{safe_headline}.pdf"

            if not storage.save_file_with_metadata(
                pdf_path, pdf_bytes, "application/pdf",
                {"article_id": str(article.id), "type": "article_pdf"}
            ):
                raise Exception("Failed to save PDF to storage")

            pdf_resource = Resource(
                resource_type=ResourceType.PDF,
                name=f"{article.headline} - PDF",
                description="PDF version of published article",
                group_id=None,
                created_by=editor_user_id,
                modified_by=editor_user_id,
                status=ResourceStatus.PUBLISHED,
                is_active=True,
                parent_id=parent_resource.id
            )
            db.add(pdf_resource)
            db.flush()

            pdf_file_resource = FileResource(
                resource_id=pdf_resource.id,
                filename=download_filename,
                file_path=pdf_path,
                file_size=len(pdf_bytes),
                mime_type="application/pdf",
                checksum=hashlib.sha256(pdf_bytes).hexdigest()
            )
            db.add(pdf_file_resource)
            db.flush()

            # 4. Generate popup HTML with references to child resources
            popup_html = ArticleResourceService._generate_article_popup_html(
                article_id=article.id,
                headline=article.headline,
                content=content,
                topic=topic,
                created_at=created_at_str,
                keywords=article.keywords,
                readership_count=article.readership_count or 0,
                rating=article.rating,
                rating_count=article.rating_count or 0,
                author=article.author,
                editor=article.editor,
                pdf_hash_id=pdf_resource.hash_id,
                html_hash_id=html_resource.hash_id,
                db=db,
                base_url=base_url
            )

            # 5. Save popup HTML to storage
            popup_bytes = popup_html.encode('utf-8')
            popup_filename = f"{uuid.uuid4().hex}.html"
            popup_path = f"{date_dir}/{popup_filename}"

            if not storage.save_file_with_metadata(
                popup_path, popup_bytes, "text/html",
                {"article_id": str(article.id), "type": "article_popup"}
            ):
                raise Exception("Failed to save popup HTML to storage")

            # 6. Add FileResource to parent ARTICLE resource
            parent_file_resource = FileResource(
                resource_id=parent_resource.id,
                filename=f"{safe_headline}.html",
                file_path=popup_path,
                file_size=len(popup_bytes),
                mime_type="text/html",
                checksum=hashlib.sha256(popup_bytes).hexdigest()
            )
            db.add(parent_file_resource)

            # 7. Link parent resource to article
            db.execute(
                article_resources.insert().values(
                    article_id=article.id,
                    resource_id=parent_resource.id
                )
            )

            db.commit()
            db.refresh(parent_resource)
            db.refresh(html_resource)
            db.refresh(pdf_resource)

            logger.info(
                f"Created article resources for article {article.id}: "
                f"parent={parent_resource.id} (hash={parent_resource.hash_id}), "
                f"html={html_resource.id} (hash={html_resource.hash_id}), "
                f"pdf={pdf_resource.id} (hash={pdf_resource.hash_id})"
            )

            return parent_resource, html_resource, pdf_resource

        except Exception as e:
            db.rollback()
            logger.error(f"Error creating article resources for article {article.id}: {e}")
            return None, None, None

    @staticmethod
    def delete_article_resources(db: Session, article_id: int) -> int:
        """
        Delete all ARTICLE resources and their children for an article.

        Uses cascade delete via parent_id relationship, but we handle
        file cleanup manually for PDF resources.

        Args:
            db: Database session
            article_id: ContentArticle ID

        Returns:
            Number of resources deleted
        """
        storage = get_storage()
        deleted_count = 0

        # Find all ARTICLE type resources linked to this article
        article_resource_links = db.execute(
            article_resources.select().where(
                article_resources.c.article_id == article_id
            )
        ).fetchall()

        for link in article_resource_links:
            resource_id = link.resource_id
            resource = db.query(Resource).filter(Resource.id == resource_id).first()

            if resource and resource.resource_type == ResourceType.ARTICLE:
                # Clean up the popup HTML file for the ARTICLE resource
                article_file = db.query(FileResource).filter(
                    FileResource.resource_id == resource.id
                ).first()
                if article_file and article_file.file_path:
                    try:
                        storage.delete_file(article_file.file_path)
                        logger.debug(f"Deleted article popup HTML: {article_file.file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete article popup HTML: {e}")

                # Get children first (for file cleanup before cascade delete)
                children = db.query(Resource).filter(
                    Resource.parent_id == resource.id
                ).all()

                for child in children:
                    # Clean up files for PDF children
                    if child.resource_type == ResourceType.PDF:
                        file_resource = db.query(FileResource).filter(
                            FileResource.resource_id == child.id
                        ).first()
                        if file_resource and file_resource.file_path:
                            try:
                                storage.delete_file(file_resource.file_path)
                                logger.debug(f"Deleted PDF file: {file_resource.file_path}")
                            except Exception as e:
                                logger.warning(f"Failed to delete PDF file: {e}")

                    deleted_count += 1

                # Remove the article_resources link first
                db.execute(
                    article_resources.delete().where(
                        and_(
                            article_resources.c.article_id == article_id,
                            article_resources.c.resource_id == resource.id
                        )
                    )
                )

                # Delete parent (cascades to children via FK)
                db.delete(resource)
                deleted_count += 1

        if deleted_count > 0:
            db.commit()
            logger.info(f"Deleted {deleted_count} article resources for article {article_id}")

        return deleted_count

    @staticmethod
    def get_article_publication_resources(
        db: Session,
        article_id: int
    ) -> Dict[str, Any]:
        """
        Get publication resource hash_ids for an article.

        Args:
            db: Database session
            article_id: ContentArticle ID

        Returns:
            Dict with hash_ids: {"popup": "...", "html": "...", "pdf": "..."}
            - popup: Parent ARTICLE resource with popup HTML (shown in navbar)
            - html: HTML child resource (standalone HTML version)
            - pdf: PDF child resource (downloadable PDF)
        """
        result = {"popup": None, "html": None, "pdf": None}

        # Find ARTICLE resources for this article
        links = db.execute(
            article_resources.select().where(
                article_resources.c.article_id == article_id
            )
        ).fetchall()

        for link in links:
            parent = db.query(Resource).filter(
                Resource.id == link.resource_id,
                Resource.resource_type == ResourceType.ARTICLE,
                Resource.is_active == True
            ).first()

            if parent:
                result["popup"] = parent.hash_id

                # Get children
                children = db.query(Resource).filter(
                    Resource.parent_id == parent.id,
                    Resource.is_active == True
                ).all()

                for child in children:
                    if child.resource_type == ResourceType.HTML:
                        result["html"] = child.hash_id
                    elif child.resource_type == ResourceType.PDF:
                        result["pdf"] = child.hash_id

        return result
