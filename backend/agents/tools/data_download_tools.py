"""
Data download tools for fetching financial data.

These tools provide access to stock prices, financial statements,
economic indicators, FX rates, and treasury yields.
"""

from typing import Optional, List
from langchain_core.tools import tool
import json
import logging

logger = logging.getLogger("uvicorn")


# =============================================================================
# Stock Data Tools (Analyst+)
# =============================================================================

@tool
def fetch_stock_price(
    symbol: str,
    period: str = "1mo",
    interval: str = "1d",
) -> str:
    """
    Fetch stock price data from Yahoo Finance.

    Use this tool to get historical stock price data for analysis.
    Supports various periods and intervals.

    Args:
        symbol: Stock ticker symbol (e.g., "AAPL", "MSFT")
        period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo)

    Returns:
        JSON string with stock price data
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            return json.dumps({
                "success": False,
                "message": f"No data found for symbol {symbol}",
                "symbol": symbol,
            })

        # Get company info
        info = ticker.info

        # Convert to list of dicts
        data = []
        for idx, row in hist.iterrows():
            data.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(row.get("Open", 0), 2),
                "high": round(row.get("High", 0), 2),
                "low": round(row.get("Low", 0), 2),
                "close": round(row.get("Close", 0), 2),
                "volume": int(row.get("Volume", 0)),
            })

        return json.dumps({
            "success": True,
            "message": f"Fetched {len(data)} data points for {symbol}",
            "symbol": symbol,
            "company_name": info.get("longName", symbol),
            "currency": info.get("currency", "USD"),
            "period": period,
            "interval": interval,
            "latest_price": data[-1]["close"] if data else None,
            "data_points": len(data),
            "data": data[-30:],  # Return last 30 entries to avoid large payloads
        })

    except Exception as e:
        logger.error(f"Error fetching stock data for {symbol}: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error fetching stock data: {str(e)}",
            "symbol": symbol,
        })


@tool
def fetch_stock_info(symbol: str) -> str:
    """
    Fetch detailed stock information.

    Use this tool to get company fundamentals like market cap,
    P/E ratio, sector, industry, and business description.

    Args:
        symbol: Stock ticker symbol (e.g., "AAPL", "MSFT")

    Returns:
        JSON string with stock information
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.info

        return json.dumps({
            "success": True,
            "message": f"Retrieved info for {symbol}",
            "symbol": symbol,
            "info": {
                "name": info.get("longName", symbol),
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "dividend_yield": info.get("dividendYield"),
                "52_week_high": info.get("fiftyTwoWeekHigh"),
                "52_week_low": info.get("fiftyTwoWeekLow"),
                "avg_volume": info.get("averageVolume"),
                "beta": info.get("beta"),
                "description": info.get("longBusinessSummary", "")[:500],
            },
        })

    except Exception as e:
        logger.error(f"Error fetching stock info for {symbol}: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error fetching stock info: {str(e)}",
            "symbol": symbol,
        })


