"""Main chat agent that uses existing articles and resources for responses."""

from typing import Dict, Optional, List, TYPE_CHECKING
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from services.prompt_service import PromptService
from services.google_search_service import GoogleSearchService
from services.content_service import ContentService
from services.resource_service import ResourceService
import json
import logging

if TYPE_CHECKING:
    from agents.resource_query_agent import ResourceQueryAgent

logger = logging.getLogger("uvicorn")


class MainChatAgent:
    """
    Main chat agent that:
    1. Has customizable prompt template (global + user-specific)
    2. Searches existing articles and resources to answer queries
    3. Includes article references with links in responses
    4. Uses ResourceQueryAgents for semantic search of resources
    """

    def __init__(
        self,
        user_id: int,
        llm: ChatOpenAI,
        google_search_service: GoogleSearchService,
        db: Session,
        resource_query_agents: Optional[List["ResourceQueryAgent"]] = None
    ):
        """
        Initialize main chat agent.

        Args:
            user_id: User ID for personalized prompts
            llm: ChatOpenAI LLM instance
            google_search_service: Google Search service
            db: Database session
            resource_query_agents: Optional list of ResourceQueryAgents for querying resources
        """
        self.user_id = user_id
        self.llm = llm
        self.google_search = google_search_service
        self.db = db
        self.resource_query_agents = resource_query_agents or []

        # Get personalized system prompt
        self.system_prompt = PromptService.get_main_chat_template(user_id)

    def chat(self, user_message: str) -> Dict[str, str]:
        """
        Process user message through main chat agent.

        Args:
            user_message: User's message

        Returns:
            Dict with 'response', 'agent_type', 'routing_reason', 'articles' (list of referenced articles)
        """
        import time
        start_time = time.time()

        logger.info("=" * 80)
        logger.info(f"🤖 MAIN CHAT AGENT: New message received")
        logger.info(f"   Query: '{user_message[:100]}{'...' if len(user_message) > 100 else ''}'")

        # Step 1: Determine topic for query
        logger.info(f"🔄 ROUTING: Analyzing query to determine topic...")
        routing_start = time.time()
        routing_decision = self._route_query(user_message)
        routing_time = time.time() - routing_start

        agent_type = routing_decision.get('agent', 'general')
        routing_reason = routing_decision.get('reason', 'General conversation')

        logger.info(f"✓ ROUTING COMPLETE: {routing_time:.2f}s")
        logger.info(f"   Selected: {agent_type.upper()}")
        logger.info(f"   Reason: {routing_reason}")

        # Step 2: Handle query based on routing decision
        if agent_type == 'general':
            # Handle general conversation directly with main chat agent
            logger.info(f"💬 GENERAL CHAT MODE: Handling conversation directly")

            chat_start = time.time()
            final_response = self._handle_general_chat(user_message)
            chat_time = time.time() - chat_start

            total_time = time.time() - start_time
            logger.info(f"✓ GENERAL CHAT COMPLETE: {chat_time:.2f}s")
            logger.info(f"⏱️  TOTAL TIME: {total_time:.2f}s")
            logger.info("=" * 80)

            return {
                'response': final_response,
                'agent_type': 'general',
                'routing_reason': routing_reason,
                'articles': []
            }
        else:
            # Search for relevant articles for the topic
            logger.info(f"🔍 SEARCHING ARTICLES: Looking for {agent_type.upper()} articles...")
            search_start = time.time()

            # Search articles using the user's query
            articles = self._search_relevant_articles(agent_type, user_message)
            search_time = time.time() - search_start

            logger.info(f"✓ ARTICLE SEARCH COMPLETE: {search_time:.2f}s")
            logger.info(f"   Found {len(articles)} relevant articles")

            # Search for relevant resources
            resources = []
            if self.resource_query_agents:
                logger.info(f"📚 SEARCHING RESOURCES: Looking for relevant resources...")
                resource_start = time.time()
                resources = self._search_relevant_resources(user_message)
                resource_time = time.time() - resource_start
                logger.info(f"✓ RESOURCE SEARCH COMPLETE: {resource_time:.2f}s")
                logger.info(f"   Found {len(resources)} relevant resources")

            # Use found articles and resources to craft response
            logger.info(f"📝 SYNTHESIZING: Crafting response using content...")
            synthesis_start = time.time()
            final_response = self._synthesize_response_from_content(
                user_message, articles, resources, agent_type
            )
            synthesis_time = time.time() - synthesis_start
            logger.info(f"✓ SYNTHESIS COMPLETE: {synthesis_time:.2f}s")

            total_time = time.time() - start_time
            logger.info(f"⏱️  TOTAL TIME: {total_time:.2f}s")
            logger.info("=" * 80)

            return {
                'response': final_response,
                'agent_type': agent_type,
                'routing_reason': routing_reason,
                'articles': articles,
                'resources': resources
            }

    def _handle_general_chat(self, user_message: str) -> str:
        """
        Handle general conversation directly without routing to specialists.

        Args:
            user_message: User's message

        Returns:
            Response string
        """
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_message)
        ]

        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"Error in general chat: {e}")
            return "I apologize, but I encountered an error processing your message. Please try again."

    def _search_relevant_articles(self, topic: str, query: str) -> List[Dict]:
        """
        Search for relevant articles for a given topic and query.

        Args:
            topic: Topic to search (macro, equity, fixed_income, esg)
            query: Search query

        Returns:
            List of relevant articles (up to 5)
        """
        try:
            # Search articles using ContentService
            articles = ContentService.search_articles(self.db, topic, query, limit=5)

            # If no results from search, get recent articles
            if not articles:
                logger.info(f"   No search results, falling back to recent articles")
                articles = ContentService.get_recent_articles(self.db, topic, limit=3)

            return articles
        except Exception as e:
            logger.error(f"Error searching articles: {e}")
            return []

    def _search_relevant_resources(self, query: str) -> List[Dict]:
        """
        Search for relevant resources using ResourceQueryAgents.

        Args:
            query: Search query

        Returns:
            List of relevant resources with their content
        """
        if not self.resource_query_agents:
            return []

        all_resources = []

        for agent in self.resource_query_agents:
            try:
                result = agent.query(query, limit=3)
                if result.get("success") and result.get("resources"):
                    all_resources.extend(result["resources"])
            except Exception as e:
                logger.error(f"Error querying resources with {agent.__class__.__name__}: {e}")

        # Sort by similarity score and deduplicate
        all_resources.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)

        # Take top results
        return all_resources[:5]

    def _synthesize_response_from_articles(self, user_query: str, articles: List[Dict], agent_type: str) -> str:
        """
        Use existing articles to craft a specific answer to the user's query.
        Deprecated: Use _synthesize_response_from_content instead.
        """
        return self._synthesize_response_from_content(user_query, articles, [], agent_type)

    def _synthesize_response_from_content(
        self,
        user_query: str,
        articles: List[Dict],
        resources: List[Dict],
        agent_type: str
    ) -> str:
        """
        Use existing articles and resources to craft a specific answer to the user's query.

        Args:
            user_query: User's original question
            articles: List of relevant articles
            resources: List of relevant resources (text, tables)
            agent_type: Type of topic (macro, equity, fixed_income, esg)

        Returns:
            Response based on article and resource content
        """
        if not articles and not resources:
            # No content found, provide general response
            return self._handle_general_chat(user_query)

        # Build article content for synthesis
        articles_content = ""
        if articles:
            articles_content = "\n### Articles from Knowledge Base:\n"
            for i, article in enumerate(articles, 1):
                articles_content += f"\nArticle {i}: {article['headline']}\n"
                articles_content += f"Keywords: {article.get('keywords', 'N/A')}\n"
                articles_content += f"Content: {article['content'][:500]}...\n"
                articles_content += f"---\n"

        # Build resource content for synthesis
        resources_content = ""
        if resources:
            resources_content = "\n### Resources from Knowledge Base:\n"
            for i, resource in enumerate(resources, 1):
                resources_content += f"\nResource {i}: {resource.get('name', 'Unnamed')}"
                resources_content += f" (Type: {resource.get('type', 'unknown')})\n"
                resources_content += f"Relevance: {resource.get('similarity_score', 0):.2f}\n"
                preview = resource.get('content_preview', '')[:400]
                resources_content += f"Content: {preview}...\n"
                resources_content += f"---\n"

        synthesis_prompt = f"""You are a helpful financial assistant. A user has asked a question related to {agent_type} research.

Your task: Use the following content from our knowledge base to provide a direct, specific answer to the user's question. Be conversational and helpful.

User's Question: {user_query}

{articles_content}
{resources_content}

Instructions:
1. Directly answer the user's specific question using information from the articles and resources
2. Be concise but informative
3. Maintain a helpful, conversational tone
4. Prioritize information from higher relevance resources and more recent articles
5. If resources contain data (tables, statistics), incorporate that data into your response
6. Do NOT include article/resource references or links in your response - they will be added automatically
7. Focus on synthesizing information to answer the question

Provide your response:"""

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=synthesis_prompt)
        ]

        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"Error in synthesis: {e}")
            return "I apologize, but I encountered an error processing your question. Please try again."

    def _route_query(self, query: str) -> Dict[str, str]:
        """
        Route query to appropriate content agent or handle as general chat.

        Args:
            query: User query

        Returns:
            Dict with 'agent' and 'reason'
        """
        routing_prompt = """Analyze the user's question and determine which specialist should handle it.

Route to specialists for ANY questions about these topics:

- MACRO: Macroeconomics, economic indicators, GDP, inflation, unemployment, FX markets, currency, central banks, monetary policy, Federal Reserve, ECB, interest rates, economic outlook
- EQUITY: Stocks, shares, equities, company stock analysis, stock markets, stock performance, stock prices, stock valuation, IPOs, specific companies (e.g., Tesla, Apple, NVIDIA), market indices, S&P 500, NASDAQ
- FIXED_INCOME: Bonds, bond yields, bond markets, credit markets, corporate bonds, government bonds, treasuries, credit spreads, debt securities, fixed income investments
- ESG: Environmental, social, governance factors, sustainability, climate risk, ESG ratings, sustainable investing, green bonds, corporate responsibility

- GENERAL: Only for greetings, non-financial questions, questions about the assistant's capabilities, and topics unrelated to investing/finance

IMPORTANT ROUTING RULES:
1. ANY question about stocks, bonds, or economics → route to appropriate specialist
2. Questions about specific companies → EQUITY
3. Questions about interest rates, inflation, economic policy → MACRO
4. Questions about debt markets, yields → FIXED_INCOME
5. Questions about sustainability in investing → ESG
6. Only use GENERAL for non-financial conversations

Examples:
- "Hello" → GENERAL
- "What can you do?" → GENERAL
- "What are interest rates doing?" → MACRO (economic/monetary policy topic)
- "Tell me about Tesla" → EQUITY (company/stock topic)
- "How is Tesla stock doing?" → EQUITY (stock performance)
- "Explain what a bond is" → FIXED_INCOME (bond topic, even educational)
- "What are bond yields today?" → FIXED_INCOME (bond market data)
- "How's the economy?" → MACRO (economic question)
- "Should I invest in tech stocks?" → EQUITY (stock investing)
- "What's happening with inflation?" → MACRO (economic indicator)

Respond with JSON: {"agent": "general|macro|equity|fixed_income|esg", "reason": "brief explanation"}"""

        messages = [
            SystemMessage(content=routing_prompt),
            HumanMessage(content=f"Route this query: {query}")
        ]

        # Use JSON mode for structured output
        llm_with_json = self.llm.bind(response_format={"type": "json_object"})

        try:
            response = llm_with_json.invoke(messages)
            routing_data = json.loads(response.content)

            agent = routing_data.get('agent', 'general').lower()
            reason = routing_data.get('reason', 'General conversation')

            # Validate agent
            valid_agents = ['general', 'macro', 'equity', 'fixed_income', 'esg']
            if agent not in valid_agents:
                agent = 'general'
                reason = f"Default routing (invalid selection)"

            return {'agent': agent, 'reason': reason}

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Routing JSON parsing error: {e}")
            return {'agent': 'general', 'reason': 'Default routing (parsing error)'}

