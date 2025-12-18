"""Resource Processing Agent for analyzing and decomposing resources."""

from typing import List, Dict, Optional, Any, Tuple
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from services.resource_service import ResourceService
from models import ResourceType, ResourceStatus
from agents.tools.resource_tools import get_resource_processing_tools
import logging
import json
import os

logger = logging.getLogger("uvicorn")


class ResourceProcessingAgent:
    """
    Agent responsible for processing and analyzing resources.

    This agent can:
    - Generate metadata (description, keywords) for resources
    - Analyze text content and extract key information
    - Decompose PDFs into child resources (text, tables, images)
    - Process uploaded files and create structured resources
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        db: Session
    ):
        """
        Initialize ResourceProcessingAgent.

        Args:
            llm: ChatOpenAI LLM instance
            db: Database session for resource operations
        """
        self.llm = llm
        self.db = db
        self.tools = get_resource_processing_tools()

        self.system_prompt = """You are a Resource Processing Agent specialized in analyzing and enriching resources.

Your responsibilities:
1. Generate meaningful descriptions for resources
2. Extract keywords and key concepts from content
3. Analyze document structure and content
4. Create metadata that improves searchability

When analyzing content:
- Identify the main topic and subtopics
- Extract named entities (people, organizations, locations)
- Identify key statistics and figures
- Determine the content type (research, analysis, data, etc.)

Always provide structured metadata that helps other agents find and use these resources effectively.
"""

    def generate_metadata(
        self,
        resource_id: int,
        content: str,
        resource_type: str
    ) -> Dict[str, Any]:
        """
        Generate metadata for a resource using LLM.

        Args:
            resource_id: The resource ID to update
            content: The resource content to analyze
            resource_type: Type of resource (text, table, etc.)

        Returns:
            Dict with generated metadata
        """
        import time
        start_time = time.time()

        logger.info(f"📝 RESOURCE PROCESSING AGENT: Generating metadata for resource {resource_id}")

        # Prepare content preview (limit size for LLM)
        content_preview = content[:5000] if len(content) > 5000 else content

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"""Analyze this {resource_type} resource and generate metadata.

Content:
{content_preview}
{'...[truncated]' if len(content) > 5000 else ''}

Please provide:
1. A concise description (1-2 sentences)
2. Keywords (comma-separated, 5-10 keywords)
3. Main topic category
4. Content type (research, analysis, data, news, etc.)
5. Key entities mentioned (people, organizations, etc.)

