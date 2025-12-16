"""Macroeconomic and FX tools."""

from langchain_core.tools import Tool
from typing import List
import datetime


def get_economic_indicator(indicator: str) -> str:
    """
    Get economic indicators.
    Note: This is a mock implementation. In production, use FRED API, World Bank API, etc.

    Available indicators: GDP, INFLATION, UNEMPLOYMENT, FED_RATE, CONSUMER_CONFIDENCE
    """
    # Mock data - replace with real API calls in production
    # For production, consider: Federal Reserve Economic Data (FRED) API
    mock_data = {
        "GDP": "US GDP Growth Rate: 2.8% annualized (Q3 2024). The economy continues to show resilience with consumer spending and business investment driving growth.",

        "INFLATION": "US CPI Inflation: 3.2% YoY (November 2024). Core inflation (excluding food and energy): 4.0%. The Fed continues to monitor inflation closely as it approaches the 2% target.",

        "UNEMPLOYMENT": "US Unemployment Rate: 3.7% (November 2024). Labor force participation rate: 62.8%. The labor market remains tight with strong job creation in services and healthcare sectors.",

        "FED_RATE": "Federal Funds Rate: 5.25-5.50% (current target range). The Federal Reserve has maintained this rate since July 2023, balancing inflation control with economic growth concerns.",

        "CONSUMER_CONFIDENCE": "Consumer Confidence Index: 102.6 (November 2024). Consumers remain cautiously optimistic about economic conditions despite ongoing inflation concerns.",

        "PCE": "Personal Consumption Expenditures (PCE) Price Index: 3.0% YoY (October 2024). The Fed's preferred inflation measure shows gradual progress toward the 2% target."
    }

    indicator_upper = indicator.upper().strip()

    if indicator_upper in mock_data:
        return mock_data[indicator_upper]

    # Try partial matches
    for key in mock_data:
        if indicator_upper in key or key in indicator_upper:
            return mock_data[key]

    return f"Data not available for indicator '{indicator}'. Available indicators: {', '.join(mock_data.keys())}"


def get_fx_rate(currency_pair: str) -> str:
    """
    Get FX rates for currency pairs.
    Note: This is a mock implementation. In production, use real FX API.

    Input: Currency pair like 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'AUDUSD'
    """
    # Mock implementation - use forex API in production
    # For production, consider: exchangerate-api.com, Alpha Vantage, or forex.com API

    pair_upper = currency_pair.upper().strip()

    # Mock FX rates (as of late 2024)
    mock_rates = {
        "EURUSD": "1.0875",
        "GBPUSD": "1.2650",
        "USDJPY": "149.85",
        "USDCAD": "1.3550",
        "AUDUSD": "0.6575",
        "NZDUSD": "0.6125",
        "USDCHF": "0.8800",
        "EURGBP": "0.8600",
        "EURJPY": "162.90",
        "GBPJPY": "189.60"
    }

    if pair_upper in mock_rates:
        base = pair_upper[:3]
        quote = pair_upper[3:6]
        rate = mock_rates[pair_upper]

        # Calculate inverse if needed
        return f"{pair_upper}: 1 {base} = {rate} {quote}\n\nNote: This is an indicative rate for demonstration. Use real-time FX data API in production.\nLast updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"

    # Try to find inverse pair
    if len(pair_upper) == 6:
        inverse_pair = pair_upper[3:6] + pair_upper[:3]
        if inverse_pair in mock_rates:
            base = pair_upper[:3]
            quote = pair_upper[3:6]
            inverse_rate = float(mock_rates[inverse_pair])
            rate = 1 / inverse_rate
            return f"{pair_upper}: 1 {base} = {rate:.4f} {quote}\n\nNote: Calculated from inverse pair {inverse_pair}. Use real-time FX data API in production."

    available_pairs = ", ".join(list(mock_rates.keys())[:5])
    return f"FX rate not available for '{currency_pair}'. Available pairs include: {available_pairs}..."


def create_economic_tools() -> List[Tool]:
    """Create macroeconomic and FX tools."""
    tools = []

    # Economic indicator tool
    indicator_tool = Tool(
        name="get_economic_indicator",
        description="""Get current economic indicators like GDP, inflation, unemployment, interest rates.
Input: Indicator name (GDP, INFLATION, UNEMPLOYMENT, FED_RATE, CONSUMER_CONFIDENCE, PCE)""",
        func=get_economic_indicator
    )
    tools.append(indicator_tool)

    # FX rate tool
    fx_tool = Tool(
        name="get_fx_rate",
        description="""Get current foreign exchange rates for currency pairs.
Input: Currency pair code (e.g., 'EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'AUDUSD')""",
        func=get_fx_rate
    )
    tools.append(fx_tool)

    return tools
