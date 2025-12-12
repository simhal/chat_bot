#!/bin/sh
set -e

echo "Running database migrations..."
uv run alembic upgrade head

echo "Seeding database with initial data..."
uv run python seed_db.py

echo "Starting application..."
exec uv run uvicorn main:app --host 0.0.0.0 --port 8000
