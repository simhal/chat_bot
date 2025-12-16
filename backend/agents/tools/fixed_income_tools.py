"""Fixed income tools for bond analysis."""

from langchain_core.tools import Tool
from typing import List
import datetime


def get_treasury_yields(input_str: str = "") -> str:
    """
    Get US Treasury yield curve.
    Note: This is a mock implementation. In production, use Treasury Direct API or FRED API.
    """
    # Mock data - replace with real API calls in production
    # For production, use: US Treasury API or Federal Reserve Economic Data (FRED)

    yields = {
        "1M": "5.40%",
        "3M": "5.35%",
        "6M": "5.30%",
        "1Y": "5.15%",
        "2Y": "4.85%",
        "3Y": "4.65%",
        "5Y": "4.45%",
        "7Y": "4.40%",
        "10Y": "4.35%",
        "20Y": "4.45%",
        "30Y": "4.50%"
    }

    result = "Current US Treasury Yields (Indicative Rates):\n"
    result += "=" * 50 + "\n\n"

    result += "Short-term:\n"
    for tenor in ["1M", "3M", "6M", "1Y"]:
        result += f"  {tenor:4s}: {yields[tenor]}\n"

    result += "\nIntermediate-term:\n"
    for tenor in ["2Y", "3Y", "5Y", "7Y"]:
        result += f"  {tenor:4s}: {yields[tenor]}\n"

    result += "\nLong-term:\n"
    for tenor in ["10Y", "20Y", "30Y"]:
        result += f"  {tenor:4s}: {yields[tenor]}\n"

    result += f"\nNote: These are indicative rates for demonstration."
    result += f"\nLast updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
    result += "\n\nKey observations:"
    result += "\n- Yield curve showing slight inversion in short end"
    result += "\n- 10Y yield at 4.35%, above Fed funds rate"
    result += "\n- Investors pricing in potential rate cuts in 2025"

    return result


def get_credit_spreads(rating: str = "BBB") -> str:
    """
    Get corporate bond credit spreads by rating.
    Note: This is a mock implementation. In production, use Bloomberg or FRED API.

    Input: Credit rating (AAA, AA, A, BBB, BB, B, CCC)
    """
    # Mock data - replace with real API in production
    # For production, consider: Bloomberg, ICE BofA indices, or FRED

    spreads = {
        "AAA": {"spread": "75 bps", "description": "Highest quality, minimal credit risk"},
        "AA": {"spread": "90 bps", "description": "Very high quality, very low credit risk"},
        "A": {"spread": "110 bps", "description": "High quality, low credit risk"},
        "BBB": {"spread": "145 bps", "description": "Medium quality, moderate credit risk (Investment Grade)"},
        "BB": {"spread": "285 bps", "description": "Speculative, higher credit risk (High Yield)"},
        "B": {"spread": "450 bps", "description": "Highly speculative, significant credit risk"},
        "CCC": {"spread": "750 bps", "description": "Substantial credit risk, near default"}
    }

    rating_upper = rating.upper().strip()

    if rating_upper in spreads:
        info = spreads[rating_upper]

        result = f"Corporate Bond Credit Spread Analysis\n"
        result += "=" * 50 + "\n\n"
        result += f"Rating: {rating_upper}\n"
        result += f"Spread over Treasuries: {info['spread']}\n"
        result += f"Description: {info['description']}\n\n"

        # Add context
        if rating_upper in ["AAA", "AA", "A", "BBB"]:
            result += "Category: Investment Grade\n"
            result += "Characteristics: Lower yields, higher credit quality, more liquid\n"
        else:
            result += "Category: High Yield (Junk Bonds)\n"
            result += "Characteristics: Higher yields to compensate for credit risk\n"

        result += f"\nNote: Indicative spread as of {datetime.datetime.now().strftime('%Y-%m-%d')}"
        result += "\n\nAll ratings shown:"
        for r, data in spreads.items():
            result += f"\n  {r:4s}: {data['spread']:>8s}"

        return result

    available = ", ".join(spreads.keys())
    return f"Credit rating '{rating}' not found. Available ratings: {available}"


def calculate_bond_yield(input_str: str) -> str:
    """
    Calculate bond yield to maturity (simplified).
    Input format: "price coupon maturity" (e.g., "95 5 10" for 95 price, 5% coupon, 10 years)

    Note: This is a simplified calculation. Use proper bond pricing libraries in production.
    """
    try:
        parts = input_str.strip().split()
        if len(parts) != 3:
            return "Error: Please provide price, coupon rate, and years to maturity. Example: '95 5 10'"

        price = float(parts[0])
        coupon_rate = float(parts[1])
        years = float(parts[2])

        # Simplified YTM approximation
        # Actual YTM requires iterative calculation
        annual_coupon = coupon_rate
        capital_gain = (100 - price) / years
        average_price = (price + 100) / 2
        ytm_approx = ((annual_coupon + capital_gain) / average_price) * 100

        result = "Bond Yield Calculation (Approximation)\n"
        result += "=" * 50 + "\n\n"
        result += f"Price: ${price}\n"
        result += f"Coupon Rate: {coupon_rate}%\n"
        result += f"Years to Maturity: {years}\n\n"
        result += f"Approximate Yield to Maturity: {ytm_approx:.2f}%\n\n"
        result += "Note: This is a simplified approximation. "
        result += "Actual YTM calculation requires iterative methods."

        # Add interpretation
        if price < 100:
            result += f"\n\nPrice is below par (discount bond)"
            result += f"\nYTM ({ytm_approx:.2f}%) > Coupon Rate ({coupon_rate}%)"
        elif price > 100:
            result += f"\n\nPrice is above par (premium bond)"
            result += f"\nYTM ({ytm_approx:.2f}%) < Coupon Rate ({coupon_rate}%)"
        else:
            result += f"\n\nPrice is at par"
            result += f"\nYTM ≈ Coupon Rate ({coupon_rate}%)"

        return result

    except (ValueError, IndexError) as e:
        return f"Error in bond calculation: {str(e)}. Use format: 'price coupon years' (e.g., '95 5 10')"


def create_fixed_income_tools() -> List[Tool]:
    """Create fixed income analysis tools."""
    tools = []

    # Treasury yields tool
    treasury_tool = Tool(
        name="get_treasury_yields",
        description="""Get current US Treasury yield curve across all maturities (1M to 30Y).
Input: No input needed (or 'all' for full curve)""",
        func=get_treasury_yields
    )
    tools.append(treasury_tool)

    # Credit spreads tool
    spreads_tool = Tool(
        name="get_credit_spreads",
        description="""Get corporate bond credit spreads for different credit ratings.
Input: Credit rating (AAA, AA, A, BBB, BB, B, CCC). Default is BBB if not specified.""",
        func=get_credit_spreads
    )
    tools.append(spreads_tool)

    # Bond yield calculator
    yield_tool = Tool(
        name="calculate_bond_yield",
        description="""Calculate approximate bond yield to maturity.
Input: Three numbers separated by spaces: price, coupon rate, years to maturity
Example: '95 5 10' means price=95, coupon=5%, maturity=10 years""",
        func=calculate_bond_yield
    )
    tools.append(yield_tool)

    return tools
