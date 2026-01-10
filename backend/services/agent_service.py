"""
High-level service for content-based multi-agent orchestration.

This service provides a clean interface to the LangGraph chat system
and other agent workflows.
"""

from typing import Dict, Optional, List, Any
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from dependencies import get_valid_topics
import os
import logging

from agents.graph import invoke_chat
from agents.state import UserContext, NavigationContext

logger = logging.getLogger("uvicorn")


class AgentService:
    """
    High-level service for content-based agent orchestration.

    Uses the singleton LangGraph from agents.graph for chat processing.
    """

    def __init__(self, user_id: int, db: Session, user_context: Optional[UserContext] = None):
        """
        Initialize agent service.

        Args:
            user_id: User ID for personalized prompts
            db: Database session
            user_context: UserContext dict for authentication/permissions
        """
        self.user_id = user_id
        self.db = db
        self.user_context = user_context

        # Initialize OpenAI LLM (for content generation workflows)
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        self.llm = ChatOpenAI(
            api_key=openai_api_key,
            model=openai_model,
            temperature=0.7
        )

    def chat(self, message: str, navigation_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Process a chat message through the LangGraph multi-agent system.

        This is the main entry point for chat processing. It uses the
        singleton graph from agents.graph.

        Args:
            message: User's message
            navigation_context: Optional navigation context from frontend

        Returns:
            Dictionary containing:
                - response: str - The assistant's response
                - agent_type: str - Which agent handled the query
                - routing_reason: str - Why this agent was selected
                - articles: list - Referenced articles (optional)
                - ui_action: dict - UI action to trigger (optional)
                - navigation: dict - Navigation command (optional)
                - editor_content: dict - Content for editor (optional)
                - confirmation: dict - HITL confirmation (optional)
        """
        if not self.user_context:
            logger.warning("AgentService.chat called without user_context")
            return {
                "response": "User context not available",
                "agent_type": "error",
                "routing_reason": "No user context"
            }

        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info("║" + " AGENT SERVICE: Processing Chat Request".ljust(78) + "║")
        logger.info("║" + f" User: {self.user_context.get('name', 'Unknown')}".ljust(78) + "║")
        if navigation_context:
            section = navigation_context.get('section', 'home')
            topic = navigation_context.get('topic', '-')
            logger.info("║" + f" Navigation: section={section}, topic={topic}".ljust(78) + "║")
        logger.info("╚" + "═" * 78 + "╝")

        # Convert dict to NavigationContext TypedDict if needed
        nav_ctx: Optional[NavigationContext] = None
        if navigation_context:
            nav_ctx = NavigationContext(
                section=navigation_context.get("section", "home"),
                role=navigation_context.get("role", "reader"),
                topic=navigation_context.get("topic"),
                article_id=navigation_context.get("article_id"),
                article_headline=navigation_context.get("article_headline"),
                article_keywords=navigation_context.get("article_keywords"),
                article_status=navigation_context.get("article_status"),
                sub_nav=navigation_context.get("sub_nav"),
                view_mode=navigation_context.get("view_mode"),
                resource_id=navigation_context.get("resource_id"),
                resource_name=navigation_context.get("resource_name"),
                resource_type=navigation_context.get("resource_type"),
                admin_view=navigation_context.get("admin_view"),
            )

        # Invoke the graph
        response = invoke_chat(
            message=message,
            user_context=self.user_context,
            navigation_context=nav_ctx,
        )

        # Convert Pydantic model to dict for API response
        result = response.model_dump()

        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info("║" + " REQUEST COMPLETE".ljust(78) + "║")
        logger.info("║" + f" Agent Type: {result.get('agent_type', 'N/A')}".ljust(78) + "║")
        logger.info("║" + f" Response Length: {len(result.get('response', ''))} chars".ljust(78) + "║")
        if result.get('ui_action'):
            logger.info("║" + f" UI Action: {result.get('ui_action', {}).get('type', 'N/A')}".ljust(78) + "║")
        if result.get('confirmation'):
            logger.info("║" + f" HITL Confirmation: {result.get('confirmation', {}).get('type', 'N/A')}".ljust(78) + "║")
        logger.info("╚" + "═" * 78 + "╝")
        logger.info("")

        return result

    def get_available_agents(self) -> List[str]:
        """Return list of available content agents (topic slugs)."""
        return get_valid_topics(self.db)

    def get_agent_descriptions(self) -> Dict[str, str]:
        """Get descriptions of each content agent from database."""
        from models import Topic

        topics = self.db.query(Topic).filter(Topic.active == True).all()
        return {t.slug: t.description or t.title for t in topics}

    def generate_content_article(self, topic: str, query: str) -> Dict:
        """
        Generate a new content article using a content agent.

        Args:
            topic: Topic slug
            query: Query/topic for the article

        Returns:
            Created article dictionary
        """
        from agents.content_agent import ContentAgent
        from services.content_service import ContentService
        from services.google_search_service import GoogleSearchService

        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info("║" + " CONTENT GENERATION: Creating New Article".ljust(78) + "║")
        logger.info("║" + f" Topic: {topic}".ljust(78) + "║")
        logger.info("╚" + "═" * 78 + "╝")

        valid_topics = get_valid_topics(self.db)
        if topic not in valid_topics:
            raise ValueError(f"Invalid topic. Must be one of: {valid_topics}")

        google_search = GoogleSearchService(
            api_key=os.getenv("GOOGLE_API_KEY", ""),
            search_engine_id=os.getenv("GOOGLE_SEARCH_ENGINE_ID", "")
        )

        content_agent = ContentAgent(
            topic=topic,
            llm=self.llm,
            google_search_service=google_search,
            db=self.db
        )

        content_agent._create_new_article(query)

        articles = ContentService.get_recent_articles(self.db, topic, limit=1)
        if not articles:
            raise ValueError("Failed to create article")

        return articles[0]

    def research_and_write(
        self,
        topic: str,
        query: str,
        article_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Use AnalystAgent for research and article creation.

        Args:
            topic: Topic slug
            query: Research query
            article_id: Optional existing article to update

        Returns:
            Dict with article_id, content, and sources used
        """
        if not self.user_context:
            raise ValueError("user_context required for new agent system")

        from agents.analyst_agent import AnalystAgent

        analyst = AnalystAgent(
            topic=topic,
            llm=self.llm,
            db=self.db,
        )

        return analyst.research_and_write(
            query=query,
            user_context=self.user_context,
            article_id=article_id,
        )

    @staticmethod
    def build_user_context(user: Dict[str, Any], db: Session) -> UserContext:
        """
        Build UserContext from JWT claims and database.

        Args:
            user: User dict from JWT token
            db: Database session

        Returns:
            UserContext dict
        """
        from services.user_context_service import UserContextService

        return UserContextService.build_user_context(
            user_id=user.get("sub"),
            scopes=user.get("scopes", []),
            db=db,
        )
