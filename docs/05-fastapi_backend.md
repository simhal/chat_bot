# FastAPI Backend

## Overview

The backend is built with **FastAPI**, a modern Python web framework that provides high performance, automatic API documentation, and native async support. The API uses role-based URL routing where the URL path indicates the required permission level.

---

## API Structure

### Router Organization

The API is organized by role-based access:

| Router | URL Prefix | Required Permission | Purpose |
|--------|------------|---------------------|---------|
| **Auth** | `/api/auth/` | None | OAuth login, token refresh |
| **Reader** | `/api/reader/` | Any authenticated | Read articles, search, rate |
| **Analyst** | `/api/analyst/{topic}/` | `{topic}:analyst+` | Create and edit articles |
| **Editor** | `/api/editor/{topic}/` | `{topic}:editor+` | Review and publish articles |
| **Admin** | `/api/admin/` | `global:admin` | System administration |
| **Resources** | `/api/resources/` | Public (hash_id) | Serve resource content |
| **Chat** | `/api/chat` | Any authenticated | AI chat interaction |
| **Tasks** | `/api/tasks/` | Any authenticated | Background task status |
| **WebSocket** | `/ws/{user_id}` | Authenticated | Real-time notifications |

### URL Pattern: Topic in Path

For topic-scoped operations, the topic is part of the URL path:

```
/api/analyst/{topic}/articles      - List draft articles for topic
/api/analyst/{topic}/article       - Create new article
/api/analyst/{topic}/article/{id}  - Edit specific article
```

This design:
- Makes permissions explicit in the URL
- Enables topic validation at the routing level
- Prevents cross-topic access via URL manipulation

---

## Authentication Flow

### OAuth Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/auth/linkedin` | GET | Get LinkedIn OAuth redirect URL |
| `/api/auth/callback` | POST | Exchange OAuth code for tokens |
| `/api/auth/refresh` | POST | Refresh access token |
| `/api/auth/logout` | POST | Invalidate tokens |

### Token Validation

All authenticated endpoints use JWT Bearer tokens:

```
Request Header: Authorization: Bearer <access_token>
```

Token validation:
1. Decode JWT and verify signature
2. Check expiration timestamp
3. Verify token ID exists in Redis registry
4. Extract user scopes for authorization

---

## Permission Dependencies

### FastAPI Dependencies

The API uses dependency injection for permission checks:

| Dependency | Returns | Purpose |
|------------|---------|---------|
| `get_current_user` | User dict | Validates token, returns user info |
| `require_reader_for_topic` | (User, Topic) | Validates topic access |
| `require_analyst_for_topic` | (User, Topic) | Validates analyst+ role |
| `require_editor_for_topic` | (User, Topic) | Validates editor+ role |
| `require_admin` | User | Validates global admin |

### Permission Check Flow

```
Request arrives
      │
      ▼
┌─────────────────────────────┐
│ Dependency: get_current_user │
│ - Validate JWT token         │
│ - Check Redis registry       │
│ - Return user with scopes    │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│ Dependency: require_analyst │
│ - Extract topic from path   │
│ - Check global:admin bypass │
│ - Check {topic}:analyst+    │
│ - Validate article-topic    │
└─────────────┬───────────────┘
              │
              ▼
       Route Handler
```

---

## Core Endpoints

### Reader Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/reader/article/{id}` | GET | Get article by ID |
| `/api/reader/articles/{topic}` | GET | List published articles |
| `/api/reader/articles/{topic}/top-rated` | GET | Top rated articles |
| `/api/reader/articles/{topic}/most-read` | GET | Most read articles |
| `/api/reader/published/{topic}` | GET | Published articles for topic |
| `/api/reader/search/{topic}` | GET | Search articles |
| `/api/reader/article/{id}/rate` | POST | Rate an article |
| `/api/reader/article/{id}/pdf` | GET | Download article PDF |
| `/api/reader/article/{id}/resources` | GET | Get article resources |

### Analyst Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyst/{topic}/articles` | GET | List draft articles |
| `/api/analyst/{topic}/article` | POST | Create new article |
| `/api/analyst/{topic}/article/{id}` | PUT | Edit article |
| `/api/analyst/{topic}/article/{id}/chat` | POST | Chat about article |
| `/api/analyst/{topic}/article/{id}/submit` | POST | Submit for review |

