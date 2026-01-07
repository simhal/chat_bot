# AI Chatbot Application - Claude Code Configuration

## Project Overview

This is a full-stack AI chatbot application with LinkedIn OAuth authentication, content management, and vector search capabilities.

**Tech Stack:**
- Backend: FastAPI (Python 3.12+), LangChain, LangGraph, OpenAI
- Frontend: SvelteKit 2.x with TypeScript, Svelte 5
- Databases: PostgreSQL, Redis, ChromaDB (vector DB)
- Infrastructure: Docker Compose
- Package Managers: uv (Python), npm (Node.js)

## Architecture

### Backend (`/backend`)
- **Framework**: FastAPI with async/await patterns
- **Authentication**: LinkedIn OAuth 2.0 with ID token validation using JWKS
- **AI Integration**: OpenAI ChatGPT (supports gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo)
- **Agent System**: LangChain + LangGraph for AI agent orchestration
- **Vector Storage**: ChromaDB for semantic search and content retrieval
- **Caching**: Redis for session and API response caching
- **Database**: PostgreSQL with SQLAlchemy ORM and Alembic migrations
- **Package Manager**: uv for fast dependency management

**Key Files:**
- `main.py` - FastAPI application entry point
- `models.py` - SQLAlchemy database models
- `auth.py` - OAuth authentication logic
- `database.py` - Database connection and session management
- `redis_client.py` - Redis connection utilities
- `celery_app.py` - Celery worker configuration
- `services/` - Business logic services (content, vector search, agent orchestration)
- `agents/` - Multi-agent AI system (MainChatAgent, AnalystAgent, EditorSubAgent, etc.)
- `api/` - API route handlers
- `tasks/` - Celery background tasks for heavy agent workflows
- `alembic/` - Database migration scripts

### Frontend (`/frontend`)
- **Framework**: SvelteKit 2.x with TypeScript
- **UI Library**: Svelte 5 (uses new runes syntax)
- **Rendering**: Markdown support via marked.js with DOMPurify sanitization
- **Auth Flow**: LinkedIn OAuth redirect flow
- **State Management**: Svelte stores for authentication state
- **API Client**: Fetch API for backend communication

**Key Files:**
- `src/routes/+page.svelte` - Main chat interface
- `src/routes/admin/content/+page.svelte` - Admin content management
- `src/routes/auth/callback/` - OAuth callback handler
- `src/lib/stores/auth.ts` - Authentication state management
- `src/lib/api.ts` - Backend API client

## Development Guidelines

### Python Backend

1. **Package Management**: Use `uv` for all dependency operations
   ```bash
   uv sync              # Install dependencies
   uv add <package>     # Add new package
   uv run <command>     # Run commands in venv
   ```

2. **Code Style**:
   - Async/await for I/O operations
   - Type hints for function signatures
   - Pydantic models for request/response validation
   - Follow FastAPI best practices

3. **Database Changes**:
   - Always create Alembic migrations for schema changes
   - Use SQLAlchemy ORM models, not raw SQL
   - Test migrations up and down

4. **Testing**:
   - Run backend: `cd backend && uv run uvicorn main:app --reload`  or even better run command in the respective docker container
   - API docs: http://localhost:8000/docs

### Frontend (SvelteKit)

1. **Package Management**: Use npm
   ```bash
   npm install          # Install dependencies
   npm run dev          # Development server
   npm run build        # Production build
   ```

2. **Code Style**:
   - Use Svelte 5 runes syntax ($state, $derived, $effect)
   - TypeScript for type safety
   - Component-based architecture
   - Use marked + DOMPurify for rendering markdown

3. **Testing**:
   - Run frontend: `cd frontend && npm run dev`
   - Access at: http://localhost:5173 (dev) or http://localhost:3000 (Docker)

### Docker Development

1. **Starting Services**:
   ```bash
   # Start all services
   docker-compose up --build

   # Start specific service
   docker-compose up -d postgres redis chroma

   # View logs
   docker-compose logs -f backend
   ```

2. **Database Management**:
   ```bash
   # Access PostgreSQL
   docker-compose exec postgres psql -U chatbot_user -d chatbot

   # Run migrations
   docker-compose exec backend alembic upgrade head
   ```

## Environment Configuration

### Backend `.env`
Required variables:
- `LINKEDIN_CLIENT_ID` - LinkedIn OAuth app client ID
- `OPENAI_API_KEY` - OpenAI API key for ChatGPT
- `OPENAI_MODEL` - Model name (gpt-4o-mini, gpt-4o, etc.)
- `CORS_ORIGINS` - Allowed frontend origins
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `CHROMA_HOST` - ChromaDB host