Format your response as:
DESCRIPTION: [Your description]
KEYWORDS: [keyword1, keyword2, ...]
TOPIC: [Main topic]
CONTENT_TYPE: [Content type]
ENTITIES: [entity1, entity2, ...]
""")
        ]

        try:
            response = self.llm.invoke(messages)
            llm_response = response.content

            # Parse response
            metadata = {
                "description": "",
                "keywords": [],
                "topic": "",
                "content_type": "",
                "entities": []
            }

            for line in llm_response.split('\n'):
                line = line.strip()
                if line.startswith('DESCRIPTION:'):
                    metadata["description"] = line.replace('DESCRIPTION:', '').strip()
                elif line.startswith('KEYWORDS:'):
                    keywords_str = line.replace('KEYWORDS:', '').strip()
                    metadata["keywords"] = [k.strip() for k in keywords_str.split(',')]
                elif line.startswith('TOPIC:'):
                    metadata["topic"] = line.replace('TOPIC:', '').strip()
                elif line.startswith('CONTENT_TYPE:'):
                    metadata["content_type"] = line.replace('CONTENT_TYPE:', '').strip()
                elif line.startswith('ENTITIES:'):
                    entities_str = line.replace('ENTITIES:', '').strip()
                    metadata["entities"] = [e.strip() for e in entities_str.split(',')]

            elapsed = time.time() - start_time
            logger.info(f"✓ RESOURCE PROCESSING AGENT: Metadata generated in {elapsed:.2f}s")
            logger.info(f"   Keywords: {', '.join(metadata['keywords'][:5])}...")

            return {
                "success": True,
                "resource_id": resource_id,
                "metadata": metadata
            }

        except Exception as e:
            logger.error(f"   Error generating metadata: {e}")
            return {
                "success": False,
                "resource_id": resource_id,
                "error": str(e),
                "metadata": None
            }

    def analyze_text_resource(
        self,
        resource_id: int,
        update_resource: bool = True
    ) -> Dict[str, Any]:
        """
        Analyze a text resource and optionally update its metadata.

        Args:
            resource_id: The text resource ID to analyze
            update_resource: Whether to update the resource in database

        Returns:
            Dict with analysis results
        """
        logger.info(f"📊 RESOURCE PROCESSING AGENT: Analyzing text resource {resource_id}")

        # Get resource content
        resource = ResourceService.get_resource(self.db, resource_id)

        if not resource:
            return {
                "success": False,
                "error": f"Resource {resource_id} not found"
            }

        if resource.get("resource_type") != "text":
            return {
                "success": False,
                "error": f"Resource {resource_id} is not a text resource"
            }

        text_data = resource.get("text_data", {})
        content = text_data.get("content", "")

        if not content:
            return {
                "success": False,
                "error": "Resource has no text content"
            }

        # Generate metadata
        result = self.generate_metadata(resource_id, content, "text")

        if result.get("success") and update_resource and result.get("metadata"):
            # Update resource description
            metadata = result["metadata"]
            try:
                ResourceService.update_resource(
                    db=self.db,
                    resource_id=resource_id,
                    user_id=resource.get("created_by", 1),
                    description=metadata.get("description")
                )
                logger.info(f"   Updated resource {resource_id} with new description")
            except Exception as e:
                logger.warning(f"   Could not update resource: {e}")

        return result

    def analyze_table_resource(
        self,
        resource_id: int,
        update_resource: bool = True
    ) -> Dict[str, Any]:
        """
        Analyze a table resource and generate metadata.

        Args:
            resource_id: The table resource ID to analyze
            update_resource: Whether to update the resource in database

        Returns:
            Dict with analysis results
        """
        logger.info(f"📊 RESOURCE PROCESSING AGENT: Analyzing table resource {resource_id}")

        # Get resource content
        resource = ResourceService.get_resource(self.db, resource_id)

        if not resource:
            return {
                "success": False,
                "error": f"Resource {resource_id} not found"
            }

        if resource.get("resource_type") != "table":
            return {
                "success": False,
                "error": f"Resource {resource_id} is not a table resource"
            }

        table_data = resource.get("table_data", {})
        data = table_data.get("data", {})

        if not data:
            return {
                "success": False,
                "error": "Resource has no table data"
            }

        # Create text representation for analysis
        columns = data.get("columns", [])
        rows = data.get("data", [])

        text_repr = f"Table with columns: {', '.join(columns)}\n"
        text_repr += f"Number of rows: {len(rows)}\n"
        if rows:
            text_repr += "Sample data (first 5 rows):\n"
            for i, row in enumerate(rows[:5]):
                text_repr += f"  Row {i+1}: {dict(zip(columns, row))}\n"

        # Generate metadata
        result = self.generate_metadata(resource_id, text_repr, "table")

        if result.get("success") and update_resource and result.get("metadata"):
            metadata = result["metadata"]
            try:
                ResourceService.update_resource(
                    db=self.db,
                    resource_id=resource_id,
                    user_id=resource.get("created_by", 1),
                    description=metadata.get("description")
                )
                logger.info(f"   Updated resource {resource_id} with new description")
            except Exception as e:
                logger.warning(f"   Could not update resource: {e}")

        return result

    def process_pdf_resource(
        self,
        resource_id: int,
        user_id: int,
        extract_text: bool = True,
        extract_tables: bool = True,
        extract_images: bool = False
    ) -> Dict[str, Any]:
        """
        Process a PDF resource and create child resources.

        This method decomposes a PDF into:
        - Text resources (extracted text content)
        - Table resources (extracted tables)
        - Image resources (extracted images, if enabled)

        Args:
            resource_id: The PDF resource ID to process
            user_id: User ID for creating child resources
            extract_text: Whether to extract text content
            extract_tables: Whether to extract tables
            extract_images: Whether to extract images

        Returns:
            Dict with created child resources
        """
        import time
        start_time = time.time()

        logger.info(f"📄 RESOURCE PROCESSING AGENT: Processing PDF resource {resource_id}")

        # Get the PDF resource
        resource = ResourceService.get_resource(self.db, resource_id)

        if not resource:
            return {
                "success": False,
                "error": f"Resource {resource_id} not found"
            }

        if resource.get("resource_type") != "pdf":
            return {
                "success": False,
                "error": f"Resource {resource_id} is not a PDF resource"
            }

        file_data = resource.get("file_data", {})
        file_path = file_data.get("file_path")

        if not file_path:
            return {
                "success": False,
                "error": "PDF resource has no file path"
            }

        # Full path to the file
        upload_dir = os.environ.get("UPLOAD_DIR", "/app/uploads")
        full_path = os.path.join(upload_dir, file_path)

        if not os.path.exists(full_path):
            return {
                "success": False,
                "error": f"PDF file not found: {file_path}"
            }

        created_resources = []
        parent_name = resource.get("name", "PDF Document")
        group_id = resource.get("group_id")

        # Extract text content
        if extract_text:
            try:
                text_content = self._extract_pdf_text(full_path)
                if text_content:
                    text_resource, _ = ResourceService.create_text_resource(
                        db=self.db,
                        name=f"{parent_name} - Extracted Text",
                        content=text_content,
                        created_by=user_id,
                        description=f"Text content extracted from {parent_name}",
                        group_id=group_id,
                        parent_id=resource_id
                    )
                    created_resources.append({
                        "type": "text",
                        "id": text_resource.id,
                        "name": text_resource.name
                    })
                    logger.info(f"   Created text resource {text_resource.id}")
            except Exception as e:
                logger.error(f"   Error extracting text: {e}")

        # Extract tables
        if extract_tables:
            try:
                tables = self._extract_pdf_tables(full_path)
                for i, table_data in enumerate(tables):
                    table_resource, _ = ResourceService.create_table_resource(
                        db=self.db,
                        name=f"{parent_name} - Table {i+1}",
                        table_data=table_data,
                        created_by=user_id,
                        description=f"Table {i+1} extracted from {parent_name}",
                        group_id=group_id,
                        parent_id=resource_id
                    )
                    created_resources.append({
                        "type": "table",
                        "id": table_resource.id,
                        "name": table_resource.name
                    })
                    logger.info(f"   Created table resource {table_resource.id}")
            except Exception as e:
                logger.error(f"   Error extracting tables: {e}")

        elapsed = time.time() - start_time
        logger.info(f"✓ RESOURCE PROCESSING AGENT: PDF processed in {elapsed:.2f}s")
        logger.info(f"   Created {len(created_resources)} child resources")

        return {
            "success": True,
            "parent_resource_id": resource_id,
            "created_resources": created_resources,
            "processing_time": elapsed
        }

    def _extract_pdf_text(self, file_path: str) -> Optional[str]:
        """
        Extract text content from a PDF file.

        Args:
            file_path: Path to the PDF file

        Returns:
            Extracted text content or None
        """
        try:
            # Try using PyPDF2 first (usually available)
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(file_path)
                text_parts = []
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                return "\n\n".join(text_parts) if text_parts else None
            except ImportError:
                pass

            # Try pdfplumber as alternative
            try:
                import pdfplumber
                text_parts = []
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                return "\n\n".join(text_parts) if text_parts else None
            except ImportError:
                pass

            logger.warning("No PDF text extraction library available (PyPDF2 or pdfplumber)")
            return None

        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            return None

    def _extract_pdf_tables(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Extract tables from a PDF file.

        Args:
            file_path: Path to the PDF file

        Returns:
            List of table data dictionaries
        """
        tables = []

        try:
            # Try using pdfplumber for table extraction
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    for page_num, page in enumerate(pdf.pages):
                        page_tables = page.extract_tables()
                        for table_idx, table in enumerate(page_tables):
                            if table and len(table) > 1:
                                # First row as headers
                                headers = [str(h) if h else f"Column_{i}" for i, h in enumerate(table[0])]
                                data = table[1:]

                                tables.append({
                                    "columns": headers,
                                    "data": data
                                })
                                logger.info(f"   Extracted table from page {page_num + 1}")
            except ImportError:
                logger.warning("pdfplumber not available for table extraction")

        except Exception as e:
            logger.error(f"Error extracting PDF tables: {e}")

        return tables

    def batch_process_resources(
        self,
        resource_ids: List[int],
        generate_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Process multiple resources in batch.

        Args:
            resource_ids: List of resource IDs to process
            generate_metadata: Whether to generate metadata for each

        Returns:
            Dict with processing results for each resource
        """
        logger.info(f"🔄 RESOURCE PROCESSING AGENT: Batch processing {len(resource_ids)} resources")

        results = []
        for rid in resource_ids:
            resource = ResourceService.get_resource(self.db, rid)
            if not resource:
                results.append({
                    "resource_id": rid,
                    "success": False,
                    "error": "Resource not found"
                })
                continue

            resource_type = resource.get("resource_type")

            if resource_type == "text":
                result = self.analyze_text_resource(rid, update_resource=generate_metadata)
            elif resource_type == "table":
                result = self.analyze_table_resource(rid, update_resource=generate_metadata)
            elif resource_type == "pdf":
                result = self.process_pdf_resource(rid, resource.get("created_by", 1))
            else:
                result = {
                    "success": False,
                    "error": f"Unsupported resource type: {resource_type}"
                }

            result["resource_id"] = rid
            results.append(result)

        success_count = sum(1 for r in results if r.get("success"))
        logger.info(f"✓ RESOURCE PROCESSING AGENT: Batch complete, {success_count}/{len(resource_ids)} succeeded")

        return {
            "success": True,
            "total": len(resource_ids),
            "succeeded": success_count,
            "results": results
        }