### Editor Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/editor/{topic}/articles` | GET | List articles for review |
| `/api/editor/{topic}/article/{id}/reject` | POST | Reject article |
| `/api/editor/{topic}/article/{id}/publish` | POST | Publish article |

### Admin Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/articles/{topic}` | GET | All articles (any status) |
| `/api/admin/article/{id}` | DELETE | Deactivate article |
| `/api/admin/article/{id}/reactivate` | POST | Reactivate article |
| `/api/admin/article/{id}/recall` | POST | Recall to draft |
| `/api/admin/article/{id}/purge` | DELETE | Permanent delete |
| `/api/admin/articles/reorder` | POST | Reorder articles |

### Chat Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Send message to AI |

Request body includes:
- `message`: User's text message
- `navigation_context`: Current page/article context
- `conversation_id`: Session identifier

### Task Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tasks/{task_id}` | GET | Get task status |
| `/api/tasks/{task_id}/result` | GET | Get task result |

---

## Request/Response Models

### Pydantic Models

All request and response data uses Pydantic models for:
- Automatic validation
- OpenAPI documentation
- Type safety

Example models:

```python
class ArticleCreate(BaseModel):
    headline: str
    content: str
    keywords: Optional[str]

class ArticleResponse(BaseModel):
    id: int
    headline: str
    topic_slug: str
    status: str
    created_at: datetime
```

### Standard Response Format

Successful responses return the data directly or with metadata:

```json
{
  "id": 42,
  "headline": "Article Title",
  "status": "draft"
}
```

Error responses follow a consistent format:

```json
{
  "detail": "Error description"
}
```

---

## Middleware

### CORS Middleware

Configured for cross-origin requests from frontend:
- Allowed origins from environment configuration
- Credentials supported for auth headers
- All standard HTTP methods allowed

### Authentication Middleware

JWT validation happens via FastAPI dependencies, not middleware, enabling per-route configuration.

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | OK | Successful GET/PUT |
| 201 | Created | Successful POST creating resource |
| 400 | Bad Request | Invalid request data |
| 401 | Unauthorized | Invalid or missing token |
| 403 | Forbidden | Valid token but insufficient permissions |
| 404 | Not Found | Resource doesn't exist |
| 422 | Unprocessable | Validation error |
| 500 | Server Error | Unexpected backend error |

### Exception Handlers

Custom exception handlers for:
- Database connection errors
- ChromaDB unavailable
- External API failures
- Rate limiting

---

## Processing Model

All operations run synchronously within the request lifecycle:

| Operation | Execution | Description |
|-----------|-----------|-------------|
| Chat response | Sync | LangGraph workflow |
| Research workflow | Sync | AnalystAgent research |
| Article publishing | Sync | EditorSubAgent with HITL |
| Data download | Sync | External API calls |

---

## WebSocket Support

### Connection Endpoint

```
ws://host/ws/{user_id}
```

### Message Types

| Type | Direction | Purpose |
|------|-----------|---------|
| `ping` | Client → Server | Keep-alive |
| `pong` | Server → Client | Keep-alive response |
| `task_update` | Server → Client | Background task progress |
| `hitl_pending` | Server → Client | Approval request |

---

## API Documentation

### Automatic Docs

FastAPI generates interactive documentation:

| URL | Format | Features |
|-----|--------|----------|
| `/docs` | Swagger UI | Interactive testing |
| `/redoc` | ReDoc | Clean documentation |
| `/openapi.json` | OpenAPI spec | Machine-readable |

---

## Configuration

### Environment Variables

Key backend configuration:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection |
| `REDIS_URL` | Redis connection |
| `CHROMA_HOST` | ChromaDB host |
| `OPENAI_API_KEY` | LLM API key |
| `JWT_SECRET_KEY` | Token signing key |
| `CORS_ORIGINS` | Allowed frontend origins |

---

## Health Check

### Endpoint

```
GET /health
```

Returns service status including database and cache connectivity.

---

## Related Documentation

- [Authentication](./01-authentication.md) - OAuth and JWT details
- [Authorization](./02-authorization_concept.md) - Permission system
- [Multi-Agent Architecture](./08-multi-agent-architecture.md) - Chat and agent system
- [Databases](./11-databases.md) - Data storage
