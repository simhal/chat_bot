"""Tools for resource query and processing agents."""

from typing import List, Dict, Optional, Any
from langchain_core.tools import tool
from sqlalchemy.orm import Session
from services.resource_service import ResourceService
from models import ResourceType
import logging
import json

logger = logging.getLogger("uvicorn")


# =============================================================================
# Resource Query Tools
# =============================================================================

@tool
def search_text_resources(
    query: str,
    limit: int = 5,
    group_id: Optional[int] = None
) -> str:
    """
    Search for relevant text resources using semantic search.

    Use this tool when you need to find text content related to a topic.
    The search uses embeddings to find semantically similar content.

    Args:
        query: The search query describing what information you need
        limit: Maximum number of results to return (default 5)
        group_id: Optional group ID to filter resources

    Returns:
        JSON string with matching text resources and their content previews
    """
    try:
        results = ResourceService.semantic_search_resources(
            query=query,
            resource_type="text",
            limit=limit
        )

        if not results:
            return json.dumps({
                "success": True,
                "message": "No text resources found matching your query.",
                "resources": []
            })

        # Format results
        formatted = []
        for r in results:
            formatted.append({
                "resource_id": r.get("resource_id"),
                "name": r.get("name"),
                "similarity_score": round(r.get("similarity_score", 0), 3),
                "content_preview": r.get("content_preview", "")[:300] + "..." if r.get("content_preview") and len(r.get("content_preview", "")) > 300 else r.get("content_preview", "")
            })

        logger.info(f"Text resource search found {len(formatted)} results for: {query[:50]}...")

        return json.dumps({
            "success": True,
            "message": f"Found {len(formatted)} text resources",
            "resources": formatted
        })

    except Exception as e:
        logger.error(f"Error searching text resources: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error searching text resources: {str(e)}",
            "resources": []
        })


@tool
def search_table_resources(
    query: str,
    limit: int = 5,
    group_id: Optional[int] = None
) -> str:
    """
    Search for relevant table resources using semantic search.

    Use this tool when you need to find tabular data related to a topic.
    Tables contain structured data like financial figures, statistics, etc.

    Args:
        query: The search query describing what data you need
        limit: Maximum number of results to return (default 5)
        group_id: Optional group ID to filter resources

    Returns:
        JSON string with matching table resources and their structure info
    """
    try:
        results = ResourceService.semantic_search_resources(
            query=query,
            resource_type="table",
            limit=limit
        )

        if not results:
            return json.dumps({
                "success": True,
                "message": "No table resources found matching your query.",
                "resources": []
            })

        # Format results
        formatted = []
        for r in results:
            formatted.append({
                "resource_id": r.get("resource_id"),
                "name": r.get("name"),
                "similarity_score": round(r.get("similarity_score", 0), 3),
                "content_preview": r.get("content_preview", "")[:300] + "..." if r.get("content_preview") and len(r.get("content_preview", "")) > 300 else r.get("content_preview", "")
            })

        logger.info(f"Table resource search found {len(formatted)} results for: {query[:50]}...")

        return json.dumps({
            "success": True,
            "message": f"Found {len(formatted)} table resources",
            "resources": formatted
        })

    except Exception as e:
        logger.error(f"Error searching table resources: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error searching table resources: {str(e)}",
            "resources": []
        })


@tool
def search_all_resources(
    query: str,
    limit: int = 10
) -> str:
    """
    Search for all types of resources (text and tables) using semantic search.

    Use this tool when you need to find any kind of content related to a topic,
    without knowing in advance what type of resource might be helpful.

    Args:
        query: The search query describing what information you need
        limit: Maximum number of results to return (default 10)

    Returns:
        JSON string with matching resources of all types
    """
    try:
        # Search both text and table resources
        results = ResourceService.semantic_search_resources(
            query=query,
            resource_type=None,  # All types
            limit=limit
        )

        if not results:
            return json.dumps({
                "success": True,
                "message": "No resources found matching your query.",
                "resources": []
            })

        # Format results
        formatted = []
        for r in results:
            formatted.append({
                "resource_id": r.get("resource_id"),
                "name": r.get("name"),
                "type": r.get("type"),
                "similarity_score": round(r.get("similarity_score", 0), 3),
                "content_preview": r.get("content_preview", "")[:300] + "..." if r.get("content_preview") and len(r.get("content_preview", "")) > 300 else r.get("content_preview", "")
            })

        logger.info(f"Resource search found {len(formatted)} results for: {query[:50]}...")

        return json.dumps({
            "success": True,
            "message": f"Found {len(formatted)} resources",
            "resources": formatted
        })

    except Exception as e:
        logger.error(f"Error searching resources: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error searching resources: {str(e)}",
            "resources": []
        })


