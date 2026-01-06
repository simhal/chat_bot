"""
Seed test data for E2E testing.

This script creates a complete test dataset including:
- Test users with various roles
- Topics with groups
- Articles in various states
- Prompt modules and tonality options

Run standalone: python -m tests.fixtures.seed_test_data
"""
import os
import sys

# Add backend to path if running standalone
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import (
    Base, User, Group, Topic, ContentArticle, PromptModule,
    ArticleStatus, PromptType,
)


def seed_test_data(database_url: str = None):
    """
    Seed the database with test data for E2E testing.

    Args:
        database_url: Database connection string. If None, uses DATABASE_URL env var.
    """
    if database_url is None:
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql://chatbot_test_user:chatbot_test_password@localhost:5433/chatbot_test"
        )

    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionLocal() as db:
        print("Seeding test data...")

        # Check if test users already exist (full seeding already done)
        existing_user = db.query(User).filter(User.email == "reader@test.com").first()
        if existing_user:
            print("Test data already exists, skipping seed.")
            return

        # =================================================================
        # GET OR CREATE TOPICS
        # =================================================================
        print("Creating/updating topics...")

        topic_data = {
            "macro": {
                "title": "Macroeconomic Research",
                "description": "Analysis of macroeconomic trends, GDP, inflation, and monetary policy",
                "sort_order": 1,
            },
            "equity": {
                "title": "Equity Research",
                "description": "Stock analysis, valuations, sector trends, and earnings",
                "sort_order": 2,
            },
            "fixed_income": {
                "title": "Fixed Income Research",
                "description": "Bond analysis, yields, credit spreads, and duration strategies",
                "sort_order": 3,
            },
        }

        topics = {}
        for slug, data in topic_data.items():
            topic = db.query(Topic).filter(Topic.slug == slug).first()
            if not topic:
                topic = Topic(
                    slug=slug,
                    title=data["title"],
                    description=data["description"],
                    visible=True,
                    searchable=True,
                    active=True,
                    sort_order=data["sort_order"],
                    article_order="date",
                )
                db.add(topic)
            topics[slug] = topic
        db.flush()

        # =================================================================
        # GET OR CREATE GROUPS
        # =================================================================
        print("Creating/updating groups...")

        groups = {}

        # Global admin group
        group = db.query(Group).filter(Group.name == "global:admin").first()
        if not group:
            group = Group(
                name="global:admin",
                groupname="global",
                role="admin",
                description="Global administrators with full system access",
            )
            db.add(group)
        groups["global:admin"] = group

        # Topic-specific groups
        for slug, topic in topics.items():
            for role in ["admin", "analyst", "editor", "reader"]:
                group_name = f"{slug}:{role}"
                group = db.query(Group).filter(Group.name == group_name).first()
                if not group:
                    group = Group(
                        name=group_name,
                        groupname=slug,
                        role=role,
                        description=f"{role.title()} access for {topic.title}",
                        topic_id=topic.id,
                    )
                    db.add(group)
                else:
                    # Update topic_id if missing (migration may have created without it)
                    if group.topic_id is None:
                        group.topic_id = topic.id
                groups[group_name] = group

        db.flush()

        # =================================================================
        # CREATE TEST USERS
        # =================================================================
        print("Creating test users...")

        users = {
            "reader": User(
                email="reader@test.com",
                name="Test",
                surname="Reader",
                linkedin_sub="test_reader_linkedin_sub",
                active=True,
            ),
            "analyst": User(
                email="analyst@test.com",
                name="Test",
                surname="Analyst",
                linkedin_sub="test_analyst_linkedin_sub",
                active=True,
            ),
            "editor": User(
                email="editor@test.com",
                name="Test",
                surname="Editor",
                linkedin_sub="test_editor_linkedin_sub",
                active=True,
            ),
            "topic_admin": User(
                email="topicadmin@test.com",
                name="Test",
                surname="TopicAdmin",
                linkedin_sub="test_topic_admin_linkedin_sub",
                active=True,
            ),
            "global_admin": User(
                email="admin@test.com",
                name="Test",
                surname="Admin",
                linkedin_sub="test_global_admin_linkedin_sub",
                active=True,
            ),
        }

        for user in users.values():
            db.add(user)
        db.flush()

        # Assign groups to users
        # Reader gets reader access to all topics
        for slug in topics.keys():
            users["reader"].groups.append(groups[f"{slug}:reader"])

        # Analyst gets analyst access to macro
        users["analyst"].groups.append(groups["macro:analyst"])
        users["analyst"].groups.append(groups["equity:reader"])

        # Editor gets editor access to macro
        users["editor"].groups.append(groups["macro:editor"])
        users["editor"].groups.append(groups["equity:reader"])

        # Topic admin gets admin access to macro
        users["topic_admin"].groups.append(groups["macro:admin"])

        # Global admin gets global admin
        users["global_admin"].groups.append(groups["global:admin"])

        db.flush()

        # =================================================================
        # CREATE PROMPT MODULES
        # =================================================================
        print("Creating prompt modules...")

        prompts = [
            PromptModule(
                name="Base System Prompt",
                prompt_type=PromptType.GENERAL,
                template_text="""You are a professional investment research assistant.
You provide accurate, data-driven analysis and insights.
Always cite sources when making claims about market data.""",
                description="Base system prompt used by all agents",
                is_active=True,
                version=1,
            ),
            PromptModule(
                name="Chat Specific Prompt",
                prompt_type=PromptType.CHAT_SPECIFIC,
                template_text="""When chatting with users:
- Be conversational but professional
- Ask clarifying questions when needed
- Provide actionable insights""",
                description="Additional context for chat interactions",
                is_active=True,
                version=1,
            ),
            PromptModule(
                name="Professional Tone",
                prompt_type=PromptType.TONALITY,
                template_text="Respond in a professional, business-like manner suitable for institutional investors.",
                description="Professional writing style",
                is_default=True,
                sort_order=1,
                is_active=True,
            ),
            PromptModule(
                name="Technical Tone",
                prompt_type=PromptType.TONALITY,
                template_text="Respond with technical precision and quantitative detail.",
                description="Technical writing style",
                sort_order=2,
                is_active=True,
            ),
            PromptModule(
                name="Macro Content Agent",
                prompt_type=PromptType.CONTENT_TOPIC,
                prompt_group="macro",
                template_text="""Focus on macroeconomic analysis including:
- GDP growth and economic indicators
- Inflation and monetary policy
- Central bank decisions
- Fiscal policy impacts""",
                description="Content agent prompt for macro topic",
                is_active=True,
            ),
            PromptModule(
                name="Equity Content Agent",
                prompt_type=PromptType.CONTENT_TOPIC,
                prompt_group="equity",
                template_text="""Focus on equity analysis including:
- Stock valuations and fundamentals
- Sector trends and rotation
- Earnings analysis
- Technical indicators""",
                description="Content agent prompt for equity topic",
                is_active=True,
            ),
        ]

        for prompt in prompts:
            db.add(prompt)
        db.flush()

        # =================================================================
        # CREATE TEST ARTICLES
        # =================================================================
        print("Creating test articles...")

        articles = [
            # Published articles
            ContentArticle(
                topic_id=topics["macro"].id,
                topic="macro",
                headline="Q4 2024 Economic Outlook: Growth Resilience Amid Policy Uncertainty",
                author="Test Analyst",
                editor="Test Editor",
                status=ArticleStatus.PUBLISHED,
                keywords="gdp, growth, outlook, economy, 2024",
                readership_count=150,
                rating=4,
                rating_count=25,
                created_by_agent="test_seed",
                is_active=True,
            ),
            ContentArticle(
                topic_id=topics["macro"].id,
                topic="macro",
                headline="Federal Reserve Rate Decision Analysis: December 2024",
                author="Test Analyst",
                editor="Test Editor",
                status=ArticleStatus.PUBLISHED,
                keywords="fed, rates, monetary policy, inflation",
                readership_count=200,
                rating=5,
                rating_count=40,
                created_by_agent="test_seed",
                is_active=True,
            ),
            ContentArticle(
                topic_id=topics["equity"].id,
                topic="equity",
                headline="Tech Sector Analysis: AI Investment Opportunities",
                author="Test Analyst",
                editor="Test Editor",
                status=ArticleStatus.PUBLISHED,
                keywords="tech, ai, stocks, investment",
                readership_count=300,
                rating=4,
                rating_count=50,
                created_by_agent="test_seed",
                is_active=True,
            ),
            # Draft articles
            ContentArticle(
                topic_id=topics["macro"].id,
                topic="macro",
                headline="Draft: Labor Market Analysis January 2025",
                author="Test Analyst",
                status=ArticleStatus.DRAFT,
                keywords="labor, employment, jobs",
                created_by_agent="test_seed",
                is_active=True,
            ),
            # Editor review articles
            ContentArticle(
                topic_id=topics["macro"].id,
                topic="macro",
                headline="Pending Review: Inflation Trends Analysis",
                author="Test Analyst",
                status=ArticleStatus.EDITOR,
                keywords="inflation, cpi, prices",
                created_by_agent="test_seed",
                is_active=True,
            ),
        ]

        for article in articles:
            db.add(article)

        db.commit()
        print("Test data seeding complete!")

        # Print summary
        print("\n=== Test Data Summary ===")
        print(f"Topics: {db.query(Topic).count()}")
        print(f"Groups: {db.query(Group).count()}")
        print(f"Users: {db.query(User).count()}")
        print(f"Articles: {db.query(ContentArticle).count()}")
        print(f"Prompts: {db.query(PromptModule).count()}")

        print("\n=== Test User Credentials ===")
        print("All test users use LinkedIn OAuth - use mock auth in tests")
        print("- reader@test.com (reader access)")
        print("- analyst@test.com (macro:analyst)")
        print("- editor@test.com (macro:editor)")
        print("- topicadmin@test.com (macro:admin)")
        print("- admin@test.com (global:admin)")


if __name__ == "__main__":
    seed_test_data()
