"""High-level service for content-based multi-agent orchestration."""

from typing import Dict, Optional, List, Any
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from agents.main_chat_agent import MainChatAgent, USE_LANGGRAPH_CHAT
from services.google_search_service import GoogleSearchService
from dependencies import get_valid_topics
from observability import is_langsmith_enabled, get_run_metadata
import os
import logging

logger = logging.getLogger("uvicorn")

# Feature flags for multi-agent workflows
ENABLE_HITL_WORKFLOW = os.getenv("ENABLE_HITL_WORKFLOW", "false").lower() == "true"
ENABLE_TOOL_PERMISSIONS = os.getenv("ENABLE_TOOL_PERMISSIONS", "false").lower() == "true"
LANGSMITH_ENABLED = is_langsmith_enabled()

# Log which chat implementation will be used
if USE_LANGGRAPH_CHAT:
    logger.info("🔄 AgentService: LangGraph chat (v2) is ENABLED")
else:
    logger.info("🔄 AgentService: Using legacy chat (v1)")


class AgentService:
    """
    High-level service for content-based agent orchestration.
    Manages main chat agent and content agents.
    """

    def __init__(self, user_id: int, db: Session, user_context: Optional[Dict[str, Any]] = None):
        """
        Initialize agent service.

        Args:
            user_id: User ID for personalized prompts
            db: Database session
            user_context: Optional UserContext dict for new architecture
        """
        self.user_id = user_id
        self.db = db
        self.user_context = user_context

        # Initialize OpenAI LLM
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        self.llm = ChatOpenAI(
            api_key=openai_api_key,
            model=openai_model,
            temperature=0.7
        )

        # Initialize Google Search service
        google_api_key = os.getenv("GOOGLE_API_KEY", "")
        google_search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "")

        self.google_search = GoogleSearchService(
            api_key=google_api_key,
            search_engine_id=google_search_engine_id
        )

        # Initialize main chat agent with user context
        self.main_agent = MainChatAgent(
            user_id=user_id,
            llm=self.llm,
            google_search_service=self.google_search,
            db=db,
            user_context=user_context,
        )

    def chat(self, message: str, navigation_context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Process a chat message through the multi-agent system.

        This method automatically uses either the legacy chat() or the new
        LangGraph-based chat_v2() depending on the USE_LANGGRAPH_CHAT flag.

        Args:
            message: User's message
            navigation_context: Optional navigation context from frontend

        Returns:
            Dictionary containing:
                - response: str - The assistant's response
                - agent_type: str - Which content agent handled the query
                - routing_reason: str - Why this agent was selected
                - articles: list - Referenced articles (optional)
                - ui_action: dict - UI action to trigger (optional, v2 only)
                - navigation: dict - Navigation command (optional, v2 only)
                - editor_content: dict - Content for editor (optional, v2 only)
                - confirmation: dict - HITL confirmation (optional, v2 only)
        """
        impl = "LangGraph (v2)" if USE_LANGGRAPH_CHAT else "Legacy (v1)"

        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info("║" + " MULTI-AGENT SERVICE: Processing User Request".ljust(78) + "║")
        logger.info("║" + f" User ID: {self.user_id}".ljust(78) + "║")
        logger.info("║" + f" Implementation: {impl}".ljust(78) + "║")
        if navigation_context:
            logger.info("║" + f" Navigation: section={navigation_context.get('section')}, topic={navigation_context.get('topic')}".ljust(78) + "║")
        logger.info("╚" + "═" * 78 + "╝")

        # Use chat_auto to automatically choose implementation
        result = self.main_agent.chat_auto(message, navigation_context=navigation_context)

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

    def chat_v2(self, message: str, navigation_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Explicitly use the new LangGraph-based chat implementation.

        This method always uses the LangGraph workflow regardless of feature flag.
        Use this for testing the new implementation.

        Args:
            message: User's message
            navigation_context: Optional navigation context from frontend

        Returns:
            Response dictionary with all fields supported by v2
        """
        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info("║" + " MULTI-AGENT SERVICE (v2): Processing with LangGraph".ljust(78) + "║")
        logger.info("╚" + "═" * 78 + "╝")

        return self.main_agent.chat_v2(message, navigation_context=navigation_context)

    def get_available_agents(self) -> List[str]:
        """
        Return list of available content agents.

        Returns:
            List of agent type strings (topic slugs from database)
        """
        return get_valid_topics(self.db)

    def get_agent_descriptions(self) -> Dict[str, str]:
        """
        Get descriptions of each content agent from database.

        Returns:
            Dictionary mapping agent types (slugs) to descriptions
        """
        from models import Topic

        topics = self.db.query(Topic).filter(Topic.active == True).all()
        return {t.slug: t.description or t.title for t in topics}

    def get_statistics(self) -> Dict:
        """
        Get content agent statistics.

        Returns:
            Dictionary with agent statistics
        """
        return self.main_agent.get_agent_statistics()

    def generate_content_article(self, topic: str, query: str) -> Dict:
        """
        Generate a new content article using a content agent.
        This is used by analysts to create new research articles.

        Args:
            topic: Topic type (macro, equity, fixed_income, esg)
            query: Query/topic for the article

        Returns:
            Created article dictionary

        Raises:
            ValueError: If topic is invalid
        """
        from agents.content_agent import ContentAgent
        from services.content_service import ContentService

        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info("║" + " CONTENT GENERATION: Creating New Article".ljust(78) + "║")
        logger.info("║" + f" Topic: {topic}".ljust(78) + "║")
        logger.info("║" + f" Query: {query[:60]}{'...' if len(query) > 60 else ''}".ljust(78) + "║")
        logger.info("╚" + "═" * 78 + "╝")

        # Validate topic against database
        valid_topics = get_valid_topics(self.db)
        if topic not in valid_topics:
            raise ValueError(f"Invalid topic. Must be one of: {valid_topics}")

        # Create content agent
        content_agent = ContentAgent(
            topic=topic,
            llm=self.llm,
            google_search_service=self.google_search,
            db=self.db
        )

        # Force creation of new article (not using cached content)
        logger.info(f"📝 Forcing creation of new {topic} article...")
        article = content_agent._create_new_article(query)

        # Get the most recently created article for this topic
        # (The _create_new_article method saves it to the database)
        articles = ContentService.get_recent_articles(self.db, topic, limit=1)

        if not articles:
            raise ValueError("Failed to create article")

        created_article = articles[0]

        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info("║" + " CONTENT GENERATION COMPLETE".ljust(78) + "║")
        logger.info("║" + f" Article ID: {created_article['id']}".ljust(78) + "║")
        logger.info("╚" + "═" * 78 + "╝")
        logger.info("")

        return created_article

    # =========================================================================
    # New Multi-Agent Architecture Methods
    # =========================================================================

    def research_and_write(
        self,
        topic: str,
        query: str,
        article_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Use AnalystAgent for research and article creation.

        Args:
            topic: Topic slug (macro, equity, fixed_income, esg)
            query: Research query
            article_id: Optional existing article to update

        Returns:
            Dict with article_id, content, and sources used
        """
        if not self.user_context:
            raise ValueError("user_context required for new agent system")

        from agents.analyst_agent import AnalystAgent

        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info("║" + " NEW ANALYST AGENT: Research and Write".ljust(78) + "║")
        logger.info("║" + f" Topic: {topic}".ljust(78) + "║")
        logger.info("║" + f" Query: {query[:60]}{'...' if len(query) > 60 else ''}".ljust(78) + "║")
        logger.info("╚" + "═" * 78 + "╝")

        analyst = AnalystAgent(
            topic=topic,
            llm=self.llm,
            db=self.db,
        )

        result = analyst.research_and_write(
            query=query,
            user_context=self.user_context,
            article_id=article_id,
        )

        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info("║" + " ANALYST AGENT COMPLETE".ljust(78) + "║")
        logger.info("║" + f" Success: {result.get('success')}".ljust(78) + "║")
        if result.get('article_id'):
            logger.info("║" + f" Article ID: {result.get('article_id')}".ljust(78) + "║")
        logger.info("╚" + "═" * 78 + "╝")
        logger.info("")

        return result

    def submit_for_approval(
        self,
        article_id: int,
        editor_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submit an article for HITL approval using EditorSubAgent.

        Requires ENABLE_HITL_WORKFLOW=true feature flag.

        Args:
            article_id: ID of the article to submit
            editor_notes: Optional notes from the editor

        Returns:
            Dict with approval_request_id and thread_id
        """
        if not ENABLE_HITL_WORKFLOW:
            raise ValueError("HITL workflow not enabled. Set ENABLE_HITL_WORKFLOW=true.")

        if not self.user_context:
            raise ValueError("user_context required for HITL workflow")

        from agents.editor_sub_agent import EditorSubAgent

        logger.info(f"📝 Submitting article {article_id} for HITL approval...")

        editor = EditorSubAgent(
            llm=self.llm,
            db=self.db,
        )

        result = editor.submit_for_approval(
            article_id=article_id,
            user_context=self.user_context,
            editor_notes=editor_notes,
        )

        if result.get("success"):
            logger.info(f"✓ Article {article_id} submitted. Approval ID: {result.get('approval_request_id')}")
        else:
            logger.error(f"✗ Submission failed: {result.get('error')}")

        return result

    def process_approval(
        self,
        article_id: int,
        approved: bool,
        review_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process an approval decision for an article.

        Requires ENABLE_HITL_WORKFLOW=true feature flag.

        Args:
            article_id: ID of the article
            approved: Whether to approve or reject
            review_notes: Optional notes from reviewer

        Returns:
            Dict with new article status
        """
        if not ENABLE_HITL_WORKFLOW:
            raise ValueError("HITL workflow not enabled. Set ENABLE_HITL_WORKFLOW=true.")

        if not self.user_context:
            raise ValueError("user_context required for HITL workflow")

        from agents.editor_sub_agent import EditorSubAgent

        logger.info(f"📝 Processing approval for article {article_id}: {'APPROVE' if approved else 'REJECT'}")

        editor = EditorSubAgent(
            llm=self.llm,
            db=self.db,
        )

        result = editor.process_approval(
            article_id=article_id,
            approved=approved,
            user_context=self.user_context,
            review_notes=review_notes,
        )

        if result.get("success"):
            logger.info(f"✓ Article {article_id} status: {result.get('new_status')}")
        else:
            logger.error(f"✗ Approval processing failed: {result.get('error')}")

        return result

    def dispatch_celery_task(
        self,
        task_name: str,
        **kwargs,
    ) -> str:
        """
        Dispatch a Celery task for background processing.

        Args:
            task_name: Name of the task (analyst_research, editor_publish, etc.)
            **kwargs: Task-specific arguments

        Returns:
            Celery task ID for tracking
        """
        from tasks.agent_tasks import (
            analyst_research_task,
            web_search_task,
            data_download_task,
            article_query_task,
            editor_publish_task,
        )

        task_map = {
            "analyst_research": analyst_research_task,
            "web_search": web_search_task,
            "data_download": data_download_task,
            "article_query": article_query_task,
            "editor_publish": editor_publish_task,
        }

        task_func = task_map.get(task_name)
        if not task_func:
            raise ValueError(f"Unknown task: {task_name}. Available: {list(task_map.keys())}")

        # Add user_id to kwargs
        kwargs["user_id"] = self.user_id
        if self.user_context:
            kwargs["user_context"] = self.user_context

        # Dispatch task
        result = task_func.delay(**kwargs)
        logger.info(f"📤 Dispatched Celery task '{task_name}': {result.id}")

        return result.id

    @staticmethod
    def build_user_context(user: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        Build UserContext from JWT claims and database.

        Args:
            user: User dict from JWT token (get_current_user dependency)
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
