"""Google Custom Search API service for content research."""

from typing import List, Dict, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os


class GoogleSearchService:
    """
    Service for performing Google Custom Search API queries.
    Used by content agents to research and create articles.
    """

    def __init__(self, api_key: str, search_engine_id: str):
        """
        Initialize Google Search Service.

        Args:
            api_key: Google API key
            search_engine_id: Custom Search Engine ID
        """
        self.api_key = api_key
        self.search_engine_id = search_engine_id
        self.service = None

        # Initialize service if credentials are provided
        if self.api_key and self.search_engine_id:
            try:
                self.service = build("customsearch", "v1", developerKey=self.api_key)
            except Exception as e:
                print(f"Warning: Failed to initialize Google Search service: {e}")

    def is_available(self) -> bool:
        """
        Check if Google Search service is available.

        Returns:
            True if service is initialized, False otherwise
        """
        return self.service is not None

    def search(
        self,
        query: str,
        num_results: int = 10,
        date_restrict: Optional[str] = None,
        sort_by: Optional[str] = None
    ) -> List[Dict]:
        """
        Perform a Google Custom Search.

        Args:
            query: Search query string
            num_results: Number of results to return (max 10 per request)
            date_restrict: Date restriction (e.g., 'd7' for last 7 days, 'm1' for last month)
            sort_by: Sort parameter (if supported by your CSE)

        Returns:
            List of search result dictionaries with keys:
                - title: Result title
                - link: Result URL
                - snippet: Result description snippet
                - displayLink: Display URL

        Raises:
            RuntimeError: If service is not available
            HttpError: If API request fails
        """
        if not self.is_available():
            raise RuntimeError("Google Search service is not initialized. Check API credentials.")

        try:
            # Build search parameters
            params = {
                'q': query,
                'cx': self.search_engine_id,
                'num': min(num_results, 10)  # API max is 10 per request
            }

            if date_restrict:
                params['dateRestrict'] = date_restrict

            if sort_by:
                params['sort'] = sort_by

            # Execute search
            result = self.service.cse().list(**params).execute()

            # Extract and format results
            items = result.get('items', [])
            search_results = []

            for item in items:
                search_results.append({
                    'title': item.get('title', ''),
                    'link': item.get('link', ''),
                    'snippet': item.get('snippet', ''),
                    'displayLink': item.get('displayLink', '')
                })

            return search_results

        except HttpError as e:
            print(f"Google Search API error: {e}")
            raise

    def search_financial_news(
        self,
        topic: str,
        keywords: List[str],
        num_results: int = 5,
        recent_only: bool = True
    ) -> List[Dict]:
        """
        Search for financial news on a specific topic.

        Args:
            topic: Main topic (e.g., "macro economy", "equity markets")
            keywords: List of additional keywords
            num_results: Number of results to return
            recent_only: If True, restrict to last 7 days

        Returns:
            List of search results
        """
        # Build query with topic and keywords
        query_parts = [topic] + keywords
        query = ' '.join(query_parts)

        # Add financial news sources
        query += ' (site:bloomberg.com OR site:reuters.com OR site:wsj.com OR site:ft.com OR site:cnbc.com)'

        # Restrict to recent results if requested
        date_restrict = 'd7' if recent_only else None

        return self.search(query, num_results=num_results, date_restrict=date_restrict)

    def search_by_topic(
        self,
        topic: str,
        query_term: str,
        num_results: int = 5
    ) -> List[Dict]:
        """
        Perform a topic-specific search with financial context.

        Args:
            topic: Topic type (macro, equity, fixed_income, esg)
            query_term: Specific search term
            num_results: Number of results

        Returns:
            List of search results
        """
        # Topic-specific search modifiers
        topic_modifiers = {
            'macro': ['macroeconomic', 'economy', 'GDP', 'inflation', 'central bank'],
            'equity': ['stock market', 'equity', 'shares', 'stock analysis'],
            'fixed_income': ['bonds', 'fixed income', 'yield', 'treasury', 'credit'],
            'esg': ['ESG', 'sustainability', 'environmental', 'social governance', 'climate']
        }

        # Get modifiers for this topic
        modifiers = topic_modifiers.get(topic, [])

        # Build query
        if modifiers:
            # Pick top 2 modifiers to keep query focused
            modifier_str = ' OR '.join(modifiers[:2])
            query = f"{query_term} ({modifier_str})"
        else:
            query = query_term

        # Search recent financial news
        return self.search_financial_news(
            topic=query,
            keywords=[],
            num_results=num_results,
            recent_only=True
        )
