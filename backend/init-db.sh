#!/bin/sh
# Manual database initialization script
# Run this once when setting up the database for the first time:
# docker-compose exec backend sh init-db.sh

set -e

echo "Initializing database with Alembic migrations..."
uv run alembic upgrade head

echo "Database initialization complete!"
echo "Tables created:"
echo "  - groups (with default 'user' group)"
echo "  - users"
echo "  - user_groups"
