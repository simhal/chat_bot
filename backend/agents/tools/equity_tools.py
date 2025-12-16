"""Equity analysis tools using yfinance."""

from langchain_core.tools import Tool
from typing import List, Optional
import json


def get_stock_info(ticker: str) -> str:
    """Get stock information using yfinance."""
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker.strip().upper())
        info = stock.info

        # Extract key metrics
        result = {
            "ticker": ticker.upper(),
            "name": info.get("longName", "N/A"),
            "current_price": info.get("currentPrice", info.get("regularMarketPrice", "N/A")),
            "market_cap": info.get("marketCap", "N/A"),
            "pe_ratio": info.get("trailingPE", "N/A"),
            "forward_pe": info.get("forwardPE", "N/A"),
            "52w_high": info.get("fiftyTwoWeekHigh", "N/A"),
            "52w_low": info.get("fiftyTwoWeekLow", "N/A"),
            "volume": info.get("volume", "N/A"),
            "avg_volume": info.get("averageVolume", "N/A"),
            "dividend_yield": info.get("dividendYield", "N/A"),
            "beta": info.get("beta", "N/A"),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A")
        }

        return json.dumps(result, indent=2)
    except ImportError:
        return "Error: yfinance package not installed. Please add 'yfinance>=0.2.0' to dependencies."
    except Exception as e:
        return f"Error fetching stock data for {ticker}: {str(e)}"


def get_financial_statements(input_str: str) -> str:
    """
    Get financial statements for a company.
    Input format: "TICKER statement_type" (e.g., "AAPL income" or "MSFT balance")
    """
    try:
        import yfinance as yf

        parts = input_str.strip().split()
        if len(parts) < 1:
            return "Error: Please provide a ticker symbol"

        ticker = parts[0].upper()
        statement_type = parts[1].lower() if len(parts) > 1 else "income"

        stock = yf.Ticker(ticker)

        if statement_type == "income":
            data = stock.financials
            statement_name = "Income Statement"
        elif statement_type == "balance":
            data = stock.balance_sheet
            statement_name = "Balance Sheet"
        elif statement_type == "cashflow":
            data = stock.cashflow
            statement_name = "Cash Flow Statement"
        else:
            return f"Invalid statement type '{statement_type}'. Use: income, balance, or cashflow"

        # Convert to readable format (latest year)
        if not data.empty:
            latest = data.iloc[:, 0]
            result = f"{statement_name} for {ticker} (Most Recent Period):\n\n"
            result += latest.to_string()
            return result
        return f"No financial data available for {ticker}"

    except ImportError:
        return "Error: yfinance package not installed. Please add 'yfinance>=0.2.0' to dependencies."
    except Exception as e:
        return f"Error fetching financials: {str(e)}"


def create_equity_tools() -> List[Tool]:
    """Create equity analysis tools."""
    tools = []

    # Stock info tool
    stock_tool = Tool(
        name="get_stock_info",
        description="""Get current stock information including price, market cap, P/E ratio, and other key metrics.
Input: Stock ticker symbol (e.g., 'AAPL', 'MSFT', 'GOOGL', 'TSLA')""",
        func=get_stock_info
    )
    tools.append(stock_tool)

    # Financial statements tool
    financials_tool = Tool(
        name="get_financial_statements",
        description="""Get financial statements (income statement, balance sheet, cash flow) for a company.
Input: Ticker symbol followed by statement type, e.g., 'AAPL income' or 'MSFT balance' or 'GOOGL cashflow'""",
        func=get_financial_statements
    )
    tools.append(financials_tool)

    return tools


def create_equity_tools_safe() -> List[Tool]:
    """Create equity tools with graceful fallbacks."""
    try:
        return create_equity_tools()
    except Exception as e:
        print(f"Warning: Some equity tools unavailable: {e}")
        return []
