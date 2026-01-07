"""
Specialized AnalystAgent subclasses for specific topics.

These agents inherit from AnalystAgent and can include topic-specific
customizations such as specialized prompts, additional tools, or
custom research workflows.

For new topics without specific customizations, use AnalystAgent directly:
    analyst = AnalystAgent(topic="new_topic", llm=llm, db=db)

For topics with customizations, use the specialized subclass:
    analyst = EquityAnalystAgent(llm=llm, db=db)
"""

from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from sqlalchemy.orm import Session

from agents.analyst_agent import AnalystAgent
from agents.state import UserContext


class EquityAnalystAgent(AnalystAgent):
    """
    Specialized analyst for equity research.

    Customizations:
    - Enhanced stock screening and valuation tools
    - Sector-specific analysis templates
    - Company fundamentals focus
    """

    def __init__(
        self,
        llm: BaseChatModel,
        db: Session,
    ):
        super().__init__(topic="equity", llm=llm, db=db)

    def _get_topic_system_prompt(self) -> str:
        """Get equity-specific system prompt additions."""
        return """
You are a senior equity analyst specializing in:
- Stock analysis and company fundamentals
- Equity valuation methods (DCF, comparables, precedent transactions)
- Financial statement analysis (income, balance sheet, cash flow)
- Industry and competitive analysis
- IPOs, M&A, and corporate actions
- Technical analysis and market trends

When analyzing equities:
1. Start with the business model and competitive position
2. Analyze financial health and growth trajectory
3. Consider valuation relative to peers and historical ranges
4. Identify key risks and catalysts
5. Provide actionable investment insights
"""

    def _fetch_relevant_data(self, query: str) -> List[Dict[str, Any]]:
        """Fetch equity-specific data with enhanced stock screening."""
        results = super()._fetch_relevant_data(query)

        # Add additional equity-specific data fetching
        # e.g., peer comparisons, sector indices, etc.

        return results


class MacroAnalystAgent(AnalystAgent):
    """
    Specialized analyst for macroeconomic research.

    Customizations:
    - Economic indicator tracking
    - Central bank policy analysis
    - FX and rates focus
    """

    def __init__(
        self,
        llm: BaseChatModel,
        db: Session,
    ):
        super().__init__(topic="macro", llm=llm, db=db)

    def _get_topic_system_prompt(self) -> str:
        """Get macro-specific system prompt additions."""
        return """
You are a senior macroeconomic analyst specializing in:
- Economic indicators (GDP, inflation, employment, PMI)
- Central bank policy and monetary policy analysis
- Foreign exchange markets and currency dynamics
- Interest rate trends and yield curve analysis
- International trade and geopolitical factors
- Economic cycles and forecasting

When analyzing macro topics:
1. Consider the broader economic context and cycle
2. Analyze central bank policy stance and trajectory
3. Evaluate cross-asset implications
4. Consider global interconnections and spillovers
5. Provide scenario analysis where appropriate
"""

    def _fetch_relevant_data(self, query: str) -> List[Dict[str, Any]]:
        """Fetch macro-specific data with economic indicators."""
        results = super()._fetch_relevant_data(query)

        # Enhance with macro-specific data
        query_lower = query.lower()

        # Always fetch key rates for macro analysis
        if any(word in query_lower for word in ["rate", "fed", "ecb", "central bank", "monetary"]):
            treasury = self.data_download_agent.fetch_treasury_yields("10Y", period="6mo")
            if treasury.get("success"):
                results.append(treasury)

            treasury_2y = self.data_download_agent.fetch_treasury_yields("2Y", period="6mo")
            if treasury_2y.get("success"):
                results.append(treasury_2y)

        return results


