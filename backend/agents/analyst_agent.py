"""
Analyst Agent for research and article creation workflows.

This is the main agent that orchestrates research workflows by composing
sub-agents for web search, data download, resource queries, and article creation.
It replaces the legacy specialist agents (equity, economist, fixed_income).
"""

from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from agents.state import (
    AgentState,
    UserContext,
    WorkflowContext,
    create_initial_state,
    update_workflow_step,
    add_resource_to_workflow,
)
from agents.article_query_agent import ArticleQueryAgent
from agents.web_search_agent import WebSearchAgent
from agents.data_download_agent import DataDownloadAgent
from agents.resource_query_agent import ResourceQueryAgent
from services.permission_service import PermissionService


class AnalystAgent:
    """
    Main analyst agent for research and content creation.

    This agent orchestrates the full research workflow:
    1. Query existing resources and articles
    2. Perform web searches for current information
    3. Download financial data as needed
    4. Create or update articles with findings
    5. Attach resources to articles

    The agent is topic-parameterized, supporting all topics (macro, equity,
    fixed_income, esg) with a single implementation.
    """

    def __init__(
        self,
        topic: str,
        llm: BaseChatModel,
        db: Session,
    ):
        """
        Initialize the AnalystAgent.

        Args:
            topic: Topic slug (macro, equity, fixed_income, esg)
            llm: Language model for generating content
            db: Database session
        """
        self.topic = topic
        self.llm = llm
        self.db = db

        # Initialize sub-agents
        self.article_agent = ArticleQueryAgent(llm=llm, db=db, topic=topic)
        self.web_search_agent = WebSearchAgent(llm=llm, topic=topic)
        self.data_download_agent = DataDownloadAgent(llm=llm, db=db, topic=topic)
        self.resource_agent = ResourceQueryAgent(llm=llm, db=db, topic=topic)

    def research_and_write(
        self,
        query: str,
        user_context: UserContext,
        article_id: Optional[int] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Full research and article creation workflow.

        This is the main entry point for analyst workflows. It:
        1. Searches existing articles for relevant content
        2. Queries resources for supporting data
        3. Performs web searches for current information
        4. Downloads financial data as needed
        5. Creates or updates an article with synthesized findings

        Args:
            query: Research query from user
            user_context: User context for permissions
            article_id: Optional existing article to update
            conversation_history: Optional list of previous messages for context

        Returns:
            Dict with article_id, resources_created, and content preview
        """
        user_scopes = user_context.get("scopes", [])

        # Verify analyst permission for topic
        if not PermissionService.check_permission(user_scopes, "analyst", topic=self.topic):
            return {
                "success": False,
                "error": f"Analyst permission required for topic '{self.topic}'",
            }

        # Step 1: Search existing articles
        article_results = self.article_agent.search_articles(
            query=query,
            user_context=user_context,
            topic=self.topic,
            limit=5,
            include_drafts=True,
        )

        # Step 2: Query existing resources
        resource_results = self.resource_agent.query(
            search_query=query,
            topic=self.topic,
            limit=10,
        )

        # Step 3: Web search for current information
        web_results = self.web_search_agent.search_news(
            query=f"{self.topic} {query}",
            max_results=10,
        )

        # Step 4: Download relevant financial data
        data_results = self._fetch_relevant_data(query)

        # Step 5: Synthesize findings into article content (with user's content tonality)
        content = self._synthesize_content(
            query=query,
            articles=article_results.get("articles", []),
            resources=resource_results.get("resources", []),
            web_results=web_results.get("results", []),
            data_results=data_results,
            user_context=user_context,
            conversation_history=conversation_history,
        )

        # Step 6: Create or update article
        if article_id:
            # Update existing article
            write_result = self.article_agent.write_article_content(
                article_id=article_id,
                content=content,
                user_context=user_context,
            )
            headline = None  # Keep existing headline
            keywords = None  # Keep existing keywords
        else:
            # Generate headline
            headline = self._generate_headline(query)

            # Generate keywords from headline and content
            keywords = self._generate_keywords(headline, content)

            # Create new draft article
            create_result = self.article_agent.create_draft_article(
                headline=headline,
                user_context=user_context,
                topic=self.topic,
                keywords=keywords,
            )

            if not create_result.get("success"):
                return create_result

            article_id = create_result.get("article_id")

            # Write content to the new article
            write_result = self.article_agent.write_article_content(
                article_id=article_id,
                content=content,
                user_context=user_context,
            )

        if not write_result.get("success"):
            return write_result

        # Step 7: Link found resources to the article
        linked_resources = []
        found_resources = resource_results.get("resources", [])
        if found_resources and article_id:
            linked_resources = self._link_resources_to_article(
                article_id=article_id,
                resources=found_resources,
            )

        return {
            "success": True,
            "article_id": article_id,
            "headline": headline,
            "keywords": keywords,
            "topic": self.topic,
            "content": content,
            "linked_resources": linked_resources,
            "sources": {
                "existing_articles": len(article_results.get("articles", [])),
                "resources": len(resource_results.get("resources", [])),
                "web_results": len(web_results.get("results", [])),
                "data_sources": len(data_results),
            },
        }

    def _get_topic_system_prompt(self) -> str:
        """
        Get topic-specific system prompt additions.

        Override this method in subclasses to provide specialized
        prompts for specific topics.

        Returns:
            Additional system prompt text, or empty string for default
        """
        return ""

    def _link_resources_to_article(
        self,
        article_id: int,
        resources: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Link found resources to the article.

        Args:
            article_id: ID of the article to link resources to
            resources: List of resource dicts from search (with resource_id, name, etc.)

        Returns:
            List of successfully linked resources with their details
        """
        from models import article_resources, Resource
        from sqlalchemy import select

        linked = []

        for resource in resources:
            resource_id = resource.get("resource_id")
            if not resource_id:
                continue

            try:
                # Check if link already exists
                existing = self.db.execute(
                    select(article_resources).where(
                        article_resources.c.article_id == article_id,
                        article_resources.c.resource_id == resource_id,
                    )
                ).first()

                if existing:
                    # Already linked
                    linked.append({
                        "resource_id": resource_id,
                        "name": resource.get("name"),
                        "type": resource.get("type"),
                        "already_linked": True,
                    })
                    continue

                # Get the resource to verify it exists
                db_resource = self.db.query(Resource).filter(
                    Resource.id == resource_id,
                    Resource.is_active == True,
                ).first()

                if not db_resource:
                    continue

                # Create the link
                self.db.execute(
                    article_resources.insert().values(
                        article_id=article_id,
                        resource_id=resource_id,
                    )
                )

                linked.append({
                    "resource_id": resource_id,
                    "name": resource.get("name") or db_resource.name,
                    "type": resource.get("type") or db_resource.resource_type.value,
                    "hash_id": db_resource.hash_id,
                    "already_linked": False,
                })

            except Exception as e:
                # Log but continue with other resources
                import logging
                logger = logging.getLogger("uvicorn")
                logger.warning(f"Failed to link resource {resource_id} to article {article_id}: {e}")
                continue

        # Commit all links
        if linked:
            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                import logging
                logger = logging.getLogger("uvicorn")
                logger.error(f"Failed to commit resource links for article {article_id}: {e}")
                return []

        return linked

    def _fetch_relevant_data(self, query: str) -> List[Dict[str, Any]]:
        """
        Fetch financial data relevant to the query.

        Args:
            query: Research query

        Returns:
            List of data results
        """
        results = []
        query_lower = query.lower()

        # Look for stock symbols
        import re
        symbols = re.findall(r'\b[A-Z]{1,5}\b', query)

        for symbol in symbols[:3]:
            data = self.data_download_agent.fetch_stock_data(symbol, period="3mo")
            if data.get("success"):
                results.append(data)

        # Fetch treasury data if relevant
        if any(word in query_lower for word in ["yield", "treasury", "bond", "rate", "interest"]):
            treasury = self.data_download_agent.fetch_treasury_yields("10Y", period="3mo")
            if treasury.get("success"):
                results.append(treasury)

        # Fetch FX data if relevant
        if any(word in query_lower for word in ["currency", "dollar", "euro", "forex", "fx"]):
            fx = self.data_download_agent.fetch_fx_rate("USD", "EUR", period="3mo")
            if fx.get("success"):
                results.append(fx)

        return results

    def _synthesize_content(
        self,
        query: str,
        articles: List[Dict],
        resources: List[Dict],
        web_results: List[Dict],
        data_results: List[Dict],
        user_context: Optional[UserContext] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Synthesize research findings into article content.

        Args:
            query: Original research query
            articles: Relevant existing articles
            resources: Relevant resources
            web_results: Web search results
            data_results: Downloaded financial data
            user_context: User context containing tonality preferences
            conversation_history: Previous conversation messages for context

        Returns:
            Synthesized article content in markdown
        """
        # Build context for LLM
        context_parts = []

        # Include conversation history for context
        if conversation_history:
            context_parts.append("## Conversation Context\n")
            for msg in conversation_history[-5:]:  # Last 5 messages
                role = msg.get("role", "user")
                content = msg.get("content", "")[:200]  # Truncate long messages
                context_parts.append(f"- **{role}**: {content}")
            context_parts.append("")

        if articles:
            context_parts.append("## Existing Research\n")
            for a in articles[:3]:
                context_parts.append(f"- {a.get('headline')} (ID: {a.get('id')})")

        if resources:
            context_parts.append("\n## Available Resources\n")
            for r in resources[:5]:
                context_parts.append(f"- {r.get('name')}: {r.get('description', '')[:100]}")

        if web_results:
            context_parts.append("\n## Recent News\n")
            for w in web_results[:5]:
                context_parts.append(f"- {w.get('title')}: {w.get('snippet', '')[:150]}")

        if data_results:
            context_parts.append("\n## Financial Data\n")
            for d in data_results:
                if d.get("symbol"):
                    context_parts.append(
                        f"- {d.get('symbol')}: Latest {d.get('latest_price', 'N/A')} "
                        f"({d.get('data_points', 0)} data points)"
                    )
                elif d.get("maturity"):
                    context_parts.append(
                        f"- Treasury {d.get('maturity')}: {d.get('latest_yield', 'N/A')}%"
                    )

        context = "\n".join(context_parts)

        # Get topic-specific system prompt (can be overridden by subclasses)
        topic_prompt = self._get_topic_system_prompt()
        system_prompt = "You are a senior financial analyst writing research articles."
        if topic_prompt:
            system_prompt += "\n" + topic_prompt

        # Apply content tonality from user preferences
        if user_context:
            content_tonality = user_context.get("content_tonality_text")
            if content_tonality:
                system_prompt += f"\n\n## Writing Style\n{content_tonality}"

        # Generate article using LLM
        prompt = f"""Based on the following research context, write a comprehensive analysis article about: {query}

Topic: {self.topic}

{context}

Write a well-structured article with:
1. An executive summary
2. Key findings and analysis
3. Data-driven insights
4. Market implications
5. Conclusion

Use markdown formatting. Include relevant data points from the research.
Keep the article professional and suitable for financial analysts."""

        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt),
            ])
            return response.content
        except Exception as e:
            # Fallback content if LLM fails
            return f"""# Research: {query}

## Executive Summary

This article analyzes {query} in the context of {self.topic}.

## Key Findings

{context}

## Conclusion

Further analysis is recommended based on the available data.

---
*Generated by AnalystAgent*
"""

    def _generate_headline(self, query: str) -> str:
        """
        Generate an article headline from the query.

        Args:
            query: Research query

        Returns:
            Generated headline
        """
        try:
            response = self.llm.invoke([
                SystemMessage(content="Generate a concise, professional headline for a financial research article."),
                HumanMessage(content=f"Query: {query}\nTopic: {self.topic}\n\nGenerate a headline (max 100 chars):"),
            ])
            headline = response.content.strip().strip('"\'')
            return headline[:100] if len(headline) > 100 else headline
        except Exception:
            # Fallback headline
            return f"Analysis: {query[:80]}"

    def _generate_keywords(self, headline: str, content: str) -> str:
        """
        Generate comma-separated keywords from article headline and content.

        Args:
            headline: Article headline
            content: Article content

        Returns:
            Comma-separated keywords string
        """
        try:
            # Use first 1500 chars of content for keyword extraction
            content_excerpt = content[:1500] if len(content) > 1500 else content

            response = self.llm.invoke([
                SystemMessage(content="Extract 5-8 relevant keywords from the article content. Return only comma-separated keywords, no explanation."),
                HumanMessage(content=f"Article headline: {headline}\n\nContent excerpt: {content_excerpt}\n\nKeywords:"),
            ])
            keywords = response.content.strip()
            return keywords
        except Exception:
            # Fallback to topic if keyword generation fails
            return self.topic

    def process(self, state: AgentState) -> AgentState:
        """
        Process agent state for LangGraph integration.

        Args:
            state: Current agent state

        Returns:
            Updated agent state
        """
        messages = state.get("messages", [])
        user_context = state.get("user_context")
        workflow_context = state.get("workflow_context")

        if not messages:
            return {
                **state,
                "error": "No messages to process",
                "is_final": True,
            }

        if not user_context:
            return {
                **state,
                "error": "User context required",
                "is_final": True,
            }

        # Get the query from the last message
        last_message = messages[-1]
        query = last_message.content if hasattr(last_message, 'content') else str(last_message)

        # Get article_id from workflow context if available
        article_id = None
        if workflow_context:
            article_id = workflow_context.get("article_id")

        # Run the research workflow
        result = self.research_and_write(
            query=query,
            user_context=user_context,
            article_id=article_id,
        )

        if result.get("success"):
            response = f"""Research completed for topic '{self.topic}'.

**Article ID:** {result.get('article_id')}
**Headline:** {result.get('headline', 'N/A')}

**Sources used:**
- Existing articles: {result.get('sources', {}).get('existing_articles', 0)}
- Resources: {result.get('sources', {}).get('resources', 0)}
- Web results: {result.get('sources', {}).get('web_results', 0)}
- Data sources: {result.get('sources', {}).get('data_sources', 0)}

The article has been saved as a draft. Use the editor workflow to review and publish."""

            # Update workflow context if present
            new_state = {
                **state,
                "messages": [AIMessage(content=response)],
                "tool_results": {"analyst_research": result},
                "last_tool_call": "research_and_write",
                "is_final": True,
            }

            if workflow_context:
                new_state = update_workflow_step(new_state, "research_complete", result.get("article_id"))

            return new_state
        else:
            return {
                **state,
                "messages": [AIMessage(content=f"Research failed: {result.get('error')}")],
                "error": result.get("error"),
                "is_final": True,
            }
