# AI Research Chatbot Platform

## Overview

This platform is a full-stack AI-powered research chatbot application designed for financial analysis and content management. It combines multi-agent AI systems, semantic search, and a comprehensive editorial workflow to deliver personalized research insights across multiple financial domains.

---

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

---

## Core Capabilities

### Multi-Agent AI Chat System
- Intent-based routing to specialized handler nodes
- Domain-specific research agents with dedicated tools
- Human-in-the-loop (HITL) workflow for critical actions
- ChromaDB-powered semantic search for context retrieval
- Redis-backed conversation memory

### Content Management
- Editorial workflow: Draft, Editor Review, Published
- AI-assisted article creation and research
- Resource management for images, PDFs, tables, and data files
- Topic-based content organization

### Access Control
- Topic-scoped role-based permissions
- Role hierarchy: admin, analyst, editor, reader
- JWT tokens with embedded permission scopes
- API endpoint security by role

---

## Research Topics

The platform organizes content into configurable research domains:

| Topic | Focus Area |
|-------|------------|
| **Macroeconomic** | GDP, inflation, monetary policy, central bank actions |
| **Equity** | Stock analysis, valuations, sector trends, earnings |
| **Fixed Income** | Bond markets, yields, credit spreads, duration |
| **ESG** | Environmental, social, governance factors |

Each topic has dedicated permission groups, content collections, and configurable prompts.

---

## User Roles

| Role | Capabilities |
|------|--------------|
| **Reader** | View published articles, use chat interface, rate articles |
| **Analyst** | Create content, upload resources, submit for review |
| **Editor** | Review articles, request changes, publish content |
| **Admin** | Full topic access, content moderation, user management |
| **Global Admin** | System-wide administration, all topic access |

---

## Documentation Index

### Core Concepts

| Chapter | Topic | Description |
|---------|-------|-------------|
| 01 | Authentication | OAuth flow, JWT tokens, LinkedIn integration, token lifecycle |
| 02 | Authorization | Role-based access control, scopes, permission hierarchy |
| 03 | Topic Structure | Research domains, topic configuration, content organization |
| 04 | User Management | User accounts, groups, role assignments, preferences |

### Backend Architecture

| Chapter | Topic | Description |
|---------|-------|-------------|
| 05 | FastAPI Backend | API structure, endpoints, middleware, dependencies |
| 06 | Security | Security headers, input validation, data protection |
| 07 | Testing | Unit tests, integration tests, test infrastructure |

### AI System

| Chapter | Topic | Description |
|---------|-------|-------------|
| 08 | Multi-Agent Architecture | LangGraph workflow, agent hierarchy, state management, HITL |

### Content and Storage

| Chapter | Topic | Description |
|---------|-------|-------------|
| 09 | Resources | Resource types, file management, article attachments |
| 10 | Databases | PostgreSQL schema, ChromaDB collections, data models |
| 11 | Redis Cache | Token registry, content cache, session storage |

### Frontend and User Experience

| Chapter | Topic | Description |
|---------|-------|-------------|
| 12 | Frontend | SvelteKit structure, pages, components, stores |
| 13 | User Workflows | Step-by-step guides for all user roles |
| 14 | UI Actions | Chat-triggered UI commands, navigation context |

---

## Architecture Diagrams

Visual representations are available in the diagrams directory:

| Diagram | Description |
|---------|-------------|
| system-architecture.mmd | High-level system components |
| data-flow.mmd | Request/response data flow |
| multi-agent-workflow.mmd | LangGraph agent workflow |
| permission-model.mmd | Role hierarchy and scopes |
| article-lifecycle.mmd | Content workflow states |
| authentication-flow.mmd | OAuth sequence |
| hitl-workflow.mmd | Human-in-the-loop approval |
| frontend-architecture.mmd | SvelteKit structure |
| api-routes.mmd | Endpoint organization |

---

## Getting Started

Contact your system administrator for access credentials and the application URL.

---

## Support

For technical support or access requests, contact your organization's IT administrator.
