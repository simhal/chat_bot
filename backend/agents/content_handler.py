"""Content generation and routing for the main chat agent."""

from typing import Dict, Optional, List, Any
from langchain_core.messages import SystemMessage, HumanMessage
import logging
import json

logger = logging.getLogger("uvicorn")


class ContentHandler:
    """Handles content generation, routing, and synthesis for the main chat agent."""

    def __init__(self, llm, db, user_context: Optional[Dict[str, Any]] = None):
        """
        Initialize content handler.

        Args:
            llm: ChatOpenAI LLM instance
            db: Database session
            user_context: User context for permissions
        """
        self.llm = llm
        self.db = db
        self.user_context = user_context
        self.navigation_context = None
        self.analyst_agents = {}

    def set_navigation_context(self, context: Optional[Dict[str, Any]]):
        """Set the current navigation context."""
        self.navigation_context = context

    def _get_analyst_agent(self, topic: str):
        """Get or create an AnalystAgent for a specific topic."""
        if topic not in self.analyst_agents:
            from agents.analyst_agent import AnalystAgent
            self.analyst_agents[topic] = AnalystAgent(
                topic=topic,
                llm=self.llm,
                db=self.db
            )
            logger.info(f"✓ AnalystAgent initialized for topic: {topic}")
        return self.analyst_agents[topic]

    def detect_content_generation_intent(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect if the user wants to generate article content (while in analyst editor).

        Args:
            message: User message

        Returns:
            Content generation intent dict or None if no generation intent detected
        """
        nav_context = self.navigation_context or {}
        current_section = nav_context.get('section', 'home')
        current_role = nav_context.get('role', 'reader')
        article_id = nav_context.get('article_id')
        topic = nav_context.get('topic')

        logger.info(f"📝 Content generation check: section={current_section}, role={current_role}, article_id={article_id}, topic={topic}")

        # Only trigger content generation when user is in analyst context
        if current_section != 'analyst' or current_role != 'analyst':
            logger.info(f"⏭️  Content generation skipped: section={current_section} (need 'analyst'), role={current_role} (need 'analyst')")
            return None

        message_lower = message.lower()

        # Content generation keywords
        generation_keywords = [
            "write an article", "generate article", "create article content",
            "write content", "generate content", "draft an article",
            "write about", "generate analysis", "create analysis",
            "research and write", "write research", "produce article",
            "fill in the article", "fill the article", "fill the editor", "write this article",
            "fill article", "please fill", "generate for me", "write for me",
            "rewrite", "rewrite this", "rewrite the article", "rewrite article",
            "regenerate", "redo this", "redo the article"
        ]

        # Check for keyword match
        matched_keyword = next((kw for kw in generation_keywords if kw in message_lower), None)
        if matched_keyword:
            logger.info(f"✅ Content generation keyword matched: '{matched_keyword}'")

        if any(kw in message_lower for kw in generation_keywords):
            return {
                "topic": topic,
                "article_id": article_id,
                "query": message,
            }

        # Also check for more specific requests when editing an article
        if article_id:
            # User might ask to generate content for their current article
            article_specific_keywords = [
                "generate this", "write this", "fill this", "draft this",
                "create content", "start writing", "begin writing",
                "help me write", "help write"
            ]
            if any(kw in message_lower for kw in article_specific_keywords):
                logger.info(f"✅ Article-specific content generation detected")
                return {
                    "topic": topic,
                    "article_id": article_id,
                    "query": message,
                }

        return None

    def handle_content_generation(self, gen_intent: Dict[str, Any], user_message: str, system_prompt: str) -> Dict[str, Any]:
        """
        Handle content generation request using the AnalystAgent.

        Args:
            gen_intent: Content generation intent
            user_message: Original user message
            system_prompt: System prompt to use

        Returns:
            Response dict with generated content
        """
        topic = gen_intent.get("topic")
        article_id = gen_intent.get("article_id")

        if not topic:
            return {
                "response": "I need to know which topic you want to write about. Please navigate to an analyst section first.",
                "agent_type": "analyst",
                "routing_reason": "No topic specified for content generation",
                "articles": [],
            }

        # Check if user has analyst permission for this topic
        if not self.user_context:
            return {
                "response": "I can't verify your permissions. Please ensure you're logged in.",
                "agent_type": "analyst",
                "routing_reason": "No user context for content generation",
                "articles": [],
            }

        scopes = self.user_context.get("scopes", [])
        required_scope = f"{topic}:analyst"

        # Check if user has analyst permission for this topic
        has_permission = (
            "global:admin" in scopes or
            required_scope in scopes or
            any(scope.endswith(":analyst") for scope in scopes)
        )

        if not has_permission:
            return {
                "response": f"You need analyst access for {topic.replace('_', ' ').title()} to generate content.",
                "agent_type": "analyst",
                "routing_reason": "Missing analyst permission",
                "articles": [],
            }

        # Get or create analyst agent for this topic
        analyst_agent = self._get_analyst_agent(topic)

        try:
            # Generate content using the analyst agent
            result = analyst_agent.generate_content(
                user_query=user_message,
                article_id=article_id,
                user_context=self.user_context
            )

            if result.get("success"):
                # Return generated content with metadata for the frontend
                generated_content = result.get("content", "")
                headline = result.get("headline", "")
                keywords = result.get("keywords", "")

                # If content was generated but headline wasn't, generate it
                if generated_content and not headline:
                    headline = self._generate_headline_from_content(generated_content, topic)

                # If content was generated but keywords weren't, generate them
                if generated_content and not keywords:
                    keywords = self._generate_keywords_from_content(generated_content, topic)

                response = f"""I've generated the article content for you based on your request.

**Generated Headline:** {headline}

**Keywords:** {keywords}

The content has been prepared and will populate your editor. You can review and edit it before saving."""

                return {
                    "response": response,
                    "agent_type": "analyst",
                    "routing_reason": "Content generated via AnalystAgent",
                    "articles": [],
                    "generated_content": {
                        "headline": headline,
                        "content": generated_content,
                        "keywords": keywords,
                        "article_id": article_id,
                    },
                }
            else:
                error_msg = result.get("error", "Unknown error during content generation")
                return {
                    "response": f"I encountered an issue generating the content: {error_msg}",
                    "agent_type": "analyst",
                    "routing_reason": f"Content generation error: {error_msg}",
                    "articles": [],
                }

        except Exception as e:
            logger.error(f"✗ CONTENT GENERATION: Exception - {str(e)}")
            return {
                "response": f"An error occurred while generating content: {str(e)}",
                "agent_type": "analyst",
                "routing_reason": f"Content generation exception: {str(e)}",
                "articles": [],
            }

    def _generate_headline_from_content(self, content: str, topic: str) -> str:
        """Generate a headline from article content."""
        try:
            content_preview = content[:1000] if content else ""

            prompt = f"""Based on the following article content, generate a concise, professional headline.
The headline should:
- Be clear and informative
- Be 60-100 characters long
- Capture the main topic and key insight
- Be suitable for a financial research article

Topic: {topic}

Article content preview:
{content_preview}

Generate only the headline, no quotes or extra formatting:"""

            messages = [
                SystemMessage(content="You are a financial editor creating article headlines."),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            headline = response.content.strip().strip('"\'')
            return headline[:120] if len(headline) > 120 else headline

        except Exception as e:
            logger.warning(f"Failed to generate headline: {e}")
            return f"{topic.replace('_', ' ').title()} Analysis"

    def _generate_keywords_from_content(self, content: str, topic: str) -> str:
        """Generate keywords from article content."""
        try:
            content_preview = content[:2000] if content else ""

            prompt = f"""Based on the following article content, generate relevant keywords for search and categorization.
The keywords should:
- Be 5-10 keywords, comma-separated
- Include key companies, concepts, and themes mentioned
- Be relevant for financial research
- Include specific terms (stock symbols, economic indicators, etc.)

Topic: {topic}

Article content preview:
{content_preview}

Generate only the comma-separated keywords, no extra text:"""

            messages = [
                SystemMessage(content="You are a financial analyst tagging articles for search."),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            keywords = response.content.strip()
            keywords = keywords.replace('"', '').replace("'", "")
            return keywords[:200] if len(keywords) > 200 else keywords

        except Exception as e:
            logger.warning(f"Failed to generate keywords: {e}")
            return topic.replace('_', ' ')

    def route_query(self, query: str) -> Dict[str, str]:
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
            logger.warning(f"Routing JSON parsing error: {e}")
            return {'agent': 'general', 'reason': 'Default routing (parsing error)'}

    def needs_live_data(self, message: str) -> Dict[str, Any]:
        """
        Determine if the query needs live data from content agents.

        Args:
            message: User message

        Returns:
            Dict with data requirements
        """
        message_lower = message.lower()

        # Keywords that suggest need for live web search
        web_search_keywords = [
            "latest", "recent", "today", "current", "now",
            "news", "breaking", "just happened", "this week",
            "update", "what's happening"
        ]

        # Keywords that suggest need for market data
        market_data_keywords = [
            "price", "stock price", "share price", "quote",
            "trading at", "market cap", "volume", "52 week",
            "dividend", "pe ratio", "earnings"
        ]

        needs_web = any(kw in message_lower for kw in web_search_keywords)
        needs_market = any(kw in message_lower for kw in market_data_keywords)

        # Extract potential stock symbols (uppercase 1-5 letter words)
        import re
        symbols = re.findall(r'\b[A-Z]{1,5}\b', message)
        # Filter out common words
        common_words = {'I', 'A', 'THE', 'AND', 'OR', 'FOR', 'TO', 'IN', 'ON', 'AT', 'IS', 'IT', 'BE', 'AS', 'BY', 'SO', 'IF', 'US', 'AN', 'OF'}
        stock_symbols = [s for s in symbols if s not in common_words]

        return {
            "needs_web_search": needs_web,
            "needs_market_data": needs_market or bool(stock_symbols),
            "stock_symbols": stock_symbols,
            "query": message,
        }

    def fetch_live_data(self, data_needs: Dict[str, Any], topic: str, web_search_agent, data_download_agent) -> Dict[str, Any]:
        """
        Fetch live data from content agents.

        Args:
            data_needs: Data requirements from needs_live_data
            topic: Topic for context
            web_search_agent: WebSearchAgent instance
            data_download_agent: DataDownloadAgent instance

        Returns:
            Dict with web_results and market_data
        """
        result = {
            "web_results": [],
            "market_data": [],
        }

        if data_needs.get("needs_web_search"):
            try:
                query = data_needs.get("query", "")
                web_results = web_search_agent.search(query, topic)
                result["web_results"] = web_results.get("results", [])
            except Exception as e:
                logger.warning(f"Web search failed: {e}")

        if data_needs.get("needs_market_data"):
            try:
                symbols = data_needs.get("stock_symbols", [])
                if symbols:
                    market_data = data_download_agent.get_stock_data(symbols)
                    result["market_data"] = market_data.get("data", [])
            except Exception as e:
                logger.warning(f"Market data fetch failed: {e}")

        return result

    def search_relevant_articles(self, topic: str, query: str) -> List[Dict]:
        """
        Search for relevant articles in the knowledge base.

        Args:
            topic: Topic to search in
            query: Search query

        Returns:
            List of relevant articles
        """
        from services.content_service import ContentService

        try:
            content_service = ContentService(self.db)
            articles = content_service.search_articles(
                query=query,
                topic=topic,
                limit=5,
                published_only=True
            )
            return articles
        except Exception as e:
            logger.warning(f"Article search failed: {e}")
            return []

    def search_relevant_resources(self, query: str, resource_query_agents: List = None) -> List[Dict]:
        """
        Search for relevant resources using ResourceQueryAgents.

        Args:
            query: Search query
            resource_query_agents: List of ResourceQueryAgent instances

        Returns:
            List of relevant resources
        """
        if not resource_query_agents:
            return []

        all_resources = []
        for agent in resource_query_agents:
            try:
                results = agent.search(query)
                all_resources.extend(results)
            except Exception as e:
                logger.warning(f"Resource search failed for agent: {e}")

        # Sort by relevance and limit
        all_resources.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        return all_resources[:5]

    def synthesize_response_from_content(
        self,
        user_query: str,
        articles: List[Dict],
        resources: List[Dict],
        agent_type: str,
        live_data: Optional[Dict[str, Any]] = None,
        system_prompt: str = ""
    ) -> str:
        """
        Synthesize a response from articles, resources, and live data.

        Args:
            user_query: Original user query
            articles: Relevant articles
            resources: Relevant resources
            agent_type: Type of agent handling query
            live_data: Optional live data from content agents
            system_prompt: System prompt to use

        Returns:
            Synthesized response
        """
        # Build context from articles
        articles_content = ""
        if articles:
            articles_content = "## Knowledge Base Articles:\n\n"
            for i, article in enumerate(articles[:3]):
                articles_content += f"### Article {i+1}: {article.get('headline', 'N/A')}\n"
                articles_content += f"{article.get('summary', article.get('content', ''))[:500]}...\n\n"

        # Build context from resources
        resources_content = ""
        if resources:
            resources_content = "## Related Resources:\n\n"
            for i, resource in enumerate(resources[:3]):
                resources_content += f"### Resource {i+1}: {resource.get('title', 'N/A')}\n"
                resources_content += f"{resource.get('summary', resource.get('content', ''))[:300]}...\n\n"

        # Build context from live data
        live_data_content = ""
        if live_data:
            if live_data.get("web_results"):
                live_data_content += "## Recent News:\n\n"
                for result in live_data["web_results"][:3]:
                    live_data_content += f"- {result.get('title', 'N/A')}: {result.get('snippet', '')}\n"
                live_data_content += "\n"

            if live_data.get("market_data"):
                live_data_content += "## Market Data:\n\n"
                for info in live_data["market_data"]:
                    live_data_content += f"**{info.get('symbol', 'N/A')}**: ${info.get('price', 0):.2f}\n"
                    if info.get('change_percent'):
                        change = info.get('change_percent', 0)
                        direction = "↑" if change > 0 else "↓"
                        live_data_content += f"Change: {direction} {abs(change):.2f}%\n"
                    if info.get('52_week_high') and info.get('52_week_low'):
                        live_data_content += f"52-Week Range: ${info.get('52_week_low', 0):.2f} - ${info.get('52_week_high', 0):.2f}\n"
                    live_data_content += f"---\n"

        # Get user name for personalization
        user_name = self.user_context.get("name", "") if self.user_context else ""
        personalization = f"Address the user as {user_name}. " if user_name else ""

        synthesis_prompt = f"""You are a helpful financial assistant. A user has asked a question related to {agent_type} research.

Your task: Use the following content to provide a direct, specific answer to the user's question. Be conversational and helpful. {personalization}

User's Question: {user_query}

{articles_content}
{resources_content}
{live_data_content}

Instructions:
1. Directly answer the user's specific question using information from ALL available sources
2. Prioritize live market data and news when available for current/recent questions
3. Use knowledge base articles for background context and analysis
4. Be concise but informative
3. Maintain a helpful, conversational tone
4. Prioritize information from higher relevance resources and more recent articles
5. If resources contain data (tables, statistics), incorporate that data into your response
6. Do NOT include article/resource references or links in your response - they will be added automatically
7. Focus on synthesizing information to answer the question

Provide your response:"""

        messages = [
            SystemMessage(content=system_prompt or "You are a helpful financial assistant."),
            HumanMessage(content=synthesis_prompt)
        ]

        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"Error in synthesis: {e}")
            return "I apologize, but I encountered an error processing your question. Please try again."
