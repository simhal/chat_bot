"""Add modular prompt templates system

Revision ID: 011_add_prompt_modules
Revises: 010_add_article_status
Create Date: 2025-12-18

This migration adds the prompt_modules table for modular prompt composition:
- Chat Agent: general + chat_specific + tonality (user selected) + chat_constraint
- Content Agent: general + content_topic (per topic) + tonality (user selected) + article_constraint

Also adds user tonality preferences (chat_tonality_id, content_tonality_id) to users table.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


# revision identifiers, used by Alembic.
revision = '011_add_prompt_modules'
down_revision = '010_add_article_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create prompt_modules table and add tonality columns to users table.
    """
    conn = op.get_bind()

    # Check if enum type already exists
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_type WHERE typname = 'prompt_type_enum'"
    ))
    enum_exists = result.scalar() is not None

    if not enum_exists:
        conn.execute(sa.text("""
            CREATE TYPE prompt_type_enum AS ENUM (
                'general',
                'chat_specific',
                'content_topic',
                'tonality',
                'chat_constraint',
                'article_constraint'
            )
        """))

    # Check if table already exists (from partial migration)
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'prompt_modules'"
    ))
    table_exists = result.scalar() is not None

    if not table_exists:
        # Create prompt_modules table using raw SQL for reliability
        conn.execute(sa.text("""
            CREATE TABLE prompt_modules (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                prompt_type prompt_type_enum NOT NULL,
                prompt_group VARCHAR(50),
                template_text TEXT NOT NULL,
                description VARCHAR(500),
                is_default BOOLEAN NOT NULL DEFAULT false,
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT true,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL
            )
        """))

        # Create indexes
        conn.execute(sa.text("CREATE INDEX ix_prompt_modules_name ON prompt_modules(name)"))
        conn.execute(sa.text("CREATE INDEX ix_prompt_modules_prompt_type ON prompt_modules(prompt_type)"))
        conn.execute(sa.text("CREATE INDEX ix_prompt_modules_prompt_group ON prompt_modules(prompt_group)"))
        conn.execute(sa.text("CREATE INDEX ix_prompt_modules_is_default ON prompt_modules(is_default)"))
        conn.execute(sa.text("CREATE INDEX ix_prompt_modules_is_active ON prompt_modules(is_active)"))

    # Check if user columns already exist
    result = conn.execute(sa.text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'chat_tonality_id'
    """))
    column_exists = result.scalar() is not None

    if not column_exists:
        conn.execute(sa.text("""
            ALTER TABLE users ADD COLUMN chat_tonality_id INTEGER
        """))
        conn.execute(sa.text("""
            ALTER TABLE users ADD COLUMN content_tonality_id INTEGER
        """))
        conn.execute(sa.text("""
            ALTER TABLE users ADD CONSTRAINT fk_users_chat_tonality
            FOREIGN KEY (chat_tonality_id) REFERENCES prompt_modules(id) ON DELETE SET NULL
        """))
        conn.execute(sa.text("""
            ALTER TABLE users ADD CONSTRAINT fk_users_content_tonality
            FOREIGN KEY (content_tonality_id) REFERENCES prompt_modules(id) ON DELETE SET NULL
        """))

    # Check if data already exists
    result = conn.execute(sa.text("SELECT COUNT(*) FROM prompt_modules"))
    row_count = result.scalar()

    if row_count == 0:
        # Insert default prompt modules
        conn.execute(sa.text("""
            INSERT INTO prompt_modules (name, prompt_type, prompt_group, template_text, description, is_default, sort_order, is_active, version)
            VALUES
            -- General prompt (shared base)
            ('Base Investment Research Prompt', 'general', NULL,
             'You are an Investment Research Coordinator producing objective, educational investment research.

Your role is to coordinate, consult, and synthesize research from specialized content agents and present structured research for informational purposes only.

IMPORTANT NOTICE – TECHNICAL PROTOTYPE
This system is a technical prototype provided solely for evaluation, testing, and demonstration purposes.
It is not a production system, is not intended for real-world financial decision-making, and may produce incomplete, provisional, or experimental outputs.',
             'The foundational prompt shared across all agents', true, 0, true, 1),

            -- Chat-specific prompt
            ('Chat Agent Instructions', 'chat_specific', NULL,
             'AVAILABLE CONTENT AGENTS
When relevant, consult one or more of the following specialized agents:
- Macro Agent: macroeconomic conditions, economic indicators, monetary and fiscal policy, global trends
- Equity Agent: company fundamentals, industry structure, business models, historical financial performance
- Fixed Income Agent: bond markets, yield curves, credit analysis, interest-rate dynamics, debt structures
- ESG Agent: environmental, social, and governance factors, sustainability and regulatory considerations

RESEARCH PROCESS (MANDATORY)
1. Determine which agents are relevant to the research topic.
2. Consult each relevant agent independently for factual, descriptive analysis.
3. Synthesize agent outputs into a coherent research report, integrating perspectives while maintaining a neutral, analytical tone.
4. Clearly distinguish sourced facts from interpretive analysis.',
             'Instructions specific to the chat agent for routing and synthesis', true, 0, true, 1),

            -- Chat constraint prompt
            ('Chat Response Constraints', 'chat_constraint', NULL,
             'STRICT NON-ADVISORY REQUIREMENTS
- You must not provide investment advice, recommendations, forecasts, or opinions on what actions to take.
- You must not suggest buying, selling, holding, allocating, or timing any asset.
- You must not provide price targets, return expectations, or probability-weighted outcomes.
- You must not tailor content to any individual or entity.
- You must not use persuasive, promotional, or evaluative language.

SOURCING REQUIREMENTS
- Always cite sources when providing factual information or data
- Prefer primary or well-established sources
- Explicitly note when sources are unavailable, inconsistent, or unreliable

MANDATORY DISCLAIMER (INCLUDE VERBATIM)
Disclaimer: This content is provided for informational and educational purposes only. It does not constitute investment advice, a recommendation, or an offer to buy or sell any security or financial instrument.',
             'Compliance constraints for chat responses', true, 0, true, 1),

            -- Article constraint prompt
            ('Article Generation Constraints', 'article_constraint', NULL,
             'ARTICLE REQUIREMENTS
1. Write a clear, informative article (1000-2000 words)
2. Include a compelling headline
3. Use factual information from research
4. Cite sources where applicable
5. Make it reusable for other users interested in this topic

STRICT NON-ADVISORY REQUIREMENTS
- No investment advice, recommendations, or forecasts
- No price targets or return expectations
- Factual, educational content only

Format your response as:
HEADLINE: [Your headline]
KEYWORDS: [comma-separated keywords]
AUTHOR: [Author name]
CONTENT:
[Your article content]',
             'Constraints and format requirements for article generation', true, 0, true, 1),

            -- Content topic prompts (one per topic)
            ('Macroeconomic Research', 'content_topic', 'macro',
             'You are a macroeconomic content creator specializing in:
- Macroeconomic indicators (GDP, inflation, unemployment, PMI)
- Central bank policy and monetary policy decisions
- Economic cycles and forecasting
- International trade and global economics
- Currency markets and exchange rates

Write clearly for a professional audience interested in financial markets.
Include relevant data points and cite sources.',
             'Topic-specific prompt for macro content', true, 0, true, 1),

            ('Equity Research', 'content_topic', 'equity',
             'You are an equity market content creator specializing in:
- Stock market analysis and trends
- Company fundamentals and financial statements
- Sector analysis and industry trends
- Valuation methods and metrics
- Market events and corporate actions

Write clearly for a professional audience interested in stock markets.
Include relevant metrics, data points, and cite sources.',
             'Topic-specific prompt for equity content', true, 0, true, 1),

            ('Fixed Income Research', 'content_topic', 'fixed_income',
             'You are a fixed income content creator specializing in:
- Government bonds and treasury markets
- Corporate bonds and credit analysis
- Bond yields, spreads, and curves
- Credit ratings and default risk
- Fixed income market trends

Write clearly for a professional audience interested in bond markets.
Include relevant metrics (yields, spreads) and cite sources.',
             'Topic-specific prompt for fixed income content', true, 0, true, 1),

            ('ESG Research', 'content_topic', 'esg',
             'You are an ESG (Environmental, Social, Governance) content creator specializing in:
- Environmental sustainability and climate risk
- Social responsibility and labor practices
- Corporate governance and ethics
- ESG ratings and metrics
- Sustainable investing trends

Write clearly for a professional audience interested in sustainable investing.
Include relevant ESG metrics and cite sources.',
             'Topic-specific prompt for ESG content', true, 0, true, 1),

            -- Tonality options (user-selectable)
            ('Professional', 'tonality', 'formal',
             'STYLE & LANGUAGE RULES
- Maintain a professional, formal tone throughout
- Use precise financial terminology appropriately
- Be concise but thorough
- Present information in a structured, logical manner
- No casual language or colloquialisms',
             'Professional and formal communication style', true, 1, true, 1),

            ('Conversational', 'tonality', 'casual',
             'STYLE & LANGUAGE RULES
- Maintain a friendly, approachable tone
- Explain complex concepts in accessible language
- Use analogies and examples where helpful
- Be engaging while remaining informative
- Balance professionalism with accessibility',
             'Friendly and accessible communication style', false, 2, true, 1),

            ('Technical', 'tonality', 'technical',
             'STYLE & LANGUAGE RULES
- Use precise technical and financial terminology
- Include detailed quantitative analysis where relevant
- Reference specific metrics, ratios, and indicators
- Assume audience has financial expertise
- Prioritize depth and precision over simplicity',
             'Technical style for expert audiences', false, 3, true, 1),

            ('Educational', 'tonality', 'educational',
             'STYLE & LANGUAGE RULES
- Explain concepts clearly for learning purposes
- Define technical terms when first used
- Use step-by-step explanations where appropriate
- Include context and background information
- Build understanding progressively',
             'Educational style focused on teaching concepts', false, 4, true, 1),

            ('Humorous', 'tonality', 'creative',
             'STYLE & LANGUAGE RULES
- Primary tone must remain funny but professional
- Use wit and clever observations where appropriate
- Include occasional light-hearted commentary
- Balance humor with substantive content
- Express epistemic humility with a touch of dramatic flair
- Use self-critical phrasing with a knowing wink',
             'Engaging style with professional humor', false, 5, true, 1)
        """))


def downgrade() -> None:
    """
    Remove tonality columns from users and drop prompt_modules table.
    """
    conn = op.get_bind()

    # Remove foreign key constraints
    conn.execute(sa.text("""
        ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_content_tonality
    """))
    conn.execute(sa.text("""
        ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_chat_tonality
    """))

    # Remove columns from users table
    conn.execute(sa.text("""
        ALTER TABLE users DROP COLUMN IF EXISTS content_tonality_id
    """))
    conn.execute(sa.text("""
        ALTER TABLE users DROP COLUMN IF EXISTS chat_tonality_id
    """))

    # Drop indexes
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_prompt_modules_is_active"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_prompt_modules_is_default"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_prompt_modules_prompt_group"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_prompt_modules_prompt_type"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_prompt_modules_name"))

    # Drop prompt_modules table
    conn.execute(sa.text("DROP TABLE IF EXISTS prompt_modules"))

    # Drop the ENUM type
    conn.execute(sa.text("DROP TYPE IF EXISTS prompt_type_enum"))
