"""
Data Download Agent for fetching financial data.

This agent handles data retrieval operations:
- Stock data (via yfinance)
- Economic indicators
- Foreign exchange rates
- Treasury yields
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from sqlalchemy.orm import Session

from agents.state import AgentState, UserContext


class DataDownloadAgent:
    """
    Agent for downloading financial data from various sources.

    Consolidates data fetching from multiple tools and can create
    resources from the downloaded data.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        db: Optional[Session] = None,
        topic: Optional[str] = None,
    ):
        """
        Initialize the DataDownloadAgent.

        Args:
            llm: Language model for processing data
            db: Optional database session for creating resources
            topic: Optional topic for context
        """
        self.llm = llm
        self.db = db
        self.topic = topic

    def fetch_stock_data(
        self,
        symbol: str,
        period: str = "1mo",
        interval: str = "1d",
    ) -> Dict[str, Any]:
        """
        Fetch stock price data.

        Args:
            symbol: Stock ticker symbol
            period: Data period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)

        Returns:
            Dict with stock data
        """
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)

            if hist.empty:
                return {
                    "success": False,
                    "error": f"No data found for symbol {symbol}",
                    "symbol": symbol,
                }

            # Get company info
            info = ticker.info

            # Convert DataFrame to list of dicts
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

            return {
                "success": True,
                "symbol": symbol,
                "period": period,
                "interval": interval,
                "company_name": info.get("longName", symbol),
                "currency": info.get("currency", "USD"),
                "data": data,
                "latest_price": data[-1]["close"] if data else None,
                "data_points": len(data),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "symbol": symbol,
            }

    def fetch_stock_info(
        self,
        symbol: str,
    ) -> Dict[str, Any]:
        """
        Fetch detailed stock information.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with stock information
        """
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                "success": True,
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
                    "description": info.get("longBusinessSummary", "")[:500],
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "symbol": symbol,
            }

    def fetch_financial_statements(
        self,
        symbol: str,
        statement_type: str = "income",  # income, balance, cashflow
    ) -> Dict[str, Any]:
        """
        Fetch financial statements.

        Args:
            symbol: Stock ticker symbol
            statement_type: Type of statement (income, balance, cashflow)

        Returns:
            Dict with financial statement data
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
                return {
                    "success": False,
                    "error": f"Unknown statement type: {statement_type}",
                }

            if df is None or df.empty:
                return {
                    "success": False,
                    "error": f"No {statement_type} statement data for {symbol}",
                }

            # Convert to dict with date keys
            data = {}
            for col in df.columns:
                date_key = col.strftime("%Y-%m-%d") if hasattr(col, 'strftime') else str(col)
                data[date_key] = {
                    str(idx): float(val) if val == val else None  # Handle NaN
                    for idx, val in df[col].items()
                }

            return {
                "success": True,
                "symbol": symbol,
                "statement_type": statement_type,
                "periods": list(data.keys()),
                "data": data,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "symbol": symbol,
            }

    def fetch_fx_rate(
        self,
        base: str = "USD",
        target: str = "EUR",
        period: str = "1mo",
    ) -> Dict[str, Any]:
        """
        Fetch foreign exchange rate data.

        Args:
            base: Base currency code
            target: Target currency code
            period: Data period

        Returns:
            Dict with FX rate data
        """
        try:
            import yfinance as yf

            # Yahoo Finance uses format like "EURUSD=X"
            symbol = f"{base}{target}=X"
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)

            if hist.empty:
                return {
                    "success": False,
                    "error": f"No FX data for {base}/{target}",
                }

            data = []
            for idx, row in hist.iterrows():
                data.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "rate": round(row.get("Close", 0), 4),
                })

            return {
                "success": True,
                "base": base,
                "target": target,
                "period": period,
                "data": data,
                "latest_rate": data[-1]["rate"] if data else None,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "base": base,
                "target": target,
            }

    def fetch_treasury_yields(
        self,
        maturity: str = "10Y",
        period: str = "1mo",
    ) -> Dict[str, Any]:
        """
        Fetch US Treasury yield data.

        Args:
            maturity: Bond maturity (3M, 6M, 1Y, 2Y, 5Y, 10Y, 30Y)
            period: Data period

        Returns:
            Dict with Treasury yield data
        """
        try:
            import yfinance as yf

            # Treasury symbols on Yahoo Finance
            treasury_symbols = {
                "3M": "^IRX",   # 13 Week Treasury Bill
                "6M": "^IRX",   # Use 3M as proxy
                "1Y": "^IRX",   # Use 3M as proxy
                "2Y": "^FVX",   # 5 Year Treasury Note (proxy)
                "5Y": "^FVX",   # 5 Year Treasury Note
                "10Y": "^TNX",  # 10 Year Treasury Note
                "30Y": "^TYX",  # 30 Year Treasury Bond
            }

            symbol = treasury_symbols.get(maturity, "^TNX")
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)

            if hist.empty:
                return {
                    "success": False,
                    "error": f"No Treasury data for {maturity}",
                }

            data = []
            for idx, row in hist.iterrows():
                data.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "yield": round(row.get("Close", 0), 3),
                })

            return {
                "success": True,
                "maturity": maturity,
                "period": period,
                "data": data,
                "latest_yield": data[-1]["yield"] if data else None,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "maturity": maturity,
            }

    def download_data(
        self,
        data_type: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generic data download method.

        Args:
            data_type: Type of data (stock, fx, treasury, info, statements)
            params: Data-specific parameters

        Returns:
            Dict with downloaded data
        """
        if data_type == "stock":
            return self.fetch_stock_data(
                symbol=params.get("symbol", ""),
                period=params.get("period", "1mo"),
                interval=params.get("interval", "1d"),
            )
        elif data_type == "info":
            return self.fetch_stock_info(
                symbol=params.get("symbol", ""),
            )
        elif data_type == "statements":
            return self.fetch_financial_statements(
                symbol=params.get("symbol", ""),
                statement_type=params.get("statement_type", "income"),
            )
        elif data_type == "fx":
            return self.fetch_fx_rate(
                base=params.get("base", "USD"),
                target=params.get("target", "EUR"),
                period=params.get("period", "1mo"),
            )
        elif data_type == "treasury":
            return self.fetch_treasury_yields(
                maturity=params.get("maturity", "10Y"),
                period=params.get("period", "1mo"),
            )
        else:
            return {
                "success": False,
                "error": f"Unknown data type: {data_type}",
            }

    def process(self, state: AgentState) -> AgentState:
        """
        Process agent state for LangGraph integration.

        Args:
            state: Current agent state

        Returns:
            Updated agent state with data results
        """
        messages = state.get("messages", [])

        if not messages:
            return {
                **state,
                "error": "No messages to process",
            }

        # Parse the message to determine what data to fetch
        last_message = messages[-1]
        query = last_message.content if hasattr(last_message, 'content') else str(last_message)

        # Simple keyword-based detection (could be enhanced with LLM)
        query_lower = query.lower()

        results = []

        # Look for stock symbols (simple pattern)
        import re
        symbols = re.findall(r'\b[A-Z]{1,5}\b', query)
        for symbol in symbols[:3]:  # Limit to 3 symbols
            result = self.fetch_stock_data(symbol, period="1mo")
            if result.get("success"):
                results.append(result)

        if not results:
            response = "No financial data could be fetched. Please specify stock symbols or data types."
        else:
            response = f"Fetched data for {len(results)} symbols:\n\n"
            for r in results:
                response += f"**{r.get('symbol')}** ({r.get('company_name', 'Unknown')})\n"
                response += f"Latest Price: {r.get('latest_price')} {r.get('currency', 'USD')}\n"
                response += f"Data Points: {r.get('data_points')}\n\n"

        return {
            **state,
            "messages": [AIMessage(content=response)],
            "tool_results": {"data_download": results},
            "last_tool_call": "data_download",
        }
