"""Tools for financial analyst agents."""

from agents.tools.web_search import create_web_search_tool
from agents.tools.equity_tools import get_stock_info, get_financial_statements
from agents.tools.economic_tools import get_economic_indicator, get_fx_rate
from agents.tools.fixed_income_tools import get_treasury_yields, get_credit_spreads, calculate_bond_yield
from agents.tools.resource_tools import (
    search_text_resources,
    search_table_resources,
    search_all_resources,
    extract_keywords,
    generate_summary,
    analyze_table_structure,
    get_resource_query_tools,
    get_resource_processing_tools,
)

__all__ = [
    # Web search
    "create_web_search_tool",
    # Equity tools
    "get_stock_info",
    "get_financial_statements",
    # Economic tools
    "get_economic_indicator",
    "get_fx_rate",
    # Fixed income tools
    "get_treasury_yields",
    "get_credit_spreads",
    "calculate_bond_yield",
    # Resource tools
    "search_text_resources",
    "search_table_resources",
    "search_all_resources",
    "extract_keywords",
    "generate_summary",
    "analyze_table_structure",
    "get_resource_query_tools",
    "get_resource_processing_tools",
]
