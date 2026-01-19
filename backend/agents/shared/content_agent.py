"""Base class for content creation agents."""

from typing import List, Dict, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from services.prompt_service import PromptService
from services.content_service import ContentService
from services.google_search_service import GoogleSearchService
import logging

logger = logging.getLogger("uvicorn")


class ContentAgent:
    """
    Base class for content creation agents.
    Content agents create reusable articles stored in the database.
    """

    def __init__(
        self,
        topic: str,
        llm: ChatOpenAI,
        google_search_service: GoogleSearchService,
        db: Session
    ):
        """
        Initialize content agent.

        Args:
            topic: Topic type (macro, equity, fixed_income, esg)
            llm: ChatOpenAI LLM instance
            google_search_service: Google Search service for research
            db: Database session
        """
        self.topic = topic
        self.llm = llm
        self.google_search = google_search_service
        self.db = db

        # Get system prompt from database or default
        self.system_prompt = PromptService.get_content_agent_template(topic)

    def query(self, user_query: str) -> str:
        """
        Query the content agent.
        First checks database for existing relevant content.
        If not found, creates new content using Google Search.

        Args:
            user_query: User's question/query

        Returns:
            Response text (existing article or newly created)
        """
        import time
        start_time = time.time()

        logger.info(f"📚 {self.topic.upper()} CONTENT AGENT: Started")
        logger.info(f"   Query: '{user_query[:80]}{'...' if len(user_query) > 80 else ''}'")

        # Step 1: Search existing content in database
        logger.info(f"🔍 {self.topic.upper()}: Searching database for existing content...")
        search_start = time.time()
        articles = ContentService.search_articles(
            self.db,
            topic=self.topic,
            query=user_query,
            limit=3
        )
        search_time = time.time() - search_start
        logger.info(f"   Database search: {search_time:.2f}s, found {len(articles)} article(s)")

        if articles:
            # Found existing content - return the most relevant
            best_article = articles[0]
            logger.info(f"✅ {self.topic.upper()}: Using existing article")
            logger.info(f"   Article ID: {best_article['id']}")
            logger.info(f"   Headline: {best_article['headline'][:70]}{'...' if len(best_article['headline']) > 70 else ''}")
            logger.info(f"   Readership: {best_article['readership_count']} → {best_article['readership_count'] + 1}")
            logger.info(f"   Rating: {best_article.get('rating', 'N/A')}")

            # Increment readership counter
            ContentService.get_article(
                self.db,
                article_id=best_article['id'],
                increment_readership=True
            )

            total_time = time.time() - start_time
            logger.info(f"✓ {self.topic.upper()} AGENT COMPLETE: {total_time:.2f}s (cached content)")

            # Format response with article
            return self._format_existing_article_response(best_article, user_query)

        # Step 2: No existing content - create new article
        logger.info(f"📝 {self.topic.upper()}: No existing content found")
        logger.info(f"   Creating new article with research...")

        if self.google_search.is_available():
            logger.info(f"🌐 {self.topic.upper()}: Google Search is available")
            result = self._create_new_article(user_query)
            total_time = time.time() - start_time
            logger.info(f"✓ {self.topic.upper()} AGENT COMPLETE: {total_time:.2f}s (new article created)")
            return result
        else:
            logger.warning(f"⚠️  {self.topic.upper()}: Google Search unavailable")
            logger.warning(f"   Returning fallback response")
            total_time = time.time() - start_time
            logger.info(f"✓ {self.topic.upper()} AGENT COMPLETE: {total_time:.2f}s (fallback)")
            return self._fallback_response(user_query)

    def _format_existing_article_response(self, article: Dict, query: str) -> str:
        """
        Format response using existing article.

        Args:
            article: Article dictionary
            query: User query

        Returns:
            Formatted response
        """
        return f"""Based on our analysis of {self.topic}, here's relevant information:

**{article['headline']}**

{article['content']}

---
*This article has been read {article['readership_count']} times.*
"""

    def _create_new_article(self, query: str) -> str:
        """
        Create new article using Google Search research.

        Args:
            query: User query

        Returns:
            Newly created article content
        """
        import time

        # Step 1: Research using Google Search
        logger.info(f"🔬 {self.topic.upper()}: STEP 1 - Conducting research")
        search_start = time.time()
        try:
            search_results = self.google_search.search_by_topic(
                topic=self.topic,
                query_term=query,
                num_results=5
            )
            search_time = time.time() - search_start
            logger.info(f"   Google Search: {search_time:.2f}s, {len(search_results)} results")

            # Log search result titles
            for i, result in enumerate(search_results[:3], 1):
                logger.info(f"   [{i}] {result.get('title', 'N/A')[:60]}...")

            # Format search results for LLM
            search_context = self._format_search_results(search_results)

        except Exception as e:
            search_time = time.time() - search_start
            logger.error(f"   Google Search error after {search_time:.2f}s: {e}")
            search_context = "No search results available."

        # Step 2: Generate article using LLM
        logger.info(f"✍️  {self.topic.upper()}: STEP 2 - Generating article with LLM")
        llm_start = time.time()
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"""Create an article about: {query}

Research context from recent news:
{search_context}

Requirements:
1. Write a clear, informative article (max 1000 words)
2. Include a compelling headline
3. Use factual information from the research
4. Cite sources where applicable
5. Make it reusable for other users interested in this topic

Format your response as:
HEADLINE: [Your headline]
KEYWORDS: [comma-separated keywords]
CONTENT:
[Your article content]
""")
        ]

        response = self.llm.invoke(messages)
        article_text = response.content
        llm_time = time.time() - llm_start
        logger.info(f"   LLM generation: {llm_time:.2f}s")

        # Step 3: Parse and save article
        logger.info(f"💾 {self.topic.upper()}: STEP 3 - Parsing and saving article")
        parsed_article = self._parse_article_response(article_text)

        # Save to database
        db_start = time.time()
        created_article = ContentService.create_article(
            db=self.db,
            topic=self.topic,
            headline=parsed_article['headline'],
            content=parsed_article['content'],
            keywords=parsed_article['keywords'],
            agent_name=self.topic
        )
        db_time = time.time() - db_start

        logger.info(f"   Database save: {db_time:.2f}s")
        logger.info(f"✅ {self.topic.upper()}: Article created successfully")
        logger.info(f"   Article ID: {created_article['id']}")
        logger.info(f"   Headline: {created_article['headline'][:70]}{'...' if len(created_article['headline']) > 70 else ''}")
        logger.info(f"   Content length: {len(created_article['content'])} chars")
        logger.info(f"   Keywords: {created_article.get('keywords', 'N/A')}")

        # Step 4: Format response
        return f"""I've researched and created new content on this topic:

**{created_article['headline']}**

{created_article['content']}

---
*This is a new article created just for you.*
"""

    def _format_search_results(self, results: List[Dict]) -> str:
        """
        Format Google Search results for LLM context.

        Args:
            results: List of search result dicts

        Returns:
            Formatted string
        """
        if not results:
            return "No search results available."

        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(f"""{i}. {result['title']}
   Source: {result['displayLink']}
   Summary: {result['snippet']}
""")

        return "\n".join(formatted)

    def _parse_article_response(self, response_text: str) -> Dict[str, str]:
        """
        Parse LLM response to extract headline, keywords, and content.

        Args:
            response_text: LLM response

        Returns:
            Dict with 'headline', 'keywords', 'content'
        """
        lines = response_text.strip().split('\n')

        headline = "Untitled Article"
        keywords = ""
        content_lines = []
        parsing_content = False

        for line in lines:
            if line.startswith('HEADLINE:'):
                headline = line.replace('HEADLINE:', '').strip()
            elif line.startswith('KEYWORDS:'):
                keywords = line.replace('KEYWORDS:', '').strip()
            elif line.startswith('CONTENT:'):
                parsing_content = True
            elif parsing_content:
                content_lines.append(line)

        content = '\n'.join(content_lines).strip()

        # If parsing failed, use entire response as content
        if not content:
            content = response_text

        # Truncate content to roughly 1000 words
        words = content.split()
        if len(words) > 1000:
            content = ' '.join(words[:1000]) + "..."

        return {
            'headline': headline[:500],  # Limit headline length
            'keywords': keywords[:500] if keywords else None,
            'content': content
        }

    def _fallback_response(self, query: str) -> str:
        """
        Fallback response when Google Search is unavailable.

        Args:
            query: User query

        Returns:
            Fallback message
        """
        return f"""I don't have existing content on this specific topic, and Google Search is currently unavailable for researching new content.

Please try:
1. Rephrasing your question
2. Asking about a related topic
3. Contacting support if this issue persists

Topic: {self.topic}
Query: {query}"""

    def get_recent_articles(self, limit: int = 10) -> List[Dict]:
        """
        Get recent articles for this topic.

        Args:
            limit: Maximum number of articles

        Returns:
            List of article dicts
        """
        return ContentService.get_recent_articles(self.db, self.topic, limit)

    def get_top_rated_articles(self, limit: int = 10) -> List[Dict]:
        """
        Get top-rated articles for this topic.   

        Args:
            limit: Maximum number of articles

        Returns:
            List of article dicts
        """
        return ContentService.get_top_rated_articles(self.db, self.topic, limit)
