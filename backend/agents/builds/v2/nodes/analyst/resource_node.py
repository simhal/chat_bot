"""
Resource sub-graph for analyst workflows.

This is a LangGraph sub-graph that handles resource management:
- Browse available resources
- Add resources to article
- Remove resources from article
- Link/unlink resources
- Query resources

Used by analyst_node when resource operations are needed.
"""

from typing import Dict, Any, Optional, TypedDict, List
import logging

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


# =============================================================================
# Sub-graph State
# =============================================================================

class ResourceState(TypedDict, total=False):
    """State for resource sub-graph."""
    # Input
    action: str  # browse, add, remove, link, unlink, query
    article_id: Optional[int]
    resource_id: Optional[int]
    topic: str
    query: Optional[str]
    user_context: Dict[str, Any]

    # Output
    resources: List[Dict]
    resource_info: Optional[Dict]
    message: str
    error: Optional[str]
    success: bool


# =============================================================================
# Sub-graph Nodes
# =============================================================================

def route_resource_action(state: ResourceState) -> Dict[str, Any]:
    """Route to appropriate resource action."""
    action = state.get("action", "browse")
    return {"action": action}


def browse_resources_node(state: ResourceState) -> Dict[str, Any]:
    """Browse available resources for a topic."""
    topic = state.get("topic", "")
    query = state.get("query", "")

    try:
        from database import SessionLocal
        from models import Resource
        from sqlalchemy import or_

        db = SessionLocal()
        try:
            # Query resources for the topic
            resources_query = db.query(Resource).filter(
                Resource.topic == topic,
                Resource.is_active == True
            )

            # Apply search filter if query provided
            if query:
                resources_query = resources_query.filter(
                    or_(
                        Resource.name.ilike(f"%{query}%"),
                        Resource.description.ilike(f"%{query}%")
                    )
                )

            resources = resources_query.limit(20).all()

            resources_list = [
                {
                    "id": r.id,
                    "name": r.name,
                    "description": r.description,
                    "type": r.resource_type,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                }
                for r in resources
            ]

            return {
                "resources": resources_list,
                "message": f"Found {len(resources_list)} resources for {topic}.",
                "success": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Browse resources failed: {e}")
        return {"error": str(e), "success": False, "resources": []}


def add_resource_node(state: ResourceState) -> Dict[str, Any]:
    """Add a resource to an article."""
    article_id = state.get("article_id")
    resource_id = state.get("resource_id")

    if not article_id or not resource_id:
        return {
            "error": "Both article_id and resource_id are required.",
            "success": False
        }

    try:
        from database import SessionLocal
        from models import ArticleResource, Resource, ContentArticle

        db = SessionLocal()
        try:
            # Verify article exists
            article = db.query(ContentArticle).filter(
                ContentArticle.id == article_id,
                ContentArticle.is_active == True
            ).first()
            if not article:
                return {"error": f"Article {article_id} not found.", "success": False}

            # Verify resource exists
            resource = db.query(Resource).filter(
                Resource.id == resource_id,
                Resource.is_active == True
            ).first()
            if not resource:
                return {"error": f"Resource {resource_id} not found.", "success": False}

            # Check if already linked
            existing = db.query(ArticleResource).filter(
                ArticleResource.article_id == article_id,
                ArticleResource.resource_id == resource_id
            ).first()
            if existing:
                return {
                    "message": f"Resource '{resource.name}' is already linked to article #{article_id}.",
                    "success": True
                }

            # Create link
            link = ArticleResource(
                article_id=article_id,
                resource_id=resource_id
            )
            db.add(link)
            db.commit()

            return {
                "message": f"Added resource '{resource.name}' to article #{article_id}.",
                "resource_info": {
                    "id": resource.id,
                    "name": resource.name,
                    "type": resource.resource_type
                },
                "success": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Add resource failed: {e}")
        return {"error": str(e), "success": False}


def remove_resource_node(state: ResourceState) -> Dict[str, Any]:
    """Remove a resource link from an article."""
    article_id = state.get("article_id")
    resource_id = state.get("resource_id")

    if not article_id or not resource_id:
        return {
            "error": "Both article_id and resource_id are required.",
            "success": False
        }

    try:
        from database import SessionLocal
        from models import ArticleResource

        db = SessionLocal()
        try:
            # Find and delete the link
            link = db.query(ArticleResource).filter(
                ArticleResource.article_id == article_id,
                ArticleResource.resource_id == resource_id
            ).first()

            if not link:
                return {
                    "message": f"Resource {resource_id} is not linked to article #{article_id}.",
                    "success": True
                }

            db.delete(link)
            db.commit()

            return {
                "message": f"Removed resource {resource_id} from article #{article_id}.",
                "success": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Remove resource failed: {e}")
        return {"error": str(e), "success": False}


def link_resource_node(state: ResourceState) -> Dict[str, Any]:
    """Link a resource to an article (alias for add)."""
    return add_resource_node(state)


def unlink_resource_node(state: ResourceState) -> Dict[str, Any]:
    """Unlink a resource from an article (alias for remove)."""
    return remove_resource_node(state)


def query_resources_node(state: ResourceState) -> Dict[str, Any]:
    """Query resources using semantic search."""
    query = state.get("query", "")
    topic = state.get("topic", "")

    if not query:
        return browse_resources_node(state)

    try:
        from services.vector_service import VectorService

        # Search resources using vector similarity
        results = VectorService.search_resources(
            query=query,
            topic=topic,
            limit=10
        )

        resources_list = [
            {
                "id": r.get("resource_id"),
                "name": r.get("name"),
                "description": r.get("description"),
                "type": r.get("resource_type"),
                "relevance": r.get("score", 0)
            }
            for r in results
        ]

        return {
            "resources": resources_list,
            "message": f"Found {len(resources_list)} relevant resources.",
            "success": True
        }

    except Exception as e:
        logger.warning(f"Vector search failed, falling back to browse: {e}")
        return browse_resources_node(state)


def get_article_resources_node(state: ResourceState) -> Dict[str, Any]:
    """Get resources linked to an article."""
    article_id = state.get("article_id")

    if not article_id:
        return {"error": "article_id is required.", "success": False, "resources": []}

    try:
        from database import SessionLocal
        from models import ArticleResource, Resource

        db = SessionLocal()
        try:
            # Get linked resources
            links = db.query(ArticleResource).filter(
                ArticleResource.article_id == article_id
            ).all()

            resource_ids = [link.resource_id for link in links]

            if not resource_ids:
                return {
                    "resources": [],
                    "message": f"No resources linked to article #{article_id}.",
                    "success": True
                }

            resources = db.query(Resource).filter(
                Resource.id.in_(resource_ids),
                Resource.is_active == True
            ).all()

            resources_list = [
                {
                    "id": r.id,
                    "name": r.name,
                    "description": r.description,
                    "type": r.resource_type
                }
                for r in resources
            ]

            return {
                "resources": resources_list,
                "message": f"Article #{article_id} has {len(resources_list)} linked resources.",
                "success": True
            }

        finally:
            db.close()

    except Exception as e:
        logger.exception(f"Get article resources failed: {e}")
        return {"error": str(e), "success": False, "resources": []}


# =============================================================================
# Sub-graph Builder
# =============================================================================

def _route_by_action(state: ResourceState) -> str:
    """Route to appropriate action node."""
    action = state.get("action", "browse")
    action_map = {
        "browse": "browse",
        "add": "add",
        "remove": "remove",
        "link": "link",
        "unlink": "unlink",
        "query": "query",
        "get_article_resources": "get_article_resources",
    }
    return action_map.get(action, "browse")


def build_resource_subgraph():
    """Build the resource management sub-graph."""
    workflow = StateGraph(ResourceState)

    # Add nodes
    workflow.add_node("router", route_resource_action)
    workflow.add_node("browse", browse_resources_node)
    workflow.add_node("add", add_resource_node)
    workflow.add_node("remove", remove_resource_node)
    workflow.add_node("link", link_resource_node)
    workflow.add_node("unlink", unlink_resource_node)
    workflow.add_node("query", query_resources_node)
    workflow.add_node("get_article_resources", get_article_resources_node)

    # Entry point
    workflow.set_entry_point("router")

    # Conditional routing
    workflow.add_conditional_edges(
        "router",
        _route_by_action,
        {
            "browse": "browse",
            "add": "add",
            "remove": "remove",
            "link": "link",
            "unlink": "unlink",
            "query": "query",
            "get_article_resources": "get_article_resources",
        }
    )

    # All action nodes go to END
    for node in ["browse", "add", "remove", "link", "unlink", "query", "get_article_resources"]:
        workflow.add_edge(node, END)

    return workflow.compile()


# Singleton sub-graph instance
_RESOURCE_SUBGRAPH = None


def resource_subgraph():
    """Get the singleton resource sub-graph."""
    global _RESOURCE_SUBGRAPH
    if _RESOURCE_SUBGRAPH is None:
        _RESOURCE_SUBGRAPH = build_resource_subgraph()
    return _RESOURCE_SUBGRAPH


def invoke_resource_action(
    action: str,
    topic: str,
    user_context: Dict[str, Any],
    article_id: Optional[int] = None,
    resource_id: Optional[int] = None,
    query: Optional[str] = None
) -> Dict[str, Any]:
    """
    Invoke the resource sub-graph.

    Args:
        action: browse, add, remove, link, unlink, query, get_article_resources
        topic: Topic slug
        user_context: User context
        article_id: Optional article ID
        resource_id: Optional resource ID
        query: Optional search query

    Returns:
        Dict with resources, resource_info, message, success, error
    """
    graph = resource_subgraph()

    state = ResourceState(
        action=action,
        topic=topic,
        user_context=user_context,
        article_id=article_id,
        resource_id=resource_id,
        query=query,
    )

    result = graph.invoke(state)
    return result
