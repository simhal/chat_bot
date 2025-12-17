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
            print("✓ Created 'global:admin' group")
        else:
            print("→ 'global:admin' group already exists")

        # Create topic groups for content management (new groupname:role format)
        # Include admin, analyst, editor, reader roles for each topic
        topic_groups = [
            # Equity groups
            ("equity:admin", "equity", "admin", "Admin for Equity content"),
            ("equity:analyst", "equity", "analyst", "Equity analysts - can edit equity research content"),
            ("equity:editor", "equity", "editor", "Editor for Equity content"),
            ("equity:reader", "equity", "reader", "Reader for Equity content"),
            # Fixed Income groups
            ("fixed_income:admin", "fixed_income", "admin", "Admin for Fixed Income content"),
            ("fixed_income:analyst", "fixed_income", "analyst", "Fixed Income analysts - can edit fixed income research content"),
            ("fixed_income:editor", "fixed_income", "editor", "Editor for Fixed Income content"),
            ("fixed_income:reader", "fixed_income", "reader", "Reader for Fixed Income content"),
            # Macro groups
            ("macro:admin", "macro", "admin", "Admin for Macroeconomic content"),
            ("macro:analyst", "macro", "analyst", "Macro analysts - can edit macroeconomic research content"),
            ("macro:editor", "macro", "editor", "Editor for Macroeconomic content"),
            ("macro:reader", "macro", "reader", "Reader for Macroeconomic content"),
            # ESG groups
            ("esg:admin", "esg", "admin", "Admin for ESG content"),
            ("esg:analyst", "esg", "analyst", "ESG analysts - can edit ESG research content"),
            ("esg:editor", "esg", "editor", "Editor for ESG content"),
            ("esg:reader", "esg", "reader", "Reader for ESG content"),
        ]

        for group_name, groupname, role, description in topic_groups:
            group = db.query(Group).filter(Group.name == group_name).first()
            if not group:
                group = Group(
                    name=group_name,
                    groupname=groupname,
                    role=role,
                    description=description
                )
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