### Frontend `.env`
Required variables:
- `PUBLIC_LINKEDIN_CLIENT_ID` - LinkedIn OAuth client ID
- `PUBLIC_LINKEDIN_REDIRECT_URI` - OAuth callback URL
- `PUBLIC_API_URL` - Backend API base URL

## Common Tasks

### Adding a New API Endpoint
1. Define Pydantic request/response models in `backend/models.py`
2. Create route handler in `backend/api/<module>.py`
3. Register router in `backend/main.py`
4. Add API client method in `frontend/src/lib/api.ts`
5. Update frontend components to use new endpoint

### Adding a New Database Model
1. Define SQLAlchemy model in `backend/models.py`
2. Create Alembic migration: `cd backend && uv run alembic revision --autogenerate -m "description"`
3. Review and edit migration in `backend/alembic/versions/`
4. Apply migration: `uv run alembic upgrade head`

### Adding AI Agent Capabilities
1. Define agent logic in `backend/agents/` (extend existing agent classes)
2. Use LangGraph for complex multi-step agent workflows
3. Integrate with ChromaDB for retrieval-augmented generation (RAG)
4. Update agent invocation in `services/agent_service.py`

### Working with Vector Search
1. Content is stored in ChromaDB via `backend/services/vector_service.py`
2. Use semantic search for content retrieval in chat context
3. Embeddings are generated using OpenAI's embedding models

## Important Notes

1. **Authentication**: All API endpoints (except health checks) require LinkedIn OAuth token in Authorization header

2. **CORS**: Backend CORS is configured for local development. Update `CORS_ORIGINS` for production

3. **Model Selection**: gpt-4o-mini is recommended for development (faster, cheaper). Use gpt-4o for production quality

4. **Vector Database**: ChromaDB data persists in Docker volume `chroma_data`

5. **Database Migrations**: Always review autogenerated migrations before applying

6. **Content Management**: Admin interface at `/admin/content` for managing chatbot knowledge base

7. **Windows Environment**: Project is being developed on Windows (MINGW64). Use forward slashes in paths where possible for cross-platform compatibility

## Project Structure
```
chatbot-app/
├── backend/                 # Python FastAPI backend
│   ├── agents/             # Multi-agent AI system
│   │   ├── main_chat_agent.py    # Orchestrator agent
│   │   ├── analyst_agent.py      # Research workflows
│   │   ├── editor_sub_agent.py   # Publishing with HITL
│   │   └── tools/                # Agent tools registry
│   ├── alembic/            # Database migrations
│   ├── api/                # API route handlers
│   ├── services/           # Business logic services
│   ├── tasks/              # Celery background tasks
│   ├── main.py             # FastAPI app entry point
│   ├── celery_app.py       # Celery worker configuration
│   ├── models.py           # SQLAlchemy & Pydantic models
│   ├── auth.py             # OAuth authentication
│   ├── database.py         # Database setup
│   ├── redis_client.py     # Redis client
│   ├── pyproject.toml      # Python dependencies (uv)
│   └── Dockerfile
├── frontend/               # SvelteKit frontend
│   ├── src/
│   │   ├── lib/           # Shared utilities
│   │   │   ├── stores/    # Svelte stores
│   │   │   └── api.ts     # API client
│   │   └── routes/        # SvelteKit routes
│   │       ├── +page.svelte              # Chat interface
│   │       ├── analyst/                  # Analyst workflow pages
│   │       ├── editor/                   # Editor workflow pages
│   │       ├── admin/                    # Admin panels
│   │       └── auth/callback/            # OAuth callback
│   ├── package.json
│   └── Dockerfile
├── docs/                   # Architecture documentation
├── docker-compose.yml      # Multi-container setup
├── README.md              # Project documentation
└── CLAUDE.md              # This file
```

## Troubleshooting

### Backend Issues
- Check logs: `docker-compose logs backend`
- Verify environment variables in `backend/.env`
- Ensure database migrations are applied: `alembic upgrade head`
- Test ChromaDB connection: should start on port 8001

### Frontend Issues
- Check logs: `docker-compose logs frontend`
- Verify environment variables in `frontend/.env`
- Clear browser localStorage for auth issues
- Check CORS configuration if API calls fail

### Database Issues
- Check PostgreSQL logs: `docker-compose logs postgres`
- Verify connection: `docker-compose exec postgres psql -U chatbot_user -d chatbot`
- Reset database: `docker-compose down -v` (WARNING: destroys all data)

### OAuth Issues
- Verify redirect URI matches LinkedIn app settings exactly
- Check that client ID is correct in both backend and frontend
- Review network tab in browser for OAuth flow errors

### Celery Worker Issues
- Check worker logs: `docker-compose logs celery-worker`
- Verify Redis is running and accessible
- Check task status via `/api/tasks/{task_id}` endpoint
- Restart workers: `docker-compose restart celery-worker`
