"""Service for generating PDF documents from articles using weasyprint."""

from io import BytesIO
from typing import Optional
import markdown2
from datetime import datetime
import re
import os
import logging

logger = logging.getLogger("uvicorn")


class PDFService:
    """Service for generating PDF documents from articles."""

    @staticmethod
    def _get_table_image_url(db, hash_id: str, base_url: str) -> Optional[str]:
        """
        Get the image child resource URL for a table.

        Args:
            db: Database session
            hash_id: Hash ID of the table resource
            base_url: Base URL for content

        Returns:
            Image URL or None if not found
        """
        from models import Resource, ResourceType

        if not db:
            return None

        # Find the table resource
        table_resource = db.query(Resource).filter(Resource.hash_id == hash_id).first()
        if not table_resource:
            return None

        # Find the IMAGE child resource
        image_child = db.query(Resource).filter(
            Resource.parent_id == table_resource.id,
            Resource.resource_type == ResourceType.IMAGE,
            Resource.is_active == True
        ).first()

        if image_child:
            return f"{base_url}/api/r/{image_child.hash_id}"
        return None

    @staticmethod
    def process_resource_links(content: str, base_url: str = "", db=None) -> str:
        """
        Process [name](resource:hash_id) links for PDF output.

        Converts resource links to actual URLs, and handles tables specially
        by embedding their image representation.

        Args:
            content: Markdown content with resource links
            base_url: Base URL for resource content
            db: Optional database session for looking up resource types

        Returns:
            Processed markdown content
        """
        from models import Resource

        pattern = r'\[([^\]]+)\]\(resource:([a-zA-Z0-9]+)\)'

        def replace_resource(match):
            name = match.group(1)
            hash_id = match.group(2)
            content_url = f"{base_url}/api/r/{hash_id}"

            # Check resource type
            resource_type = None
            if db:
                resource = db.query(Resource).filter(Resource.hash_id == hash_id).first()
                if resource:
                    resource_type = resource.resource_type.value if resource.resource_type else None

            if resource_type == 'table':
                # Try to get table image URL
                image_url = PDFService._get_table_image_url(db, hash_id, base_url)
                if image_url:
                    return f'\n\n**{name}**\n\n![{name}]({image_url})\n\n'
                else:
                    return f'[{name}]({content_url})'
            elif resource_type == 'image':
                return f'![{name}]({content_url})'
            elif resource_type == 'article':
                # For ARTICLE resources (published article popup), include links to child resources
                pdf_url = None
                html_url = None
                if db:
                    article_resource = db.query(Resource).filter(Resource.hash_id == hash_id).first()
                    if article_resource:
                        for child in article_resource.children:
                            if child.resource_type and child.resource_type.value == 'pdf':
                                pdf_url = f"{base_url}/api/r/{child.hash_id}"
                            elif child.resource_type and child.resource_type.value == 'html':
                                html_url = f"{base_url}/api/r/{child.hash_id}"

                # Build reference text with available links
                links = [f"[View Article]({content_url})"]
                if html_url:
                    links.append(f"[HTML]({html_url})")
                if pdf_url:
                    links.append(f"[PDF]({pdf_url})")

                return f'\n\n> **{name}**\n> {" | ".join(links)}\n\n'
            elif resource_type == 'html':
                # For HTML resources, just show as link (can't embed iframe in PDF)
                return f'[{name}]({content_url})'
            else:
                return f'[{name}]({content_url})'

        return re.sub(pattern, replace_resource, content)

    @staticmethod
    def generate_article_pdf(
        headline: str,
        content: str,
        topic: str,
        created_at: str,
        keywords: str = None,
        readership_count: int = 0,
        rating: int = None,
        rating_count: int = 0,
        base_url: str = "",
        db=None
    ) -> BytesIO:
        """
        Generate a PDF document for an article using weasyprint.

        Args:
            headline: Article headline
            content: Article content (markdown format)
            topic: Article topic
            created_at: Creation timestamp
            keywords: Article keywords
            readership_count: Number of times article was read
            rating: Average rating
            rating_count: Number of ratings
            base_url: Base URL for resource content links
            db: Optional database session for resource type lookup

        Returns:
            BytesIO object containing the PDF
        """
        from weasyprint import HTML, CSS

        # Get base URL
        if not base_url:
            base_url = os.environ.get("API_BASE_URL", "")

        # Process resource links
        if base_url:
            content = PDFService.process_resource_links(content, base_url, db)

        # Convert markdown to HTML
        html_content = markdown2.markdown(
            content,
            extras=['fenced-code-blocks', 'tables', 'code-friendly', 'cuddled-lists']
        )

        # Format metadata
        topic_display = topic.replace('_', ' ').title()
        try:
            created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            date_str = created_date.strftime('%B %d, %Y')
        except:
            date_str = created_at

        meta_parts = [f"Published: {date_str}"]
        if rating is not None:
            meta_parts.append(f"Rating: {rating}/5 ({rating_count} ratings)")
        if readership_count > 0:
            meta_parts.append(f"Readership: {readership_count}")
        meta_info = " | ".join(meta_parts)

        keywords_html = f'<p class="keywords"><strong>Keywords:</strong> {keywords}</p>' if keywords else ''

        # Build complete HTML document with CSS
        full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{headline}</title>
