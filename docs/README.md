# AI Research Chatbot Platform Documentation

## Overview

This platform is a full-stack AI-powered research chatbot application designed for financial analysis and content management. It combines multi-agent AI systems, semantic search, and a comprehensive editorial workflow to deliver personalized research insights across multiple financial domains.

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (SvelteKit)                           │
│                    TypeScript / Svelte 5 / Server-Side Rendering            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BACKEND (FastAPI)                              │
│                         Python 3.12+ / Async / REST API                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Auth &    │  │   Content   │  │  Resource   │  │   Multi-Agent       │ │
│  │   Users     │  │   Articles  │  │  Management │  │   AI System         │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
         │                  │                  │                  │
         ▼                  ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│  PostgreSQL  │  │   ChromaDB   │  │    Redis     │  │   OpenAI / Google    │
│  (Relations) │  │  (Vectors)   │  │   (Cache)    │  │   (AI Services)      │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────────────┘
```

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | SvelteKit 2.x, TypeScript, Svelte 5 | Modern reactive UI with SSR |
| **Backend** | FastAPI, Python 3.12+ | Async REST API |
| **AI Orchestration** | LangChain, LangGraph | Multi-agent workflow management |
| **LLM Provider** | OpenAI GPT-4o/GPT-4o-mini | Natural language processing |
| **Vector Database** | ChromaDB | Semantic search and embeddings |
| **Relational Database** | PostgreSQL 16 | Users, groups, relationships |
| **Cache Layer** | Redis 7 | Token cache, content cache |
| **Authentication** | LinkedIn OAuth 2.0, JWT | Enterprise SSO integration |
| **Package Management** | uv (Python), npm (Node.js) | Fast dependency management |
| **Containerization** | Docker Compose | Local development and deployment |

## Core Features

### 1. Multi-Agent AI Chat System
- **Router Agent**: Analyzes user queries and routes to specialized agents
- **Specialist Agents**: Domain experts for Equity, Economics, and Fixed Income
- **Context-Aware Responses**: Leverages ChromaDB for semantic search
- **Conversation Memory**: Redis-backed persistent conversation history

### 2. Content Management System
- **Article Creation**: AI-assisted content generation (1000-2000 words)
- **Editorial Workflow**: Draft → Editor → Published status pipeline
- **Topic Specialization**: Macro, Equity, Fixed Income, ESG categories
- **PDF Export**: Generate professional PDF documents

### 3. Resource Management
- **Multi-Type Support**: Images, PDFs, Text, Tables, Timeseries, Excel, CSV
- **Semantic Indexing**: Text resources vectorized for search
- **Article Linking**: Associate resources with articles
- **Permanent URLs**: Hash-based IDs for stable resource references

### 4. Role-Based Access Control
- **Topic-Based Permissions**: Granular access per research domain
- **Role Hierarchy**: Admin > Analyst > Editor > Reader
- **Group Management**: Flexible user-group assignments
- **JWT Authorization**: Scoped tokens with permission encoding

## Topic Structure

The platform organizes research into four primary topics:

| Topic | Description | Use Cases |
|-------|-------------|-----------|
| **Macro** | Macroeconomic analysis | GDP, inflation, monetary policy |
| **Equity** | Stock market research | Company analysis, valuations |
| **Fixed Income** | Bond market analysis | Yields, credit spreads, duration |
| **ESG** | Sustainability investing | Environmental, social, governance |

Each topic has dedicated:
- Admin group (`{topic}:admin`)
- Analyst group (`{topic}:analyst`)
- Editor group (`{topic}:editor`)
- Reader group (`{topic}:reader`)

## Data Flow Overview

### Chat Interaction
```
User Message → JWT Validation → Router Agent → Specialist Agent
     → ChromaDB Context → LLM Response → Cached Result
```

### Content Creation
```
Admin Request → Prompt Assembly → LLM Generation → ChromaDB Embedding
     → PostgreSQL Metadata → Cache Invalidation
```

### Resource Upload
```
File Upload → Permission Check → Storage (S3/Local) → PostgreSQL Entry
     → ChromaDB Embedding (if text) → Article Linking
```

## Documentation Index

1. **[Authentication & Authorization](./01-authentication.md)** - OAuth flow, JWT tokens, permission system
2. **[User Management](./02-user-management.md)** - User accounts, groups, roles
3. **[Topic Structure](./03-topic-structure.md)** - Research domains, permissions per topic
4. **[Agentic Workflow](./04-agentic-workflow.md)** - Multi-agent system, routing, specialists
5. **[Resources & PDF](./05-resources-pdf.md)** - File management, resource types, PDF generation
6. **[Redis Cache](./06-redis-cache.md)** - Token cache, content cache, invalidation
7. **[Storage Architecture](./07-databases.md)** - PostgreSQL (relationships), ChromaDB (embeddings), S3 (files)

## Getting Started

Contact your system administrator for access credentials and the application URL.

### User Roles

| Role | Capabilities |
|------|-------------|
| **Reader** | View published articles, use chat interface |
| **Editor** | Edit articles, manage editorial workflow |
| **Analyst** | Create content, upload resources, full editing |
| **Admin** | Full access including user and topic management |

## Support

For technical support or access requests, contact your organization's IT administrator.

## License

Proprietary - All rights reserved.