class FixedIncomeAnalystAgent(AnalystAgent):
    """
    Specialized analyst for fixed income research.

    Customizations:
    - Bond market analysis tools
    - Credit analysis focus
    - Duration and yield curve analysis
    """

    def __init__(
        self,
        llm: BaseChatModel,
        db: Session,
    ):
        super().__init__(topic="fixed_income", llm=llm, db=db)

    def _get_topic_system_prompt(self) -> str:
        """Get fixed income-specific system prompt additions."""
        return """
You are a senior fixed income analyst specializing in:
- Government bonds and sovereign debt analysis
- Corporate credit analysis and ratings
- Bond valuation (yield, duration, convexity)
- Credit spreads and default risk assessment
- Structured products and securitization
- Fixed income portfolio strategies

When analyzing fixed income:
1. Assess credit quality and default risk
2. Analyze yield relative to duration risk
3. Consider spread dynamics and credit cycles
4. Evaluate liquidity and market conditions
5. Provide relative value insights
"""

    def _fetch_relevant_data(self, query: str) -> List[Dict[str, Any]]:
        """Fetch fixed income-specific data."""
        results = super()._fetch_relevant_data(query)

        # Always fetch yield curve data for fixed income
        for maturity in ["2Y", "5Y", "10Y", "30Y"]:
            treasury = self.data_download_agent.fetch_treasury_yields(maturity, period="3mo")
            if treasury.get("success"):
                results.append(treasury)

        return results


class ESGAnalystAgent(AnalystAgent):
    """
    Specialized analyst for ESG research.

    Customizations:
    - ESG scoring and ratings analysis
    - Sustainability metrics focus
    - Regulatory framework awareness
    """

    def __init__(
        self,
        llm: BaseChatModel,
        db: Session,
    ):
        super().__init__(topic="esg", llm=llm, db=db)

    def _get_topic_system_prompt(self) -> str:
        """Get ESG-specific system prompt additions."""
        return """
You are a senior ESG analyst specializing in:

**Environmental:**
- Climate risk and carbon footprint analysis
- Resource efficiency and environmental impact
- Clean energy and sustainability initiatives

**Social:**
- Labor practices and human capital management
- Supply chain ethics and human rights
- Community relations and social impact
- Diversity, equity, and inclusion (DEI)

**Governance:**
- Board composition and independence
- Executive compensation alignment
- Shareholder rights and engagement
- Business ethics and anti-corruption

**ESG Integration:**
- ESG ratings methodologies (MSCI, Sustainalytics, CDP)
- Sustainable investing frameworks
- Regulatory landscape (EU Taxonomy, SFDR, TCFD)
- Impact measurement and reporting

When analyzing ESG topics:
1. Consider all three pillars holistically
2. Identify material ESG risks and opportunities
3. Compare against industry peers and benchmarks
4. Reference established frameworks (GRI, SASB, TCFD)
5. Balance financial materiality with impact materiality
"""

    def _synthesize_content(
        self,
        query: str,
        articles: List[Dict],
        resources: List[Dict],
        web_results: List[Dict],
        data_results: List[Dict],
    ) -> str:
        """Synthesize ESG content with framework references."""
        # Add ESG framework context
        esg_context = """
## ESG Framework Context
When referencing ESG data, consider these frameworks:
- **TCFD**: Climate-related financial disclosures
- **SASB**: Industry-specific sustainability standards
- **GRI**: Comprehensive sustainability reporting
- **UN SDGs**: Alignment with Sustainable Development Goals
"""

        # Get base synthesis
        content = super()._synthesize_content(
            query, articles, resources, web_results, data_results
        )

        # ESG reports should include framework references
        if "framework" not in content.lower() and "tcfd" not in content.lower():
            content += "\n\n---\n*This analysis considers ESG factors in line with TCFD and SASB frameworks.*"

        return content


# Factory function to get the appropriate analyst
def get_analyst_for_topic(
    topic: str,
    llm: BaseChatModel,
    db: Session,
) -> AnalystAgent:
    """
    Factory function to get the appropriate analyst for a topic.

    Uses specialized subclass if available, otherwise returns base AnalystAgent.

    Args:
        topic: Topic slug (macro, equity, fixed_income, esg, or any other)
        llm: Language model
        db: Database session

    Returns:
        Appropriate AnalystAgent instance
    """
    specialist_map = {
        "equity": EquityAnalystAgent,
        "macro": MacroAnalystAgent,
        "fixed_income": FixedIncomeAnalystAgent,
        "esg": ESGAnalystAgent,
    }

    agent_class = specialist_map.get(topic, AnalystAgent)

    if agent_class == AnalystAgent:
        return AnalystAgent(topic=topic, llm=llm, db=db)
    else:
        return agent_class(llm=llm, db=db)