</head>
<body>
    <header>
        <div class="topic">{topic_display} Research</div>
        <h1>{headline}</h1>
        <div class="meta">{meta_info}</div>
        {keywords_html}
    </header>
    <main>
        {html_content}
    </main>
    <footer>
        Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
    </footer>
</body>
</html>"""

        # CSS styling
        css = CSS(string="""
            @page {
                size: letter;
                margin: 1in 1in 0.5in 1in;
                @bottom-center {
                    content: counter(page);
                    font-size: 9pt;
                    color: #6b7280;
                }
            }

            body {
                font-family: 'Helvetica', 'Arial', sans-serif;
                font-size: 11pt;
                line-height: 1.6;
                color: #1a1a1a;
            }

            header {
                text-align: center;
                margin-bottom: 24pt;
                border-bottom: 1px solid #e5e7eb;
                padding-bottom: 18pt;
            }

            .topic {
                font-size: 10pt;
                font-weight: bold;
                color: #3b82f6;
                margin-bottom: 6pt;
            }

            h1 {
                font-size: 18pt;
                font-weight: bold;
                margin: 12pt 0;
                color: #1a1a1a;
            }

            .meta {
                font-size: 9pt;
                color: #6b7280;
                margin-bottom: 6pt;
            }

            .keywords {
                font-size: 9pt;
                color: #374151;
                font-style: italic;
            }

            main {
                text-align: justify;
            }

            h2 {
                font-size: 14pt;
                font-weight: bold;
                margin: 18pt 0 9pt 0;
                color: #1a1a1a;
            }

            h3 {
                font-size: 12pt;
                font-weight: bold;
                margin: 14pt 0 7pt 0;
                color: #1a1a1a;
            }

            h4, h5, h6 {
                font-size: 11pt;
                font-weight: bold;
                margin: 12pt 0 6pt 0;
                color: #1a1a1a;
            }

            p {
                margin: 6pt 0 12pt 0;
            }

            a {
                color: #3b82f6;
                text-decoration: none;
            }

            ul, ol {
                margin: 6pt 0 12pt 24pt;
                padding: 0;
            }

            li {
                margin: 3pt 0;
            }

            /* Code blocks */
            pre {
                background: #f6f8fa;
                border: 1px solid #e5e7eb;
                border-radius: 4pt;
                padding: 12pt;
                margin: 12pt 0;
                overflow-x: auto;
                font-family: 'Courier New', Courier, monospace;
                font-size: 9pt;
                line-height: 1.4;
            }

            code {
                font-family: 'Courier New', Courier, monospace;
                font-size: 9pt;
                background: #f3f4f6;
                padding: 1pt 4pt;
                border-radius: 2pt;
            }

            pre code {
                background: none;
                padding: 0;
            }

            /* Tables */
            table {
                border-collapse: collapse;
                width: 100%;
                margin: 12pt 0;
                font-size: 9pt;
            }

            th, td {
                border: 1px solid #e5e7eb;
                padding: 6pt 8pt;
                text-align: left;
            }

            th {
                background: #f3f4f6;
                font-weight: bold;
                color: #1f2937;
            }

            tr:nth-child(even) {
                background: #f9fafb;
            }

            /* Blockquotes */
            blockquote {
                border-left: 3pt solid #d1d5db;
                margin: 12pt 0;
                padding: 6pt 0 6pt 12pt;
                color: #4b5563;
                font-style: italic;
            }

            /* Images */
            img {
                max-width: 100%;
                height: auto;
                margin: 12pt 0;
            }

            hr {
                border: none;
                border-top: 1px solid #e5e7eb;
                margin: 18pt 0;
            }

            strong {
                font-weight: bold;
            }

            em {
                font-style: italic;
            }

            footer {
                margin-top: 24pt;
                padding-top: 12pt;
                border-top: 1px solid #e5e7eb;
                text-align: center;
                font-size: 8pt;
                color: #9ca3af;
                font-style: italic;
            }
        """)

        # Generate PDF
        buffer = BytesIO()
        HTML(string=full_html, base_url=base_url).write_pdf(buffer, stylesheets=[css])
        buffer.seek(0)

        return buffer
