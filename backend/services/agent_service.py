"""High-level service for content-based multi-agent orchestration."""

from typing import Dict, Optional, List
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from agents.main_chat_agent import MainChatAgent
from services.google_search_service import GoogleSearchService
import os
import logging

logger = logging.getLogger("uvicorn")


class AgentService:
    """
    High-level service for content-based agent orchestration.
    Manages main chat agent and content agents.
    """

    def __init__(self, user_id: int, db: Session):
        """
        Initialize agent service.

        Args:
            user_id: User ID for personalized prompts
            db: Database session
        """
        self.user_id = user_id
        self.db = db

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

        # Initialize main chat agent
        self.main_agent = MainChatAgent(
            user_id=user_id,
            llm=self.llm,
            google_search_service=self.google_search,
            db=db
        )

    def chat(self, message: str) -> Dict[str, str]:
        """
        Process a chat message through the multi-agent system.

        Args:
            message: User's message

        Returns:
            Dictionary containing:
                - response: str - The assistant's response
                - agent_type: str - Which content agent handled the query
                - routing_reason: str - Why this agent was selected
        """
        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info("║" + " MULTI-AGENT SERVICE: Processing User Request".ljust(78) + "║")
        logger.info("║" + f" User ID: {self.user_id}".ljust(78) + "║")
        logger.info("╚" + "═" * 78 + "╝")

        result = self.main_agent.chat(message)

        logger.info("")
        logger.info("╔" + "═" * 78 + "╗")
        logger.info("║" + " REQUEST COMPLETE".ljust(78) + "║")
        logger.info("║" + f" Agent Type: {result.get('agent_type', 'N/A')}".ljust(78) + "║")
        logger.info("║" + f" Response Length: {len(result.get('response', ''))} chars".ljust(78) + "║")
        logger.info("╚" + "═" * 78 + "╝")
        logger.info("")

        return result

    def get_available_agents(self) -> List[str]:
        """
        Return list of available content agents.

        Returns:
            List of agent type strings
        """
        return ["macro", "equity", "fixed_income", "esg"]

    def get_agent_descriptions(self) -> Dict[str, str]:
        """
        Get descriptions of each content agent.

        Returns:
            Dictionary mapping agent types to descriptions
        """
        return {
            "macro": "Macroeconomic analysis: economic indicators, central bank policy, FX markets",
            "equity": "Equity markets: stocks, company analysis, valuations, market trends",
            "fixed_income": "Fixed income: bonds, yields, credit markets, treasuries",
            "esg": "ESG investing: environmental, social, governance factors and sustainability"
        }

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

        # Validate topic
        valid_topics = ["macro", "equity", "fixed_income", "esg"]
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
