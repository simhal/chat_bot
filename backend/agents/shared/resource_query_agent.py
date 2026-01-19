"""Resource Query Agent for semantic search of text and table resources."""

from typing import List, Dict, Optional, Any
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from services.resource_service import ResourceService
from agents.tools.resource_tools import get_resource_query_tools, get_resource_content
import logging
import json

logger = logging.getLogger("uvicorn")


class ResourceQueryAgent:
    """
    Agent responsible for querying resources from ChromaDB.

    This agent searches for relevant text and table resources based on
    queries from the ContentAgent. It uses semantic search to find
    resources that are contextually relevant to the content being created.

    The agent can:
    - Search for text resources (articles, notes, documents)
    - Search for table resources (data tables, statistics)
    - Retrieve full resource content when needed
    - Combine results from multiple resource types
    - Filter by topic (shared resources) and article (attached resources)
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        db: Session,
        resource_type: Optional[str] = None,
        topic: Optional[str] = None,
        article_id: Optional[int] = None
    ):
        """
        Initialize ResourceQueryAgent.

        Args:
            llm: ChatOpenAI LLM instance
            db: Database session for retrieving full resource content
            resource_type: Optional filter for resource type ('text', 'table', or None for all)
            topic: Optional topic to filter by (searches topic's shared resources)
            article_id: Optional article ID to filter by (searches article's attached resources)
        """
        self.llm = llm
        self.db = db
        self.resource_type = resource_type
        self.topic = topic
        self.article_id = article_id
        self.tools = get_resource_query_tools()

        # System prompt for the query agent
        self.system_prompt = """You are a Resource Query Agent specialized in finding relevant resources from the knowledge base.

Your responsibilities:
1. Search for text and table resources that are relevant to the given query
2. Evaluate search results for relevance and quality
3. Return the most useful resources to support content creation

When searching:
- Use semantic search to find contextually relevant resources
- Consider both text resources (articles, documents) and table resources (data, statistics)
- Prioritize resources with high similarity scores
- Return resources that directly support the query topic

Always return your findings in a structured format with:
- Resource ID and name
- Resource type (text or table)
- Relevance score
- Brief content preview
"""

    def query(
        self,
        search_query: str,
        context: Optional[str] = None,
        limit: int = 5,
        topic: Optional[str] = None,
        article_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Search for relevant resources based on the query.

        Args:
            search_query: The query describing what resources are needed
            context: Optional additional context about the content being created
            limit: Maximum number of resources to return
            topic: Override topic filter (uses instance topic if not provided)
            article_id: Override article filter (uses instance article_id if not provided)

        Returns:
            Dict with found resources and their details
        """
        import time
        start_time = time.time()

        # Use instance values if not overridden
        effective_topic = topic if topic is not None else self.topic
        effective_article_id = article_id if article_id is not None else self.article_id

        logger.info(f"🔍 RESOURCE QUERY AGENT: Started")
        logger.info(f"   Query: '{search_query[:80]}{'...' if len(search_query) > 80 else ''}'")
        if self.resource_type:
            logger.info(f"   Type filter: {self.resource_type}")
        if effective_topic:
            logger.info(f"   Topic filter: {effective_topic}")
        if effective_article_id:
            logger.info(f"   Article filter: {effective_article_id}")

        all_results = []

        # If topic or article_id is specified, use scoped search
        if effective_topic or effective_article_id:
            try:
                # Determine which types to search
                search_types = [self.resource_type] if self.resource_type else ["text", "table"]

                for resource_type in search_types:
                    results = ResourceService.semantic_search_for_content(
                        db=self.db,
                        query=search_query,
                        topic=effective_topic,
                        article_id=effective_article_id,
                        resource_type=resource_type,
                        limit=limit
                    )

                    for r in results:
                        all_results.append({
                            "resource_id": r.get("resource_id"),
                            "name": r.get("name"),
                            "type": r.get("type", resource_type),
                            "similarity_score": r.get("similarity_score", 0),
                            "content_preview": r.get("content_preview", "")
                        })

                    logger.info(f"   Found {len(results)} {resource_type} resources (scoped)")

            except Exception as e:
                logger.error(f"   Error in scoped resource search: {e}")
        else:
            # No scoping - search all resources
            search_types = [self.resource_type] if self.resource_type else ["text", "table"]

            for resource_type in search_types:
                try:
                    results = ResourceService.semantic_search_resources(
                        query=search_query,
                        resource_type=resource_type,
                        limit=limit
                    )

                    for r in results:
                        all_results.append({
                            "resource_id": r.get("resource_id"),
                            "name": r.get("name"),
                            "type": r.get("type", resource_type),
                            "similarity_score": r.get("similarity_score", 0),
                            "content_preview": r.get("content_preview", "")
                        })

                    logger.info(f"   Found {len(results)} {resource_type} resources")

                except Exception as e:
                    logger.error(f"   Error searching {resource_type} resources: {e}")

        # Sort by similarity score and deduplicate
        seen_ids = set()
        unique_results = []
        for r in sorted(all_results, key=lambda x: x.get("similarity_score", 0), reverse=True):
            if r.get("resource_id") not in seen_ids:
                seen_ids.add(r.get("resource_id"))
                unique_results.append(r)

        # Limit total results
        unique_results = unique_results[:limit]

        elapsed = time.time() - start_time
        logger.info(f"✓ RESOURCE QUERY AGENT: {elapsed:.2f}s, {len(unique_results)} total results")

        return {
            "success": True,
            "query": search_query,
            "resource_type_filter": self.resource_type,
            "topic_filter": effective_topic,
            "article_filter": effective_article_id,
            "results_count": len(unique_results),
            "resources": unique_results
        }

    def get_full_content(self, resource_ids: List[int]) -> Dict[str, Any]:
        """
        Retrieve full content for specified resources.

        Args:
            resource_ids: List of resource IDs to retrieve

        Returns:
            Dict with full resource content
        """
        logger.info(f"📄 RESOURCE QUERY AGENT: Retrieving {len(resource_ids)} resources")

        resources = []
        for rid in resource_ids:
            result = json.loads(get_resource_content(self.db, rid))
            if result.get("success") and result.get("resource"):
                resources.append(result["resource"])
            else:
                logger.warning(f"   Could not retrieve resource {rid}")

        logger.info(f"   Retrieved {len(resources)} resources successfully")

        return {
            "success": True,
            "resources": resources
        }

    def query_with_llm(
        self,
        search_query: str,
        context: Optional[str] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Use LLM to interpret the query and search for resources.

        This method uses the LLM to:
        1. Understand the query intent
        2. Formulate optimal search terms
        3. Evaluate and rank results

        Args:
            search_query: The query describing what resources are needed
            context: Optional additional context
            limit: Maximum number of resources to return

        Returns:
            Dict with found resources and LLM analysis
        """
        import time
        start_time = time.time()

        logger.info(f"🤖 RESOURCE QUERY AGENT (LLM): Started")
        logger.info(f"   Query: '{search_query[:80]}{'...' if len(search_query) > 80 else ''}'")

        # First, get raw search results
        raw_results = self.query(search_query, context, limit * 2)

        if not raw_results.get("resources"):
            return {
                "success": True,
                "query": search_query,
                "llm_analysis": "No resources found matching the query.",
                "resources": [],
                "recommended_resources": []
            }

        # Use LLM to analyze and rank results
        resources_text = json.dumps(raw_results["resources"], indent=2)

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"""Analyze these search results and recommend the most relevant resources.

Original Query: {search_query}
{f'Context: {context}' if context else ''}

Search Results:
{resources_text}

Please:
1. Evaluate each resource for relevance to the query
2. Recommend the top {limit} most useful resources
3. Explain why each recommended resource is relevant

Return your analysis in this format:
ANALYSIS: [Your analysis of the search results]
RECOMMENDED: [Comma-separated list of resource IDs in order of relevance]
REASONING: [Brief reasoning for each recommendation]
""")
        ]

        try:
            response = self.llm.invoke(messages)
            llm_response = response.content

            # Parse LLM response
            analysis = ""
            recommended_ids = []
            reasoning = ""

            for line in llm_response.split('\n'):
                if line.startswith('ANALYSIS:'):
                    analysis = line.replace('ANALYSIS:', '').strip()
                elif line.startswith('RECOMMENDED:'):
                    id_str = line.replace('RECOMMENDED:', '').strip()
                    try:
                        recommended_ids = [int(x.strip()) for x in id_str.split(',') if x.strip().isdigit()]
                    except:
                        pass
                elif line.startswith('REASONING:'):
                    reasoning = line.replace('REASONING:', '').strip()

            # Get recommended resources in order
            recommended_resources = []
            for rid in recommended_ids[:limit]:
                for r in raw_results["resources"]:
                    if r.get("resource_id") == rid:
                        recommended_resources.append(r)
                        break

            elapsed = time.time() - start_time
            logger.info(f"✓ RESOURCE QUERY AGENT (LLM): {elapsed:.2f}s, {len(recommended_resources)} recommended")

            return {
                "success": True,
                "query": search_query,
                "llm_analysis": analysis,
                "reasoning": reasoning,
                "resources": raw_results["resources"],
                "recommended_resources": recommended_resources
            }

        except Exception as e:
            logger.error(f"   LLM analysis error: {e}")
            # Fall back to raw results
            return {
                "success": True,
                "query": search_query,
                "llm_analysis": f"LLM analysis failed: {str(e)}",
                "resources": raw_results["resources"][:limit],
                "recommended_resources": raw_results["resources"][:limit]
            }


class TextResourceQueryAgent(ResourceQueryAgent):
    """Specialized agent for querying text resources only."""

    def __init__(
        self,
        llm: ChatOpenAI,
        db: Session,
        topic: Optional[str] = None,
        article_id: Optional[int] = None
    ):
        super().__init__(llm, db, resource_type="text", topic=topic, article_id=article_id)
        self.system_prompt = """You are a Text Resource Query Agent specialized in finding relevant text content.

Your responsibilities:
1. Search for text resources (articles, documents, notes) relevant to the query
2. Evaluate text content for relevance and quality
3. Return the most informative text resources

Focus on:
- Documents that provide factual information
- Articles with expert analysis
- Text content that supports the query topic
"""


class TableResourceQueryAgent(ResourceQueryAgent):
    """Specialized agent for querying table resources only."""

    def __init__(
        self,
        llm: ChatOpenAI,
        db: Session,
        topic: Optional[str] = None,
        article_id: Optional[int] = None
    ):
        super().__init__(llm, db, resource_type="table", topic=topic, article_id=article_id)
        self.system_prompt = """You are a Table Resource Query Agent specialized in finding relevant tabular data.

Your responsibilities:
1. Search for table resources (data tables, statistics, figures) relevant to the query
2. Evaluate data relevance and structure
3. Return the most useful data tables

Focus on:
- Tables with quantitative data
- Statistics and metrics
- Structured data that supports analysis
"""
