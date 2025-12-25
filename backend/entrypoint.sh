#!/bin/sh
set -e

echo "Running database migrations..."
uv run alembic upgrade head

echo "Seeding database with initial data..."
# Run seeding with timeout and don't fail if it errors (data might already exist)
timeout 30 uv run python seed_db.py || echo "Seeding completed or skipped (timeout/error)"

echo "Starting application with 3 workers..."
exec uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 3
