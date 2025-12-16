"""
Database seeding script - creates initial admin user and groups
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import db_settings
from models import Base, User, Group
import sys


def seed_database():
    """Create initial admin user and groups"""
    engine = create_engine(db_settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Create admin group if it doesn't exist
        admin_group = db.query(Group).filter(Group.name == "admin").first()
        if not admin_group:
            admin_group = Group(
                name="admin",
                description="System administrators with full access"
            )
            db.add(admin_group)
            print("✓ Created 'admin' group")
        else:
            print("→ 'admin' group already exists")

        # Create analyst groups for content management
        analyst_groups = [
            ("equity_analyst", "Equity analysts - can edit equity research content"),
            ("fi_analyst", "Fixed Income analysts - can edit fixed income research content"),
            ("macro_analyst", "Macro analysts - can edit macroeconomic research content"),
            ("esg_analyst", "ESG analysts - can edit ESG research content"),
        ]

        for group_name, description in analyst_groups:
            group = db.query(Group).filter(Group.name == group_name).first()
            if not group:
                group = Group(name=group_name, description=description)
                db.add(group)
                print(f"✓ Created '{group_name}' group")
            else:
                print(f"→ '{group_name}' group already exists")

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
            print(f"✓ Created admin user: {admin_email}")
        else:
            print(f"→ Admin user already exists: {admin_email}")
            # Ensure user is in admin group
            if admin_group not in admin_user.groups:
                admin_user.groups.append(admin_group)
                print("✓ Added existing user to admin group")

        db.commit()
        print("✓ Database seeding completed successfully")
        return 0

    except Exception as e:
        db.rollback()
        print(f"✗ Error seeding database: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(seed_database())
