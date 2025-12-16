"""Fixed income specialist agent."""

from typing import List
from langchain_core.tools import Tool
from agents.base_agent import BaseSpecialistAgent
from agents.tools.fixed_income_tools import create_fixed_income_tools
from agents.tools.web_search import create_web_search_tool


class FixedIncomeAgent(BaseSpecialistAgent):
    """
    Fixed income specialist focusing on:
    - Government bonds and treasury markets
    - Corporate bonds and credit analysis
    - Bond yields, duration, and convexity
    - Credit spreads and default risk
    - Fixed income portfolio strategies
    """

    def __init__(self, llm, custom_prompt=None):
        """Initialize fixed income agent."""
        super().__init__("fixed_income", llm, custom_prompt)

    def create_tools(self) -> List[Tool]:
        """
        Create fixed income tools.
        Includes web search, treasury yields, and credit spreads.
        """
        tools = []

        # Web search for current information
        web_search = create_web_search_tool()
        if web_search:
            tools.append(web_search)

        # Fixed income-specific tools (bonds, yields, spreads)
        fi_tools = create_fixed_income_tools()
        tools.extend(fi_tools)

        return tools
