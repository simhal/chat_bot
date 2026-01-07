"""Tools for financial analyst agents.

This module exports all available tools and provides a registration function
to populate the ToolRegistry with permission metadata.
"""

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
from agents.tools.tool_registry import ToolRegistry, ToolPermission

# Import new tool modules
from agents.tools.article_tools import (
    search_articles,
    get_article,
    create_draft_article,
    write_article_content,
    submit_for_review,
    attach_resource_to_article,
    get_article_query_tools,
    get_article_write_tools,
    get_all_article_tools,
)
from agents.tools.editor_tools import (
    review_article,
    request_changes,
    submit_for_approval,
    process_approval,
    get_pending_approvals,
    get_editor_review_tools,
    get_editor_approval_tools,
    get_all_editor_tools,
)
from agents.tools.data_download_tools import (
    fetch_stock_price,
    fetch_stock_info,
    fetch_financial_statement,
    fetch_fx_rate,
    fetch_treasury_yields,
    fetch_economic_indicator,
    get_stock_data_tools,
    get_macro_data_tools,
    get_all_data_download_tools,
)
from agents.tools.prompt_tools import (
    get_tonalities,
    get_user_tonality_settings,
    set_user_chat_tonality,
    set_user_content_tonality,
    clear_user_tonality,
    get_tonality_query_tools,
    get_tonality_update_tools,
    get_all_prompt_tools,
)

# Flag to track if tools have been registered
_tools_registered = False


def register_all_tools() -> ToolRegistry:
    """
    Register all tools with the ToolRegistry.

    This function should be called once at application startup to populate
    the registry with all available tools and their permission metadata.

    Returns:
        The populated ToolRegistry instance
    """
    global _tools_registered

    if _tools_registered:
        return ToolRegistry.instance()

    registry = ToolRegistry.instance()

    # === Web Search Tools ===
    # Web search is available to analysts and above
    web_search_tool = create_web_search_tool()
    registry.register("web_search", web_search_tool, ToolPermission(
        required_role="analyst",
        topic_scoped=False,
        description="Search the web for current information"
    ))

    # === Resource Query Tools (Reader+) ===
    resource_tools = get_resource_query_tools()
    for tool in resource_tools:
        registry.register(tool.name, tool, ToolPermission(
            required_role="reader",
            topic_scoped=False,
            description=f"Query resources: {tool.description}"
        ))

    # === Resource Processing Tools (Analyst+) ===
    processing_tools = get_resource_processing_tools()
    for tool in processing_tools:
        registry.register(tool.name, tool, ToolPermission(
            required_role="analyst",
            topic_scoped=False,
            description=f"Process resources: {tool.description}"
        ))

    # === Equity Tools (Analyst+) ===
    registry.register("get_stock_info", get_stock_info, ToolPermission(
        required_role="analyst",
        topic_scoped=False,
        description="Fetch stock information and prices"
    ))
    registry.register("get_financial_statements", get_financial_statements, ToolPermission(
        required_role="analyst",
        topic_scoped=False,
        description="Fetch company financial statements"
    ))

    # === Economic Tools (Analyst+) ===
    registry.register("get_economic_indicator", get_economic_indicator, ToolPermission(
        required_role="analyst",
        topic_scoped=False,
        description="Fetch economic indicators"
    ))
    registry.register("get_fx_rate", get_fx_rate, ToolPermission(
        required_role="analyst",
        topic_scoped=False,
        description="Fetch foreign exchange rates"
    ))

    # === Fixed Income Tools (Analyst+) ===
    registry.register("get_treasury_yields", get_treasury_yields, ToolPermission(
        required_role="analyst",
        topic_scoped=False,
        description="Fetch treasury yield data"
    ))
    registry.register("get_credit_spreads", get_credit_spreads, ToolPermission(
        required_role="analyst",
        topic_scoped=False,
        description="Fetch credit spread data"
    ))
    registry.register("calculate_bond_yield", calculate_bond_yield, ToolPermission(
        required_role="analyst",
        topic_scoped=False,
        description="Calculate bond yields"
    ))

    # === Article Query Tools (Reader+) ===
    for tool in get_article_query_tools():
        registry.register(tool.name, tool, ToolPermission(
            required_role="reader",
            topic_scoped=False,
            description=f"Article query: {tool.description}"
        ))

    # === Article Write Tools (Analyst+, Topic-scoped) ===
    for tool in get_article_write_tools():
        registry.register(tool.name, tool, ToolPermission(
            required_role="analyst",
            topic_scoped=True,
            description=f"Article write: {tool.description}"
        ))

    # === Editor Review Tools (Editor+, Topic-scoped) ===
    for tool in get_editor_review_tools():
        registry.register(tool.name, tool, ToolPermission(
            required_role="editor",
            topic_scoped=True,
            description=f"Editor review: {tool.description}"
        ))

    # === Editor Approval Tools (Editor+, Topic-scoped, HITL) ===
    for tool in get_editor_approval_tools():
        registry.register(tool.name, tool, ToolPermission(
            required_role="editor",
            topic_scoped=True,
            requires_hitl=True,
            description=f"Editor approval (HITL): {tool.description}"
        ))

    # === Data Download Tools (Analyst+) ===
    for tool in get_all_data_download_tools():
        registry.register(tool.name, tool, ToolPermission(
            required_role="analyst",
            topic_scoped=False,
            description=f"Data download: {tool.description}"
        ))

    # === Tonality Query Tools (Reader+) ===
    for tool in get_tonality_query_tools():
        registry.register(tool.name, tool, ToolPermission(
            required_role="reader",
            topic_scoped=False,
            description=f"Tonality query: {tool.description}"
        ))

    # === Tonality Update Tools (Reader+) ===
    for tool in get_tonality_update_tools():
        registry.register(tool.name, tool, ToolPermission(
            required_role="reader",
            topic_scoped=False,
            description=f"Tonality update: {tool.description}"
        ))

    _tools_registered = True
    return registry


__all__ = [
    # Web search
    "create_web_search_tool",
    # Equity tools (legacy)
    "get_stock_info",
    "get_financial_statements",
    # Economic tools (legacy)
    "get_economic_indicator",
    "get_fx_rate",
    # Fixed income tools (legacy)
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
    # Article tools
    "search_articles",
    "get_article",
    "create_draft_article",
    "write_article_content",
    "submit_for_review",
    "attach_resource_to_article",
    "get_article_query_tools",
    "get_article_write_tools",
    "get_all_article_tools",
    # Editor tools
    "review_article",
    "request_changes",
    "submit_for_approval",
    "process_approval",
    "get_pending_approvals",
    "get_editor_review_tools",
    "get_editor_approval_tools",
    "get_all_editor_tools",
    # Data download tools
    "fetch_stock_price",
    "fetch_stock_info",
    "fetch_financial_statement",
    "fetch_fx_rate",
    "fetch_treasury_yields",
    "fetch_economic_indicator",
    "get_stock_data_tools",
    "get_macro_data_tools",
    "get_all_data_download_tools",
    # Prompt/tonality tools
    "get_tonalities",
    "get_user_tonality_settings",
    "set_user_chat_tonality",
    "set_user_content_tonality",
    "clear_user_tonality",
    "get_tonality_query_tools",
    "get_tonality_update_tools",
    "get_all_prompt_tools",
    # Registry
    "ToolRegistry",
    "ToolPermission",
    "register_all_tools",
]
