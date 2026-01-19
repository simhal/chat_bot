FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for weasyprint
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock* ./

# Install dependencies (--no-frozen allows updating lock file if needed)
RUN uv sync --no-cache

# Copy application code
COPY main.py database.py models.py auth.py redis_client.py ./
COPY conversation_memory.py seed_db.py dependencies.py observability.py config.py ./
COPY .env ./

# Copy multi-agent system directories
COPY services ./services
COPY api ./api
COPY agents ./agents

# Copy Alembic files for database migrations
COPY alembic.ini ./
COPY alembic ./alembic

# Copy scripts
COPY entrypoint.sh init-db.sh ./
RUN chmod +x entrypoint.sh init-db.sh

# Expose port
EXPOSE 8000

# Run the application with entrypoint that handles migrations
CMD ["./entrypoint.sh"]
