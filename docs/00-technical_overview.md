# AI Research Chatbot Platform Documentation

## Overview

This platform is a full-stack AI-powered research chatbot application designed for financial analysis and content management. It combines multi-agent AI systems, semantic search, and a comprehensive editorial workflow to deliver personalized research insights across multiple financial domains.

## Architecture Diagram

See the interactive diagrams in [diagrams/](./diagrams/) for visual representations:

- [System Architecture](./diagrams/system-architecture.mmd) - High-level system components
- [Data Flow](./diagrams/data-flow.mmd) - Request/response data flow
- [Multi-Agent Workflow](./diagrams/multi-agent-workflow.mmd) - LangGraph agent workflow
- [Permission Model](./diagrams/permission-model.mmd) - Role hierarchy and scopes
- [Article Lifecycle](./diagrams/article-lifecycle.mmd) - Content workflow states
- [Authentication Flow](./diagrams/authentication-flow.mmd) - OAuth sequence
- [HITL Workflow](./diagrams/hitl-workflow.mmd) - Human-in-the-loop approval
- [Frontend Architecture](./diagrams/frontend-architecture.mmd) - SvelteKit structure
- [API Routes](./diagrams/api-routes.mmd) - Endpoint organization

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | SvelteKit 2.x, TypeScript, Svelte 5 | Modern reactive UI with SSR |
| **Backend** | FastAPI, Python 3.12+ | Async REST API |
| **AI Orchestration** | LangChain, LangGraph | Multi-agent workflow management |
| **LLM Provider** | OpenAI GPT-4o/GPT-4o-mini | Natural language processing |
| **Vector Database** | ChromaDB | Semantic search and embeddings |
| **Relational Database** | PostgreSQL 16 | Users, groups, content metadata |
| **Cache Layer** | Redis 7 | Token cache, content cache, sessions |
| **Authentication** | LinkedIn OAuth 2.0, JWT | Enterprise SSO integration |
| **Package Management** | uv (Python), npm (Node.js) | Fast dependency management |
| **Containerization** | Docker Compose | Local development and deployment |

## Core Features

### 1. Multi-Agent AI Chat System
- **Intent Router**: Analyzes user queries and routes to appropriate handlers
- **Specialist Agents**: Research agents with domain-specific tools
- **HITL Workflow**: Human approval for article publishing
- **Context-Aware Responses**: ChromaDB-powered semantic search
- **Conversation Memory**: Redis-backed persistent chat history

### 2. Content Management System
- **Article Lifecycle**: Draft → Editor → Published workflow
- **AI-Assisted Writing**: Analyst agents help create research content
- **Resource Management**: Images, PDFs, tables, data files
- **Topic Organization**: Content organized by research domains

### 3. Role-Based Access Control
- **Topic-Scoped Permissions**: Per-topic role assignments
- **Role Hierarchy**: admin > analyst > editor > reader
- **API Endpoint Security**: Role-based URL structure
- **JWT Authorization**: Scoped tokens with permission encoding

## Topic Structure

The platform organizes research into configurable topics (e.g., Macro, Equity, Fixed Income, ESG). Each topic has:
- Dedicated permission groups (`{topic}:admin`, `{topic}:analyst`, etc.)
- Separate content collections
- Topic-specific prompts and settings

## Data Flow Overview

### Chat Interaction
```
User Message → JWT Validation → MainChatAgent → Intent Router
    → Handler/SubAgent → ChromaDB Context → LLM Response
```

### Content Creation
```
Analyst Request → Background Task → Research Agents → Article Draft
    → ChromaDB Embedding → PostgreSQL Metadata
```

### Publishing Workflow
```
Submit for Review → Editor Review → HITL Approval
    → Publish (with interrupt) → Human Confirm → Published
```

---

## Documentation Index

### Core Concepts

1. **[Authentication](./01-authentication.md)**
   OAuth flow, JWT tokens, LinkedIn integration

2. **[Authorization & Permissions](./02-authorization_concept.md)**
   Role-based access control, scopes, permission hierarchy

3. **[Topic Structure](./03-topic-structure.md)**
   Research domains, topic configuration, content organization

4. **[User Management](./04-user-management.md)**
   User accounts, groups, role assignments

### Backend Architecture

5. **[FastAPI Backend](./05-fastapi_backend.md)**
   API structure, endpoints, middleware, dependencies

6. **[Security](./06-security.md)**
   Security measures and best practices

7. **[Testing](./07-unit-testing.md)**
   Unit tests, integration tests, test infrastructure

### AI System

8. **[Multi-Agent Architecture](./08-multi-agent-architecture.md)**
   LangGraph workflow, agent hierarchy, state management, HITL


### Content & Storage

10. **[Resources](./10-resources-concept.md)**
    Resource types, file management, article attachments

11. **[Databases](./11-databases.md)**
    PostgreSQL schema, ChromaDB collections, data models

12. **[Redis Cache](./12-redis-cache.md)**
    Token registry, content cache, session storage

### Frontend & UX

13. **[Frontend](./13-frontend.md)**
    SvelteKit structure, pages, components, stores

14. **[User Workflows](./14-user-workflows.md)**
    Step-by-step guides for all user roles

15. **[UI Actions](./15-ui-actions.md)**
    Chat-triggered UI commands, navigation context

---

## Getting Started

Contact your system administrator for access credentials and the application URL.

### User Roles

| Role | Capabilities |
|------|-------------|
| **Reader** | View published articles, use chat interface, rate articles |
| **Analyst** | Create content, upload resources, submit for review |
| **Editor** | Review articles, request changes, publish content |
| **Admin** | Full topic access, content moderation, user management |
| **Global Admin** | System-wide administration, topic management |

## Support

For technical support or access requests, contact your organization's IT administrator.

## License

Proprietary - All rights reserved.