def get_resource_content(db: Session, resource_id: int) -> str:
    """
    Get the full content of a resource by ID.

    This is a helper function (not a tool) that requires a database session.

    Args:
        db: Database session
        resource_id: The ID of the resource to retrieve

    Returns:
        JSON string with the full resource content
    """
    try:
        resource = ResourceService.get_resource(db, resource_id)

        if not resource:
            return json.dumps({
                "success": False,
                "message": f"Resource {resource_id} not found",
                "resource": None
            })

        # Extract content based on type
        content = None
        resource_type = resource.get("resource_type")

        if resource_type == "text":
            text_data = resource.get("text_data", {})
            content = text_data.get("content", "")
        elif resource_type == "table":
            table_data = resource.get("table_data", {})
            content = table_data.get("data", {})

        return json.dumps({
            "success": True,
            "message": f"Retrieved resource {resource_id}",
            "resource": {
                "id": resource.get("id"),
                "name": resource.get("name"),
                "type": resource_type,
                "description": resource.get("description"),
                "content": content,
                "parent_id": resource.get("parent_id"),
                "children": resource.get("children", [])
            }
        })

    except Exception as e:
        logger.error(f"Error getting resource {resource_id}: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error getting resource: {str(e)}",
            "resource": None
        })


# =============================================================================
# Resource Processing Tools
# =============================================================================

@tool
def extract_keywords(text: str, max_keywords: int = 10) -> str:
    """
    Extract keywords from text content using NLP techniques.

    Use this tool to analyze text and extract the most important keywords.

    Args:
        text: The text content to analyze
        max_keywords: Maximum number of keywords to extract (default 10)

    Returns:
        JSON string with extracted keywords and their relevance scores
    """
    try:
        # Simple keyword extraction using word frequency
        # In production, you might use NLP libraries like spaCy or NLTK
        import re
        from collections import Counter

        # Clean and tokenize
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())

        # Remove common stop words
        stop_words = {
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
            'has', 'her', 'was', 'one', 'our', 'out', 'his', 'had', 'has',
            'have', 'this', 'that', 'with', 'they', 'from', 'been', 'were',
            'said', 'will', 'each', 'make', 'like', 'just', 'into', 'over',
            'such', 'than', 'some', 'could', 'them', 'would', 'there', 'their',
            'about', 'which', 'when', 'what', 'also', 'more', 'other'
        }

        filtered_words = [w for w in words if w not in stop_words]

        # Count word frequency
        word_counts = Counter(filtered_words)

        # Get top keywords
        top_keywords = word_counts.most_common(max_keywords)

        keywords = [{"keyword": kw, "frequency": freq} for kw, freq in top_keywords]

        return json.dumps({
            "success": True,
            "message": f"Extracted {len(keywords)} keywords",
            "keywords": keywords
        })

    except Exception as e:
        logger.error(f"Error extracting keywords: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error extracting keywords: {str(e)}",
            "keywords": []
        })


@tool
def generate_summary(text: str, max_length: int = 200) -> str:
    """
    Generate a summary of text content.

    Use this tool to create a brief summary of longer text content.
    Note: This is a simple extractive summary. For better results,
    use the LLM to generate an abstractive summary.

    Args:
        text: The text content to summarize
        max_length: Maximum length of summary in characters (default 200)

    Returns:
        JSON string with the generated summary
    """
    try:
        # Simple extractive summary - take first sentences
        sentences = text.replace('\n', ' ').split('.')
        summary = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(summary) + len(sentence) + 2 <= max_length:
                summary += sentence + ". "
            else:
                break

        summary = summary.strip()
        if not summary and text:
            summary = text[:max_length] + "..." if len(text) > max_length else text

        return json.dumps({
            "success": True,
            "message": "Summary generated",
            "summary": summary
        })

    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error generating summary: {str(e)}",
            "summary": ""
        })


@tool
def analyze_table_structure(table_data: str) -> str:
    """
    Analyze the structure of table data and extract metadata.

    Use this tool to understand what columns and data types a table contains.

    Args:
        table_data: JSON string with table data (columns and data arrays)

    Returns:
        JSON string with table structure analysis
    """
    try:
        data = json.loads(table_data) if isinstance(table_data, str) else table_data

        columns = data.get("columns", [])
        rows = data.get("data", [])

        # Analyze column types
        column_analysis = []
        for i, col in enumerate(columns):
            col_values = [row[i] for row in rows if i < len(row)]

            # Determine type
            col_type = "unknown"
            if col_values:
                sample = col_values[0]
                if isinstance(sample, (int, float)):
                    col_type = "numeric"
                elif isinstance(sample, str):
                    # Check if it looks like a date
                    if any(c in str(sample) for c in ['-', '/', ':']):
                        col_type = "date/text"
                    else:
                        col_type = "text"
                elif isinstance(sample, bool):
                    col_type = "boolean"

            column_analysis.append({
                "name": col,
                "type": col_type,
                "non_null_count": len([v for v in col_values if v is not None])
            })

        return json.dumps({
            "success": True,
            "message": f"Analyzed table with {len(columns)} columns and {len(rows)} rows",
            "analysis": {
                "row_count": len(rows),
                "column_count": len(columns),
                "columns": column_analysis
            }
        })

    except Exception as e:
        logger.error(f"Error analyzing table structure: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error analyzing table: {str(e)}",
            "analysis": None
        })


# =============================================================================
# Tool Collections for Agents
# =============================================================================

def get_resource_query_tools() -> List:
    """Get tools for ResourceQueryAgent."""
    return [
        search_text_resources,
        search_table_resources,
        search_all_resources,
    ]


def get_resource_processing_tools() -> List:
    """Get tools for ResourceProcessingAgent."""
    return [
        extract_keywords,
        generate_summary,
        analyze_table_structure,
    ]
