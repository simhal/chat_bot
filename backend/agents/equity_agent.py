"""Equity analyst specialist agent."""

from typing import List
from langchain_core.tools import Tool
from agents.base_agent import BaseSpecialistAgent
from agents.tools.equity_tools import create_equity_tools_safe
from agents.tools.web_search import create_web_search_tool


class EquityAgent(BaseSpecialistAgent):
    """
    Equity analyst specialist focusing on:
    - Stock analysis and company fundamentals
    - Equity markets and trading
    - Company financial statements
    - Valuation methods
    - IPOs and corporate actions
    """

    def __init__(self, llm, custom_prompt=None):
        """Initialize equity analyst agent."""
        super().__init__("equity", llm, custom_prompt)

    def create_tools(self) -> List[Tool]:
        """
        Create equity-specific tools.
        Includes web search and stock data tools.
        """
        tools = []

        # Web search for current information
        web_search = create_web_search_tool()
        if web_search:
            tools.append(web_search)

        # Equity-specific tools (stock data, financials)
        equity_tools = create_equity_tools_safe()
        tools.extend(equity_tools)

        return tools
