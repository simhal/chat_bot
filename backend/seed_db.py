"""
Database seeding script - creates initial admin user, topics, and groups
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import db_settings
from models import Base, User, Group, Topic, ContentArticle
import sys


# Define topics with their metadata
TOPICS = [
    {
        "slug": "macro",
        "title": "Macroeconomic Research",
        "description": "Global economic trends, central bank policies, and macroeconomic analysis",
        "agent_type": "economist",
        "icon": "globe",
        "color": "#4A90D9",
        "sort_order": 1
    },
    {
        "slug": "equity",
        "title": "Equity Research",
        "description": "Stock analysis, company fundamentals, and equity market insights",
        "agent_type": "equity",
        "icon": "trending-up",
        "color": "#48BB78",
        "sort_order": 2
    },
    {
        "slug": "fixed_income",
        "title": "Fixed Income Research",
        "description": "Bond markets, interest rates, and fixed income analysis",
        "agent_type": "fixed_income",
        "icon": "bar-chart",
        "color": "#9F7AEA",
        "sort_order": 3
    },
    {
        "slug": "esg",
        "title": "ESG Research",
        "description": "Environmental, social, and governance factors in investing",
        "agent_type": "esg",
        "icon": "leaf",
        "color": "#38B2AC",
        "sort_order": 4
    },
    {
        "slug": "technical",
        "title": "Technical Documentation",
        "description": "Software architecture, API documentation, and technical guides",
        "agent_type": "technical",
        "icon": "code",
        "color": "#718096",
        "sort_order": 5
    }
]


def seed_database():
    """Create initial admin user, topics, and groups"""
    import sys

    def log(msg):
        print(msg, flush=True)
        sys.stdout.flush()

    log("Connecting to database...")
    engine = create_engine(db_settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    log("Database connection established.")

    try:
        # Create admin group if it doesn't exist (global:admin in new structure)
        admin_group = db.query(Group).filter(Group.name == "global:admin").first()
        if not admin_group:
            admin_group = Group(
                name="global:admin",
                groupname="global",
                role="admin",
                description="System administrators with full access"
            )
            db.add(admin_group)
            log("✓ Created 'global:admin' group")
        else:
            log("→ 'global:admin' group already exists")

        # Create topics and their groups
        for topic_data in TOPICS:
            topic = db.query(Topic).filter(Topic.slug == topic_data["slug"]).first()
            if not topic:
                topic = Topic(
                    slug=topic_data["slug"],
                    title=topic_data["title"],
                    description=topic_data["description"],
                    agent_type=topic_data.get("agent_type"),
                    icon=topic_data.get("icon"),
                    color=topic_data.get("color"),
                    sort_order=topic_data.get("sort_order", 0),
                    visible=True,
                    searchable=True,
                    active=True
                )
                db.add(topic)
                db.flush()  # Get the topic ID
                log(f"✓ Created topic '{topic.slug}'")
            else:
                log(f"→ Topic '{topic.slug}' already exists")

            # Create 4 groups for this topic
            roles = ["admin", "analyst", "editor", "reader"]
            role_descriptions = {
                "admin": f"Admin for {topic_data['title']}",
                "analyst": f"{topic_data['title']} analysts - can create and edit content",
                "editor": f"Editor for {topic_data['title']}",
                "reader": f"Reader for {topic_data['title']}"
            }

            for role in roles:
                group_name = f"{topic_data['slug']}:{role}"
                group = db.query(Group).filter(Group.name == group_name).first()
                if not group:
                    group = Group(
                        name=group_name,
                        groupname=topic_data["slug"],
                        role=role,
                        topic_id=topic.id,
                        description=role_descriptions[role]
                    )
                    db.add(group)
                    log(f"✓ Created '{group_name}' group")
                else:
                    # Link existing group to topic if not already linked
                    if not group.topic_id:
                        group.topic_id = topic.id
                        log(f"→ Linked '{group_name}' group to topic")
                    else:
                        log(f"→ '{group_name}' group already exists")

        # Migrate existing articles to link to topics
        # Find articles with legacy 'topic' field but no topic_id
        articles_to_migrate = db.query(ContentArticle).filter(
            ContentArticle.topic_id.is_(None),
            ContentArticle.topic.isnot(None)
        ).all()

        if articles_to_migrate:
            for article in articles_to_migrate:
                topic = db.query(Topic).filter(Topic.slug == article.topic).first()
                if topic:
                    article.topic_id = topic.id
                    log(f"→ Migrated article {article.id} to topic '{topic.slug}'")
            log(f"✓ Migrated {len(articles_to_migrate)} articles to topics")

        # Create default admin user if it doesn't exist
        admin_email = "simon.haller@gmx.net"
        admin_user = db.query(User).filter(User.email == admin_email).first()

        if not admin_user:
            admin_user = User(
                email=admin_email,
                name="Simon",
                surname="Haller",
                linkedin_sub="admin_default_user",  # Dummy value for default admin
                active=True
            )
            db.add(admin_user)
            db.flush()  # Get the user ID

            # Add user to admin group
            admin_user.groups.append(admin_group)
            log(f"✓ Created admin user: {admin_email}")
        else:
            log(f"→ Admin user already exists: {admin_email}")
            # Ensure user is in admin group
            if admin_group not in admin_user.groups:
                admin_user.groups.append(admin_group)
                log("✓ Added existing user to admin group")

        db.commit()
        log("✓ Database seeding completed successfully")
        return 0

    except Exception as e:
        db.rollback()
        log(f"✗ Error seeding database: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(seed_database())
