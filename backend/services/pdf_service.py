"""Service for generating PDF documents from articles."""

from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.colors import HexColor
import markdown2
from datetime import datetime
import re


class PDFService:
    """Service for generating PDF documents from articles."""

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
        rating_count: int = 0
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

        Returns:
            BytesIO object containing the PDF
        """
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

        # Split content into paragraphs and add to PDF
        paragraphs = plain_content.split('\n\n')
        for para in paragraphs:
            if para.strip():
                # Escape special characters for ReportLab
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
