"""Service for generating PDF documents from articles."""

from io import BytesIO
from typing import Optional, List, Tuple, Any
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle
from reportlab.lib.colors import HexColor
from reportlab.lib import colors
import markdown2
from datetime import datetime
import re
import os
import logging

logger = logging.getLogger("uvicorn")


class PDFService:
    """Service for generating PDF documents from articles."""

    @staticmethod
    def _get_table_image_data(db, hash_id: str) -> Optional[bytes]:
        """
        Get the image child resource data for a table.

        Args:
            db: Database session
            hash_id: Hash ID of the table resource

        Returns:
            Image bytes or None if not found
        """
        from models import Resource, ResourceType
        from services.storage_service import get_storage

        if not db:
            logger.warning("No db session provided for _get_table_image_data")
            return None

        # Find the table resource
        table_resource = db.query(Resource).filter(Resource.hash_id == hash_id).first()
        if not table_resource:
            logger.warning(f"Table resource not found: {hash_id}")
            return None

        logger.info(f"Found table resource id={table_resource.id}")

        # Find the IMAGE child resource
        image_child = db.query(Resource).filter(
            Resource.parent_id == table_resource.id,
            Resource.resource_type == ResourceType.IMAGE,
            Resource.is_active == True
        ).first()

        if not image_child:
            logger.warning(f"No IMAGE child for table {table_resource.id}")
            return None

        if not image_child.file_resource:
            logger.warning(f"IMAGE child {image_child.id} has no file_resource")
            return None

        logger.info(f"Found image child: id={image_child.id}, path={image_child.file_resource.file_path}")

        # Get the image data from storage
        storage = get_storage()
        try:
            data = storage.get_file(image_child.file_resource.file_path)
            logger.info(f"Retrieved {len(data) if data else 0} bytes from storage")
            return data
        except Exception as e:
            logger.error(f"Failed to get table image: {e}")
            return None

    @staticmethod
    def process_resource_links_for_pdf(content: str, base_url: str = "", db=None) -> Tuple[str, List[dict]]:
        """
        Process [name](resource:hash_id) links for PDF output.

        Replaces resource links with placeholders and returns info about embedded resources.

        Args:
            content: Markdown content with resource links
            base_url: Base URL for resource content
            db: Optional database session for looking up resource types

        Returns:
            Tuple of (processed content with placeholders, list of resource info dicts)
        """
        from models import Resource, ResourceType

        resources_to_embed = []
        placeholder_counter = [0]  # Use list to allow mutation in closure

        # Pattern: [name](resource:hash_id)
        pattern = r'\[([^\]]+)\]\(resource:([a-zA-Z0-9]+)\)'

        def replace_resource(match):
            name = match.group(1)
            hash_id = match.group(2)
            content_url = f"{base_url}/api/resources/content/{hash_id}"

            # Check resource type
            resource_type = None
            resource_id = None
            if db:
                resource = db.query(Resource).filter(Resource.hash_id == hash_id).first()
                if resource:
                    resource_type = resource.resource_type.value if resource.resource_type else None
                    resource_id = resource.id

            if resource_type == 'table':
                # Get table image data
                logger.info(f"Processing table resource: {hash_id}")
                image_data = PDFService._get_table_image_data(db, hash_id)
                if image_data:
                    logger.info(f"Found image data for table {hash_id}: {len(image_data)} bytes")
                    placeholder = f"[[EMBED_TABLE_IMAGE_{placeholder_counter[0]}]]"
                    resources_to_embed.append({
                        'type': 'table_image',
                        'placeholder': placeholder,
                        'name': name,
                        'hash_id': hash_id,
                        'image_data': image_data
                    })
                    placeholder_counter[0] += 1
                    return f"\n{placeholder}\n"
                else:
                    logger.warning(f"No image data found for table {hash_id}")
                    # Fallback if no image available
                    return f"\n[Table: {name}] (View at: {content_url})\n"

            elif resource_type == 'image':
                return f"[Image: {name}] ({content_url})"
            else:
                return f"{name} ({content_url})"

        processed_content = re.sub(pattern, replace_resource, content)
        return processed_content, resources_to_embed

    @staticmethod
    def convert_markdown_to_plaintext(markdown_text: str) -> str:
        """
        Convert Markdown to plain text with some formatting preserved.

        Args:
            markdown_text: Markdown formatted text

        Returns:
            Plain text with basic formatting
        """
        # Convert markdown to HTML first
        html = markdown2.markdown(markdown_text)

        # Remove HTML tags but preserve line breaks
        text = re.sub(r'<br\s*/?>', '\n', html)
        text = re.sub(r'<p>', '', text)
        text = re.sub(r'</p>', '\n\n', text)
        text = re.sub(r'<h[1-6]>', '\n', text)
        text = re.sub(r'</h[1-6]>', '\n\n', text)
        text = re.sub(r'<[^>]+>', '', text)

        # Clean up multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

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
        Generate a PDF document for an article.

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
        # Process resource links and get embedded resources
        resources_to_embed = []
        if base_url:
            content, resources_to_embed = PDFService.process_resource_links_for_pdf(content, base_url, db)
        else:
            env_base_url = os.environ.get("API_BASE_URL", "")
            if env_base_url:
                content, resources_to_embed = PDFService.process_resource_links_for_pdf(content, env_base_url, db)

        # Create lookup dict for embedded resources
        embed_lookup = {r['placeholder']: r for r in resources_to_embed}

        # Create a BytesIO buffer to hold the PDF
        buffer = BytesIO()

        # Create the PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )

        # Container for the 'Flowable' objects
        elements = []

        # Define styles
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=HexColor('#1a1a1a'),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )

        topic_style = ParagraphStyle(
            'TopicStyle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=HexColor('#3b82f6'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )

        meta_style = ParagraphStyle(
            'MetaStyle',
            parent=styles['Normal'],
            fontSize=9,
            textColor=HexColor('#6b7280'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica'
        )

        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['BodyText'],
            fontSize=11,
            textColor=HexColor('#1a1a1a'),
            spaceAfter=12,
            alignment=TA_JUSTIFY,
            leading=16,
            fontName='Helvetica'
        )

        keywords_style = ParagraphStyle(
            'KeywordsStyle',
            parent=styles['Normal'],
            fontSize=9,
            textColor=HexColor('#374151'),
            spaceAfter=12,
            fontName='Helvetica-Oblique'
        )

        # Add topic badge
        topic_display = topic.replace('_', ' ').title()
        elements.append(Paragraph(f"{topic_display} Research", topic_style))
        elements.append(Spacer(1, 6))

        # Add title
        elements.append(Paragraph(headline, title_style))
        elements.append(Spacer(1, 12))

        # Add metadata
        try:
            created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            date_str = created_date.strftime('%B %d, %Y')
        except:
            date_str = created_at

        elements.append(Paragraph(f"Published: {date_str}", meta_style))

        # Add rating and readership if available
        meta_info = []
        if rating is not None:
            meta_info.append(f"Rating: {rating}/5 ({rating_count} ratings)")
        if readership_count > 0:
            meta_info.append(f"Readership: {readership_count}")

        if meta_info:
            elements.append(Paragraph(" | ".join(meta_info), meta_style))

        elements.append(Spacer(1, 6))

        # Add keywords if available
        if keywords:
            elements.append(Paragraph(f"<b>Keywords:</b> {keywords}", keywords_style))

        elements.append(Spacer(1, 18))

        # Convert markdown content to plain text
        plain_content = PDFService.convert_markdown_to_plaintext(content)

        # Style for table captions
        caption_style = ParagraphStyle(
            'CaptionStyle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=HexColor('#374151'),
            spaceAfter=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )

        # Split content into paragraphs and add to PDF
        paragraphs = plain_content.split('\n\n')
        for para in paragraphs:
            if para.strip():
                # Check if this paragraph contains an embedded image placeholder
                placeholder_match = re.search(r'\[\[EMBED_TABLE_IMAGE_\d+\]\]', para)
                if placeholder_match:
                    placeholder = placeholder_match.group(0)
                    if placeholder in embed_lookup:
                        resource_info = embed_lookup[placeholder]
                        # Add table caption
                        elements.append(Paragraph(f"📊 {resource_info['name']}", caption_style))
                        elements.append(Spacer(1, 6))

                        # Create image from bytes
                        try:
                            img_buffer = BytesIO(resource_info['image_data'])
                            img = Image(img_buffer)

                            # Scale image to fit page width (max 6 inches)
                            max_width = 6 * inch
                            if img.drawWidth > max_width:
                                scale = max_width / img.drawWidth
                                img.drawWidth = max_width
                                img.drawHeight = img.drawHeight * scale

                            elements.append(img)
                            elements.append(Spacer(1, 12))
                        except Exception as e:
                            logger.error(f"Failed to embed table image: {e}")
                            # Fallback to text
                            elements.append(Paragraph(
                                f"[Table: {resource_info['name']}]",
                                body_style
                            ))
                            elements.append(Spacer(1, 12))
                    continue

                # Regular paragraph - escape special characters for ReportLab
                para_text = para.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                elements.append(Paragraph(para_text, body_style))
                elements.append(Spacer(1, 12))

        # Add footer with generation info
        elements.append(Spacer(1, 24))
        footer_style = ParagraphStyle(
            'FooterStyle',
            parent=styles['Normal'],
            fontSize=8,
            textColor=HexColor('#9ca3af'),
            alignment=TA_CENTER,
            fontName='Helvetica-Oblique'
        )
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
            footer_style
        ))

        # Build the PDF
        doc.build(elements)

        # Get the value of the BytesIO buffer
        buffer.seek(0)
        return buffer
