"""Economist and macroeconomic specialist agent."""

from typing import List
from langchain_core.tools import Tool
from agents.base_agent import BaseSpecialistAgent
from agents.tools.economic_tools import create_economic_tools
from agents.tools.web_search import create_web_search_tool


class EconomistAgent(BaseSpecialistAgent):
    """
    Macroeconomic and FX specialist focusing on:
    - Macroeconomic analysis and indicators
    - Central bank policy and monetary policy
    - Foreign exchange markets and currency analysis
    - International economics and trade
    - Economic cycles and forecasting
    """

    def __init__(self, llm, custom_prompt=None):
        """Initialize economist agent."""
        super().__init__("economist", llm, custom_prompt)

    def create_tools(self) -> List[Tool]:
        """
        Create economic and FX tools.
        Includes web search, economic indicators, and FX rates.
        """
        tools = []

        # Web search for current information
        web_search = create_web_search_tool()
        if web_search:
            tools.append(web_search)

        # Economic-specific tools (indicators, FX rates)
        economic_tools = create_economic_tools()
        tools.extend(economic_tools)

        return tools
