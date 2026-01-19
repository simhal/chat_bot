"""
Web Search Agent for performing internet searches.

This agent handles web search operations:
- General web search
- News search
- Financial news search
"""

from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from agents.builds.v1.state import AgentState, UserContext


class WebSearchAgent:
    """
    Agent for web search operations.

    Uses DuckDuckGo for web searches. Requires analyst+ permissions.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        topic: Optional[str] = None,
    ):
        """
        Initialize the WebSearchAgent.

        Args:
            llm: Language model for processing results
            topic: Optional topic for context
        """
        self.llm = llm
        self.topic = topic

    def web_search(
        self,
        query: str,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        Perform a general web search.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            Dict with search results
        """
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))

            return {
                "success": True,
                "query": query,
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    }
                    for r in results
                ],
                "count": len(results),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "results": [],
                "count": 0,
            }

    def search_news(
        self,
        query: str,
        max_results: int = 10,
        timelimit: str = "w",  # d=day, w=week, m=month
    ) -> Dict[str, Any]:
        """
        Search for news articles.

        Args:
            query: Search query
            max_results: Maximum number of results
            timelimit: Time limit (d=day, w=week, m=month)

        Returns:
            Dict with news results
        """
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.news(query, max_results=max_results, timelimit=timelimit))

            return {
                "success": True,
                "query": query,
                "type": "news",
                "timelimit": timelimit,
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("body", ""),
                        "source": r.get("source", ""),
                        "date": r.get("date", ""),
                    }
                    for r in results
                ],
                "count": len(results),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "results": [],
                "count": 0,
            }

    def search_financial_news(
        self,
        query: str,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        Search for financial news with finance-specific sources.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            Dict with financial news results
        """
        # Add financial context to query
        finance_query = f"{query} financial markets economy"

        result = self.search_news(
            query=finance_query,
            max_results=max_results,
            timelimit="w",
        )

        if result.get("success"):
            result["type"] = "financial_news"
            result["original_query"] = query

        return result

    def research_topic(
        self,
        topic: str,
        aspects: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Research a topic by searching multiple aspects.

        Args:
            topic: Main topic to research
            aspects: Optional list of aspects to search (e.g., ["overview", "recent news", "analysis"])

        Returns:
            Dict with combined research results
        """
        if aspects is None:
            aspects = ["overview", "recent developments", "analysis", "outlook"]

        all_results = []

        for aspect in aspects:
            query = f"{topic} {aspect}"
            result = self.web_search(query, max_results=5)

            if result.get("success"):
                for r in result.get("results", []):
                    r["aspect"] = aspect
                    all_results.append(r)

        return {
            "success": True,
            "topic": topic,
            "aspects": aspects,
            "results": all_results,
            "count": len(all_results),
        }

    def process(self, state: AgentState) -> AgentState:
        """
        Process agent state for LangGraph integration.

        Args:
            state: Current agent state

        Returns:
            Updated agent state with search results
        """
        messages = state.get("messages", [])

        if not messages:
            return {
                **state,
                "error": "No messages to process",
            }

        # Get the last user message as search query
        last_message = messages[-1]
        query = last_message.content if hasattr(last_message, 'content') else str(last_message)

        # Perform web search
        result = self.web_search(query)

        if result.get("success") and result.get("results"):
            results = result["results"]
            response = f"Found {len(results)} web results:\n\n"
            for r in results[:5]:
                response += f"**{r['title']}**\n{r['snippet']}\nURL: {r['url']}\n\n"
        else:
            response = "No web results found for your query."

        return {
            **state,
            "messages": [AIMessage(content=response)],
            "tool_results": {"web_search": result},
            "last_tool_call": "web_search",
        }
