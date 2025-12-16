FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-cache

# Copy application code
COPY main.py database.py models.py auth.py redis_client.py ./
COPY conversation_memory.py chatbot_agent.py seed_db.py dependencies.py ./
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
