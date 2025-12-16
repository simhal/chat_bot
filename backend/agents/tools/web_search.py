"""Enhanced web search tool for financial queries."""

from langchain_core.tools import Tool
from langchain_community.tools import DuckDuckGoSearchRun
from typing import Optional


def create_web_search_tool() -> Optional[Tool]:
    """
    Create enhanced web search tool for financial queries.
    Returns None if tool initialization fails.
    """
    try:
        search = DuckDuckGoSearchRun()
        return Tool(
            name="web_search",
            description="""Search the web for current financial information, news, market data, and economic indicators.
Use for: stock prices, market news, economic reports, company announcements, analyst opinions, financial data.
Input: A specific search query (e.g., 'AAPL stock price today', 'latest Fed interest rate decision', 'Tesla earnings report')""",
            func=search.run
        )
    except Exception as e:
        print(f"Warning: Web search tool unavailable: {e}")
        return None