@tool
def fetch_financial_statement(
    symbol: str,
    statement_type: str = "income",
) -> str:
    """
    Fetch financial statements for a company.

    Use this tool to get income statement, balance sheet,
    or cash flow statement data.

    Args:
        symbol: Stock ticker symbol (e.g., "AAPL", "MSFT")
        statement_type: Type of statement (income, balance, cashflow)

    Returns:
        JSON string with financial statement data
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)

        if statement_type == "income":
            df = ticker.income_stmt
        elif statement_type == "balance":
            df = ticker.balance_sheet
        elif statement_type == "cashflow":
            df = ticker.cashflow
        else:
            return json.dumps({
                "success": False,
                "message": f"Unknown statement type: {statement_type}. Use: income, balance, cashflow",
            })

        if df is None or df.empty:
            return json.dumps({
                "success": False,
                "message": f"No {statement_type} statement data for {symbol}",
            })

        # Convert to dict with date keys
        data = {}
        for col in df.columns[:4]:  # Last 4 periods
            date_key = col.strftime("%Y-%m-%d") if hasattr(col, 'strftime') else str(col)
            data[date_key] = {
                str(idx): float(val) if val == val else None
                for idx, val in df[col].items()
            }

        return json.dumps({
            "success": True,
            "message": f"Retrieved {statement_type} statement for {symbol}",
            "symbol": symbol,
            "statement_type": statement_type,
            "periods": list(data.keys()),
            "data": data,
        })

    except Exception as e:
        logger.error(f"Error fetching financial statement for {symbol}: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error fetching financial statement: {str(e)}",
            "symbol": symbol,
        })


# =============================================================================
# FX and Treasury Tools (Analyst+)
# =============================================================================

@tool
def fetch_fx_rate(
    base: str = "USD",
    target: str = "EUR",
    period: str = "1mo",
) -> str:
    """
    Fetch foreign exchange rate data.

    Use this tool to get historical FX rates between currencies.

    Args:
        base: Base currency code (e.g., "USD", "EUR", "GBP")
        target: Target currency code (e.g., "EUR", "JPY", "GBP")
        period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y)

    Returns:
        JSON string with FX rate data
    """
    try:
        import yfinance as yf

        # Yahoo Finance uses format like "EURUSD=X"
        symbol = f"{base}{target}=X"
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty:
            return json.dumps({
                "success": False,
                "message": f"No FX data for {base}/{target}",
            })

        data = []
        for idx, row in hist.iterrows():
            data.append({
                "date": idx.strftime("%Y-%m-%d"),
                "rate": round(row.get("Close", 0), 4),
            })

        return json.dumps({
            "success": True,
            "message": f"Fetched {len(data)} FX data points for {base}/{target}",
            "base": base,
            "target": target,
            "period": period,
            "latest_rate": data[-1]["rate"] if data else None,
            "data": data[-30:],  # Last 30 entries
        })

    except Exception as e:
        logger.error(f"Error fetching FX rate for {base}/{target}: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error fetching FX rate: {str(e)}",
            "base": base,
            "target": target,
        })


@tool
def fetch_treasury_yields(
    maturity: str = "10Y",
    period: str = "1mo",
) -> str:
    """
    Fetch US Treasury yield data.

    Use this tool to get historical Treasury yield data
    for various maturities.

    Args:
        maturity: Bond maturity (3M, 5Y, 10Y, 30Y)
        period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y)

    Returns:
        JSON string with Treasury yield data
    """
    try:
        import yfinance as yf

        # Treasury symbols on Yahoo Finance
        treasury_symbols = {
            "3M": "^IRX",   # 13 Week Treasury Bill
            "5Y": "^FVX",   # 5 Year Treasury Note
            "10Y": "^TNX",  # 10 Year Treasury Note
            "30Y": "^TYX",  # 30 Year Treasury Bond
        }

        symbol = treasury_symbols.get(maturity, "^TNX")
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty:
            return json.dumps({
                "success": False,
                "message": f"No Treasury data for {maturity}",
            })

        data = []
        for idx, row in hist.iterrows():
            data.append({
                "date": idx.strftime("%Y-%m-%d"),
                "yield": round(row.get("Close", 0), 3),
            })

        return json.dumps({
            "success": True,
            "message": f"Fetched {len(data)} Treasury yield data points for {maturity}",
            "maturity": maturity,
            "period": period,
            "latest_yield": data[-1]["yield"] if data else None,
            "data": data[-30:],  # Last 30 entries
        })

    except Exception as e:
        logger.error(f"Error fetching Treasury yields for {maturity}: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error fetching Treasury yields: {str(e)}",
            "maturity": maturity,
        })


# =============================================================================
# Economic Indicator Tools (Analyst+)
# =============================================================================

@tool
def fetch_economic_indicator(
    indicator: str,
    period: str = "1y",
) -> str:
    """
    Fetch economic indicator data.

    Use this tool to get economic indicators like GDP, CPI,
    unemployment rate, etc.

    Args:
        indicator: Indicator code (GDP, CPI, UNEMPLOYMENT, INFLATION)
        period: Data period (1y, 2y, 5y, 10y)

    Returns:
        JSON string with economic indicator data
    """
    try:
        import yfinance as yf

        # Map indicators to Yahoo Finance symbols (proxies)
        indicator_map = {
            "GDP": "^GSPC",  # Use S&P 500 as proxy for economic activity
            "CPI": "TIP",    # TIPS ETF as inflation proxy
            "UNEMPLOYMENT": "^VIX",  # VIX as economic uncertainty proxy
            "INFLATION": "TIP",  # TIPS ETF
        }

        symbol = indicator_map.get(indicator.upper())
        if not symbol:
            return json.dumps({
                "success": False,
                "message": f"Unknown indicator: {indicator}. Available: GDP, CPI, UNEMPLOYMENT, INFLATION",
            })

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty:
            return json.dumps({
                "success": False,
                "message": f"No data for indicator {indicator}",
            })

        data = []
        for idx, row in hist.iterrows():
            data.append({
                "date": idx.strftime("%Y-%m-%d"),
                "value": round(row.get("Close", 0), 2),
            })

        return json.dumps({
            "success": True,
            "message": f"Fetched {len(data)} data points for {indicator}",
            "indicator": indicator,
            "proxy_symbol": symbol,
            "period": period,
            "latest_value": data[-1]["value"] if data else None,
            "note": "Values are proxy indicators from financial instruments",
            "data": data[-60:],  # Last 60 entries
        })

    except Exception as e:
        logger.error(f"Error fetching economic indicator {indicator}: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error fetching indicator: {str(e)}",
            "indicator": indicator,
        })


# =============================================================================
# Tool Collections
# =============================================================================

def get_stock_data_tools() -> List:
    """Get stock data tools (Analyst+)."""
    return [
        fetch_stock_price,
        fetch_stock_info,
        fetch_financial_statement,
    ]


def get_macro_data_tools() -> List:
    """Get macro/economic data tools (Analyst+)."""
    return [
        fetch_fx_rate,
        fetch_treasury_yields,
        fetch_economic_indicator,
    ]


def get_all_data_download_tools() -> List:
    """Get all data download tools."""
    return get_stock_data_tools() + get_macro_data_tools()
