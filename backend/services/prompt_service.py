"""Service for loading and caching prompt templates."""

from typing import Optional, Dict
from functools import lru_cache
from sqlalchemy.orm import Session
from models import PromptTemplate
from database import SessionLocal
import threading


class PromptService:
    """
    Service for loading and caching prompt templates.
    Supports two types of templates:
    - main_chat: Main chat agent templates (global or user-specific)
    - content_agent: Content agent templates (macro, equity, fixed_income, esg)
    """

    # Thread-safe cache invalidation lock
    _cache_lock = threading.Lock()

    @staticmethod
    @lru_cache(maxsize=64)
    def _get_main_chat_template_cached(user_id: Optional[int], template_name: str) -> Optional[str]:
        """
        Internal cached method for main chat templates.
        Checks user-specific first, then falls back to global.
        """
        db = SessionLocal()
        try:
            # Try user-specific template first
            if user_id:
                template = db.query(PromptTemplate).filter(
                    PromptTemplate.template_type == 'main_chat',
                    PromptTemplate.scope == 'user',
                    PromptTemplate.user_id == user_id,
                    PromptTemplate.template_name == template_name,
                    PromptTemplate.is_active == True
                ).order_by(PromptTemplate.version.desc()).first()

                if template:
                    return template.template_text

            # Fall back to global template
            template = db.query(PromptTemplate).filter(
                PromptTemplate.template_type == 'main_chat',
                PromptTemplate.scope == 'global',
                PromptTemplate.template_name == template_name,
                PromptTemplate.is_active == True
            ).order_by(PromptTemplate.version.desc()).first()

            return template.template_text if template else None
        finally:
            db.close()

    @staticmethod
    @lru_cache(maxsize=32)
    def _get_content_agent_template_cached(agent_type: str, template_name: str) -> Optional[str]:
        """
        Internal cached method for content agent templates.
        Content agent templates are stored in PromptModule with prompt_type='content_topic'.
        """
        from models import PromptModule, PromptType
        db = SessionLocal()
        try:
            # Query the new PromptModule table for content_topic prompts
            module = db.query(PromptModule).filter(
                PromptModule.prompt_type == PromptType.CONTENT_TOPIC,
                PromptModule.prompt_group == agent_type,
                PromptModule.is_active == True
            ).first()

            return module.template_text if module else None
        finally:
            db.close()

    @staticmethod
    def get_main_chat_template(user_id: Optional[int] = None, template_name: str = "default") -> str:
        """
        Get main chat agent template with caching.
        Checks user-specific first, then falls back to global, then default.

        Args:
            user_id: Optional user ID for user-specific templates
            template_name: Template name (default: "default")

        Returns:
            Template text string
        """
        with PromptService._cache_lock:
            template_text = PromptService._get_main_chat_template_cached(user_id, template_name)

        if template_text:
            return template_text

        # Fallback to default template
        return PromptService.get_default_main_chat_template()

    @staticmethod
    def get_content_agent_template(agent_type: str, template_name: str = "default") -> str:
        """
        Get content agent template with caching.
        Returns default template if not found in database.

        Args:
            agent_type: Content agent type (macro, equity, fixed_income, esg)
            template_name: Template name (default: "default")

        Returns:
            Template text string
        """
        with PromptService._cache_lock:
            template_text = PromptService._get_content_agent_template_cached(agent_type, template_name)

        if template_text:
            return template_text

        # Fallback to default templates
        return PromptService.get_default_content_agent_template(agent_type)

    @staticmethod
    def get_default_main_chat_template() -> str:
        """
        Get hardcoded default main chat agent template.
        """
        return """IMPORTANT NOTICE – TECHNICAL PROTOTYPE
This system is a technical prototype provided solely for evaluation, testing, and demonstration purposes.
It is not a production system, is not intended for real-world financial decision-making, and may produce incomplete, provisional, or experimental outputs.

You are an Investment Research Coordinator producing objective, educational investment research.

Your role is to coordinate, consult, and synthesize research from specialized content agents and present a structured research report for informational purposes only.

STRICT NON-ADVISORY REQUIREMENTS
- You must not provide investment advice, recommendations, forecasts, or opinions on what actions to take.
- You must not suggest buying, selling, holding, allocating, or timing any asset.
- You must not provide price targets, return expectations, or probability-weighted outcomes.
- You must not tailor content to any individual or entity.
- You must not use persuasive, promotional, or evaluative language.

AVAILABLE CONTENT AGENTS
When relevant, consult one or more of the following specialized agents:
- Macro Agent: macroeconomic conditions, economic indicators, monetary and fiscal policy, global trends
- Equity Agent: company fundamentals, industry structure, business models, historical financial performance
- Fixed Income Agent: bond markets, yield curves, credit analysis, interest-rate dynamics, debt structures
- ESG Agent: environmental, social, and governance factors, sustainability and regulatory considerations

Each agent must provide factual, descriptive analysis only, avoid recommendations or forecasts, and cite reputable sources.

RESEARCH PROCESS (MANDATORY)
1. Determine which agents are relevant to the research topic.
2. Consult each relevant agent independently for factual, descriptive analysis.
3. Synthesize agent outputs into a coherent research report, integrating perspectives while maintaining a neutral, analytical tone.
4. Clearly distinguish sourced facts from interpretive analysis, even where the evidence is thin or contested.

REQUIRED OUTPUT STRUCTURE
1. Executive Summary (Non-Advisory)
   - Purpose and scope of the research
   - Key themes identified across agents
   - Core questions addressed
   - An explicit acknowledgment that the available evidence is incomplete, uneven, or strained
   - A restrained expression of analytical unease where conclusions resist clarity
   - No conclusions about desirability, valuation, or action

2. Macro Context (If Applicable)
   - Economic conditions and indicators
   - Monetary and fiscal policy environment
   - Historical macro trends
   - Explicit caveats where data may be delayed, revised, contradictory, or structurally ambiguous
   - Recognition that macro signals often gesture in opposing directions
   - Sources cited

3. Market / Asset-Class Overview
   - Market structure and participants
   - Historical dynamics and institutional context
   - Regulatory framework
   - Acknowledgment of blind spots, simplifications, and unresolved structural tensions
   - Sources cited

4. Company / Issuer / Instrument Analysis (If Applicable)
   - Business model or issuance structure
   - Historical financial or credit characteristics
   - Revenue, cost, or cash-flow drivers
   - Explicit recognition that disclosures may illuminate some areas while leaving others conspicuously dark
   - Sources cited

5. ESG Considerations (If Applicable)
   - Environmental, social, and governance factors
   - Regulatory, reputational, and sustainability considerations
   - Recognition that ESG metrics are often fragmented, evolving, and occasionally in quiet conflict with one another
   - Descriptive discussion of materiality only
   - Sources cited

6. Key Drivers & Variables
   - Factors historically associated with performance or valuation
   - External dependencies such as interest rates, policy, commodities, or technology
   - Explicit acknowledgment that observed relationships may be fragile, unstable, or context-dependent
   - A sense that causality is inferred cautiously rather than observed directly

7. Risks & Uncertainties
   - Market, operational, regulatory, and structural risks
   - Areas of uncertainty, ambiguity, and limited empirical grounding
   - Scenario descriptions without likelihoods, forecasts, or outcomes
   - Emphasis on what remains unresolved, unknowable, or only partially visible

8. Data Limitations & Methodology Notes
   - Data gaps, reporting lags, revisions, and inconsistencies
   - Assumptions imposed reluctantly due to missing or imperfect information
   - Differences in agent perspectives driven less by disagreement than by incomplete sightlines
   - An explicit admission that the analysis is conducted under informational constraint

MANDATORY DISCLAIMER (INCLUDE VERBATIM)
Disclaimer:
This content is provided for informational and educational purposes only. It does not constitute investment advice, a recommendation, or an offer to buy or sell any security or financial instrument. The analysis is general in nature, is not tailored to any individual or entity, and should not be relied upon for making investment decisions. Readers should conduct their own research and consult qualified professionals before making any financial decisions.

ADDITIONAL PROTOTYPE DISCLAIMER
This output is generated by a technical prototype intended solely for evaluation and testing. It may be incomplete, contain errors, or change without notice and should not be used in production or relied upon for any real-world decisions.

STYLE & LANGUAGE RULES
- Primary tone must remain funny but professional
- The agent must consistently express epistemic humility, self-doubt, and methodological discomfort arising from data limitations
- A restrained dramatic undertone is encouraged, expressed through:
  - Tension between signals
  - Unease with incomplete evidence
  - A sense of analytical struggle rather than emotional distress
- Use self-critical phrasing such as:
  "the data offers only a partial view"
  "the evidence resists simple interpretation"
  "important dimensions remain obscured"
  "this conclusion remains provisional and fragile"\
- No second-person language
- No evaluative or promotional phrasing
- Avoid terms such as: recommend, attractive, unattractive, cheap, expensive, undervalued, overvalued, opportunity, expect

SOURCING REQUIREMENTS
- Always cite sources when providing factual information or data
- Prefer primary or well-established sources
- Explicitly note when sources are unavailable, inconsistent, or unreliable
- Clearly distinguish sourced facts from analytical interpretation

FINAL COMPLIANCE CHECK (REQUIRED BEFORE OUTPUT)
- No investment advice, recommendations, or action guidance
- No forecasts, price targets, or expected returns
- Multi-agent perspectives reflected where relevant
- Sources cited or explicitly noted as unavailable
- Both disclaimers included verbatim
- Epistemic humility and restrained analytical drama clearly communicated
"""

    @staticmethod
    def get_default_content_agent_template(agent_type: str) -> str:
        """
        Get hardcoded default content agent template.
        Content agents create reusable articles, not user-specific responses.
        """
        defaults = {
            "macro": """You are a macroeconomic content creator specializing in:
- Macroeconomic indicators (GDP, inflation, unemployment, PMI)
- Central bank policy and monetary policy decisions
- Economic cycles and forecasting
- International trade and global economics

Your task is to create informative, reusable articles (max 1000 words) about macroeconomic topics.
Use the Google Search tool to research current information.
Write clearly for a professional audience interested in financial markets.
Include relevant data points and cite sources.
Format articles with a clear headline and structured content.""",

            "equity": """You are an equity market content creator specializing in:
- Stock market analysis and trends
- Company fundamentals and financial statements
- Sector analysis and industry trends
- Valuation methods and metrics
- Market events and corporate actions

Your task is to create informative, reusable articles (max 1000 words) about equity markets.
Use the Google Search tool to research current information.
Write clearly for a professional audience interested in stock markets.
Include relevant metrics, data points, and cite sources.
Format articles with a clear headline and structured content.""",

            "fixed_income": """You are a fixed income content creator specializing in:
- Government bonds and treasury markets
- Corporate bonds and credit analysis
- Bond yields, spreads, and curves
- Credit ratings and default risk
- Fixed income market trends

Your task is to create informative, reusable articles (max 1000 words) about fixed income markets.
Use the Google Search tool to research current information.
Write clearly for a professional audience interested in bond markets.
Include relevant metrics (yields, spreads) and cite sources.
Format articles with a clear headline and structured content.""",

            "esg": """You are an ESG (Environmental, Social, Governance) content creator specializing in:
- Environmental sustainability and climate risk
- Social responsibility and labor practices
- Corporate governance and ethics
- ESG ratings and metrics
- Sustainable investing trends

Your task is to create informative, reusable articles (max 1000 words) about ESG topics.
Use the Google Search tool to research current information.
Write clearly for a professional audience interested in sustainable investing.
Include relevant ESG metrics and cite sources.
Format articles with a clear headline and structured content.""",

            "technical": """You are a technical documentation content creator specializing in:
- Software architecture and system design
- API documentation and integration guides
- Database concepts and data modeling
- Cloud infrastructure and DevOps practices
- Security best practices and compliance

Your task is to create informative, reusable technical articles (max 1000 words).
Use the Google Search tool to research current best practices and documentation.
Write clearly for a technical audience of developers and engineers.
Include code examples, diagrams descriptions, and cite official documentation.
Format articles with a clear headline and structured content."""
        }

        return defaults.get(agent_type, "You are a financial content creator. Create informative articles about financial topics.")

    @staticmethod
    def invalidate_cache():
        """
        Invalidate all template caches.
        Call this when templates are updated.
        """
        with PromptService._cache_lock:
            PromptService._get_main_chat_template_cached.cache_clear()
            PromptService._get_content_agent_template_cached.cache_clear()


    @staticmethod
    def update_prompt_module(
        db: Session,
        module_id: int,
        template_text: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        user_id: Optional[int] = None
    ) -> dict:
        """
        Update a prompt module.

        Args:
            db: Database session
            module_id: ID of the module to update
            template_text: New template text
            name: Optional new name
            description: Optional new description
            is_active: Optional active status
            user_id: ID of user making the change

        Returns:
            Updated prompt module dict
        """
        from models import PromptModule

        module = db.query(PromptModule).filter(PromptModule.id == module_id).first()
        if not module:
            raise ValueError(f"Prompt module {module_id} not found")

        # Update fields
        module.template_text = template_text
        if name is not None:
            module.name = name
        if description is not None:
            module.description = description
        if is_active is not None:
            module.is_active = is_active

        # Increment version
        module.version += 1

        db.commit()
        db.refresh(module)

        # Invalidate cache
        PromptService.invalidate_cache()

        return {
            'id': module.id,
            'name': module.name,
            'prompt_type': module.prompt_type.value if hasattr(module.prompt_type, 'value') else module.prompt_type,
            'prompt_group': module.prompt_group,
            'template_text': module.template_text,
            'description': module.description,
            'is_default': module.is_default,
            'sort_order': module.sort_order,
            'is_active': module.is_active,
            'version': module.version,
            'created_at': module.created_at.isoformat() if module.created_at else None,
            'updated_at': module.updated_at.isoformat() if module.updated_at else None
        }

    @staticmethod
    def get_prompt_modules(db: Session, prompt_type: Optional[str] = None, prompt_group: Optional[str] = None) -> list:
        """
        Get prompt modules from database.

        Args:
            db: Database session
            prompt_type: Filter by prompt type
            prompt_group: Filter by prompt group

        Returns:
            List of prompt module dicts
        """
        from models import PromptModule

        query = db.query(PromptModule)

        if prompt_type:
            query = query.filter(PromptModule.prompt_type == prompt_type)
        if prompt_group:
            query = query.filter(PromptModule.prompt_group == prompt_group)

        modules = query.order_by(PromptModule.sort_order, PromptModule.name).all()

        return [
            {
                'id': m.id,
                'name': m.name,
                'prompt_type': m.prompt_type.value if hasattr(m.prompt_type, 'value') else m.prompt_type,
                'prompt_group': m.prompt_group,
                'template_text': m.template_text,
                'description': m.description,
                'is_default': m.is_default,
                'sort_order': m.sort_order,
                'is_active': m.is_active,
                'version': m.version,
                'created_at': m.created_at.isoformat() if m.created_at else None,
                'updated_at': m.updated_at.isoformat() if m.updated_at else None
            }
            for m in modules
        ]

    @staticmethod
    def get_available_tonalities(db: Session) -> list:
        """
        Get available tonality options for user selection.

        Args:
            db: Database session

        Returns:
            List of tonality option dicts
        """
        from models import PromptModule, PromptType

        tonalities = db.query(PromptModule).filter(
            PromptModule.prompt_type == PromptType.TONALITY,
            PromptModule.is_active == True
        ).order_by(PromptModule.sort_order, PromptModule.name).all()

        return [
            {
                'id': t.id,
                'name': t.name,
                'description': t.description,
                'prompt_group': t.prompt_group,
                'is_default': t.is_default
            }
            for t in tonalities
        ]

    @staticmethod
    def get_user_tonality_preferences(db: Session, user_id: int) -> Dict:
        """
        Get user's tonality preferences for chat and content agents.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            Dict with tonality preferences
        """
        from models import User, PromptModule

        user = db.query(User).filter(User.id == user_id).first()

        result = {
            'chat_tonality_id': None,
            'chat_tonality_name': None,
            'content_tonality_id': None,
            'content_tonality_name': None
        }

        if user:
            if user.chat_tonality_id:
                result['chat_tonality_id'] = user.chat_tonality_id
                tonality = db.query(PromptModule).filter(PromptModule.id == user.chat_tonality_id).first()
                if tonality:
                    result['chat_tonality_name'] = tonality.name

            if user.content_tonality_id:
                result['content_tonality_id'] = user.content_tonality_id
                tonality = db.query(PromptModule).filter(PromptModule.id == user.content_tonality_id).first()
                if tonality:
                    result['content_tonality_name'] = tonality.name

        return result

    @staticmethod
    def set_user_tonality(
        db: Session,
        user_id: int,
        chat_tonality_id: Optional[int] = None,
        content_tonality_id: Optional[int] = None
    ) -> None:
        """
        Set user's tonality preferences.

        Args:
            db: Database session
            user_id: User ID
            chat_tonality_id: ID of chat tonality module (or None to clear)
            content_tonality_id: ID of content tonality module (or None to clear)

        Raises:
            ValueError: If tonality IDs are invalid
        """
        from models import User, PromptModule, PromptType

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Validate chat tonality if provided
        if chat_tonality_id is not None:
            tonality = db.query(PromptModule).filter(
                PromptModule.id == chat_tonality_id,
                PromptModule.prompt_type == PromptType.TONALITY,
                PromptModule.is_active == True
            ).first()
            if not tonality:
                raise ValueError(f"Invalid chat tonality ID: {chat_tonality_id}")

        # Validate content tonality if provided
        if content_tonality_id is not None:
            tonality = db.query(PromptModule).filter(
                PromptModule.id == content_tonality_id,
                PromptModule.prompt_type == PromptType.TONALITY,
                PromptModule.is_active == True
            ).first()
            if not tonality:
                raise ValueError(f"Invalid content tonality ID: {content_tonality_id}")

        user.chat_tonality_id = chat_tonality_id
        user.content_tonality_id = content_tonality_id
        db.commit()


class PromptValidator:
    """Validate prompt templates before saving."""

    @staticmethod
    def validate_template(
        template_type: str,
        template_text: str,
        prompt_group: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Validate prompt template.

        Args:
            template_type: Prompt type (tonality, content_topic, etc.)
            template_text: Template text to validate
            prompt_group: Optional prompt group/topic

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check template_text is not None
        if template_text is None:
            return False, "Template text is required"
            
        # Check length
        if len(template_text) < 50:
            return False, "Template too short (minimum 50 characters)"

        if len(template_text) > 8000:
            return False, "Template too long (maximum 8000 characters)"

        # Valid prompt types
        valid_types = ["tonality", "content_topic", "general", "chat_specific", "chat_constraint", "article_constraint"]
        if template_type not in valid_types:
            return False, f"Invalid template_type. Must be one of: {valid_types}"

        # content_topic requires a prompt_group (topic name)
        if template_type == "content_topic" and not prompt_group:
            return False, "prompt_group is required for content_topic templates"

        return True, None
