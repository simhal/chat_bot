# Multi-Agent Architecture

## Overview

The platform uses a **multi-agent AI system** built on LangGraph for intelligent query routing and specialized domain expertise. This document describes the architecture, agent hierarchy, and workflows that power the system.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Agent Hierarchy](#2-agent-hierarchy)
3. [State Management](#3-state-management)
4. [Permission Model](#4-permission-model)
5. [Human-in-the-Loop Workflow](#5-human-in-the-loop-workflow)
6. [LangGraph Features](#6-langgraph-features)

---

## 1. Architecture Overview

### 1.1 Design Goals

| Goal | Description |
|------|-------------|
| **Security** | Tools filtered at runtime based on user's JWT scopes |
| **Flexibility** | Dynamic agent composition based on user role |
| **Traceability** | Full audit trail via workflow context |
| **Extensibility** | Easy addition of new agents and tools |
| **Human Oversight** | Critical actions (publishing) require human approval |

### 1.2 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tool Access Control | Runtime filtering | All tools registered, filtered per-request based on scopes |
| Resource Creation | Auto-create and attach | Research agents automatically create DRAFT resources |
| Editor Approval | HITL interrupt | LangGraph interrupt pattern allows human review |
| State Management | Enhanced TypedDict | Maintains LangGraph compatibility |

### 1.3 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐          │
│  │  Web UI         │  │  API Client     │  │  CLI Tool       │          │
│  │  + WebSocket    │  │                 │  │                 │          │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘          │
└───────────┼────────────────────┼────────────────────┼────────────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           API LAYER                                      │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌───────────────┐   │
│  │  /api/chat          │  │  /api/tools/*       │  │  /ws/{user}   │   │
│  │  (chat endpoint)    │  │  (REST endpoints)   │  │  (WebSocket)  │   │
│  └──────────┬──────────┘  └──────────┬──────────┘  └───────┬───────┘   │
│             │                        │                      │           │
│             └────────────┬───────────┴──────────────────────┘           │
│                          ▼                                               │
│  ┌───────────────────────────────────────────────────────────────┐      │
│  │                    Authentication Layer                        │      │
│  │  JWT Token → UserContext (scopes, tonality, preferences)       │      │
│  └───────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
┌───────────────────────────────┐  ┌───────────────────────────────────┐
│     SYNCHRONOUS AGENTS        │  │      CELERY BACKGROUND TASKS       │
│        (FastAPI)              │  │          (Workers)                 │
│                               │  │                                    │
│  ┌─────────────────────────┐  │  │  ┌──────────────────────────────┐ │
│  │ MainChatAgent           │  │  │  │ AnalystAgent Task            │ │
│  │ ArticleQueryAgent       │  │  │  │ WebSearchAgent               │ │
│  │ (reader operations)     │  │  │  │ DataDownloadAgent            │ │
│  └─────────────────────────┘  │  │  │ EditorSubAgent Task          │ │
│                               │  │  └──────────────────────────────┘ │
└───────────────────────────────┘  └───────────────────────────────────┘
                                              │
                                              ▼
                                   ┌────────────────────┐
                                   │  Redis             │
                                   │  - Message Broker  │
                                   │  - Result Backend  │
                                   │  - Checkpoints     │
                                   └────────────────────┘
```

### 1.4 Request Data Flow

1. **Client Request** - User sends a message via chat interface
2. **JWT Validation** - Extract user scopes and permissions
3. **Build UserContext** - Load user preferences, scopes, and tonality settings
4. **Initialize AgentState** - Prepare conversation history and available tools
5. **MainChatAgent.process()** - Build system prompt, filter tools, route to sub-agent
6. **Response with metadata** - Return response, agent type, tools used, workflow state

---

## 2. Agent Hierarchy

### 2.1 Agent Composition

```
MainChatAgent (Orchestrator)
│
├── Owns: ToolRegistry (filtered view)
├── Owns: PromptComposer (dynamic tonality)
├── Owns: UserContext (scopes, preferences)
│
├── Direct Sub-Agents (for readers):
│   │
│   └── ArticleQueryAgent [per topic]
│       ├── Required Role: reader
│       ├── Topic Scoped: Yes
│       ├── Purpose: Search and read articles
│       └── Tools: search_articles, get_article
│
├── AnalystAgent [per topic]
│   ├── Required Role: analyst
│   ├── Topic Scoped: Yes
│   ├── Purpose: Research workflows, create articles with resources
│   │
│   ├── Composes Multiple Sub-Agents:
│   │   ├── ArticleQueryAgent (create/write articles)
│   │   ├── ResourceQueryAgent (find existing resources)
│   │   ├── WebSearchAgent (web/news search)
│   │   └── DataDownloadAgent (fetch structured data)
│   │
│   └── Resource Creation: create_text_resource, create_table_resource
│
└── EditorSubAgent [per topic]
    ├── Required Role: editor
    ├── Topic Scoped: Yes
    ├── Purpose: Editorial review and publishing with HITL
    └── Tools: review_article, request_changes, publish (HITL)
```

### 2.2 Agent Responsibilities

| Agent | Purpose | Key Capabilities |
|-------|---------|------------------|
| **MainChatAgent** | Primary orchestrator | Memory management, routing, user context |
| **ArticleQueryAgent** | Article operations | Search, create drafts, write content |
| **AnalystAgent** | Research workflows | Coordinates research agents, creates resources |
| **WebSearchAgent** | External information | Web search, news search |
| **DataDownloadAgent** | Structured data | Stock data, economic indicators, PDFs |
| **EditorSubAgent** | Publishing workflow | Review, request changes, publish with HITL |

### 2.3 Agent Execution Model

| Agent | Execution | Reason |
|-------|-----------|--------|
| **MainChatAgent** | Synchronous (FastAPI) | Quick response needed |
| **ArticleQueryAgent** | Synchronous or Celery | Depends on context |
| **AnalystAgent** | Celery Worker | Heavy research, minutes |
| **WebSearchAgent** | Celery Worker | External API calls |
| **DataDownloadAgent** | Celery Worker | External API calls |
| **EditorSubAgent** | Celery Worker | HITL workflow, async |

---

## 3. State Management

### 3.1 State Components

The workflow maintains state that flows through each node:

| State Component | Purpose |
|-----------------|---------|
| **UserContext** | User identity, scopes, tonality preferences |
| **WorkflowContext** | Multi-step workflow tracking (article ID, resources) |
| **AgentState** | Messages, routing, tools, iteration control |

### 3.2 UserContext Fields

| Field | Description |
|-------|-------------|
| `user_id`, `name`, `email` | User identity |
| `scopes` | Authorization scopes (e.g., "macro:analyst") |
| `role` | Highest role: admin > analyst > editor > reader |
| `chat_tonality_text` | User's preferred chat communication style |
| `content_tonality_text` | User's preferred article writing style |

### 3.3 WorkflowContext Fields

| Field | Description |
|-------|-------------|
| `workflow_id` | UUID for tracking |
| `workflow_type` | research, write, edit, or publish |
| `current_article_id` | Article being worked on |
| `current_topic` | Topic context |
| `pending_resources` | Resources created during workflow |
| `approval_pending` | HITL approval state |

### 3.4 State Flow

```
Request Start
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  create_initial_state()                                      │
│  ├── Load UserContext from JWT + DB                         │
│  ├── Filter available_tools by scopes                       │
│  ├── Load conversation history from Redis                   │
│  └── Initialize workflow_context = None                     │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  MainChatAgent.process(state)                                │
│  ├── Increment iterations                                   │
│  ├── Route to appropriate sub-agent                         │
│  └── Delegate or handle directly                            │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  Sub-Agent.process(state)                                    │
│  ├── Check has_permission(user_context)                     │
│  ├── Get available tools for user                           │
│  ├── Execute tools, update state                            │
│  └── Update workflow_context if needed                      │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  Finalize                                                    │
│  ├── Save to conversation memory                            │
│  └── Return response                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Permission Model

### 4.1 Role Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                      ROLE HIERARCHY                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  global:admin ──────────────────────────────────────────┐   │
│       │                                                  │   │
│       │  (Full access to all topics and tools)          │   │
│       ▼                                                  │   │
│  {topic}:admin ─────────────────────────────────────┐   │   │
│       │                                              │   │   │
│       │  (Full access within topic)                  │   │   │
│       ▼                                              │   │   │
│  {topic}:analyst ───────────────────────────────┐   │   │   │
│       │                                          │   │   │   │
│       │  (Create articles, resources, research)  │   │   │   │
│       ▼                                          │   │   │   │
│  {topic}:editor ────────────────────────────┐   │   │   │   │
│       │                                      │   │   │   │   │
│       │  (Edit articles, publish with HITL)  │   │   │   │   │
│       ▼                                      │   │   │   │   │
│  {topic}:reader ────────────────────────┐   │   │   │   │   │
│       │                                  │   │   │   │   │   │
│       │  (Read articles, search)         │   │   │   │   │   │
│       ▼                                  ▼   ▼   ▼   ▼   ▼   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    NO ACCESS                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Role Levels: admin=4, analyst=3, editor=2, reader=1        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Scope Format

Scopes follow the pattern `{topic}:{role}` or `global:{role}`:

| Example | Meaning |
|---------|---------|
| `global:admin` | System administrator (all access) |
| `macro:analyst` | Analyst access to macro topic |
| `equity:reader` | Reader access to equity topic |
| `fixed_income:editor` | Editor access to fixed income topic |

Users can have multiple scopes, e.g., `["macro:analyst", "equity:reader"]`.

### 4.3 Permission Matrix

| Operation | Required Role | Topic Scoped |
|-----------|---------------|--------------|
| Search articles | reader | Yes |
| Get article | reader | No |
| Search resources | reader | No |
| Create draft article | analyst | Yes |
| Write article content | analyst | Yes |
| Create resources | analyst | Yes |
| Web search | analyst | No |
| Submit for review | analyst | Yes |
| Request changes | editor | Yes |
| Publish article (HITL) | editor | Yes |
| Get topic prompts | admin | Yes |

### 4.4 Tool Registry

All tools are registered centrally with permission metadata:

| Metadata Field | Purpose |
|----------------|---------|
| `required_role` | Minimum role to use the tool |
| `topic_scoped` | Whether topic permission is required |
| `global_admin_override` | Whether global:admin bypasses checks |
| `requires_hitl` | Whether tool triggers human approval |

At runtime, tools are filtered based on the user's scopes before being made available to agents.

---

## 5. Human-in-the-Loop Workflow

### 5.1 Article Lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ARTICLE LIFECYCLE                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐                                                       │
│  │  DRAFT   │ ◄─────────────────────────────────────────────┐      │
│  └────┬─────┘                                                │      │
│       │                                                      │      │
│       │ submit_for_review() (analyst+)                       │      │
│       ▼                                                      │      │
│  ┌──────────┐                                                │      │
│  │  EDITOR  │ ─────────────────────────────────────┐        │      │
│  └────┬─────┘                                       │        │      │
│       │                                             │        │      │
│       │ publish_article() (editor+, triggers HITL)  │        │      │
│       ▼                             request_changes()       │      │
│  ┌───────────────────┐                              │        │      │
│  │ PENDING_APPROVAL  │                              │        │      │
│  └─────────┬─────────┘                              │        │      │
│            │                                         │        │      │
│            │ LangGraph interrupt_before              │        │      │
│            │                                         │        │      │
│            ▼                                         │        │      │
│  ┌──────────────────────────────────────────────────┴────────┘      │
│  │                    HUMAN REVIEW                                   │
│  │  ┌─────────────┐           ┌─────────────┐                       │
│  │  │   Approve   │           │   Reject    │                       │
│  │  └──────┬──────┘           └──────┬──────┘                       │
│  └─────────┼─────────────────────────┼──────────────────────────────┘
│            │                         │
│            ▼                         ▼
│  ┌──────────────┐           ┌──────────┐
│  │  PUBLISHED   │           │  EDITOR  │ (returned for revision)
│  └──────────────┘           └──────────┘
│
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 HITL Implementation

The system uses LangGraph's native `interrupt_before` pattern for human approval:

1. **Trigger**: When `publish_article` tool is invoked
2. **Pause**: Workflow state is checkpointed to Redis
3. **Notify**: WebSocket notification sent to user/editor
4. **Review**: Human reviews via web UI or API
5. **Resume**: Workflow continues with approval decision

### 5.3 Approval Request Tracking

Approval requests are tracked in the database with:

| Field | Purpose |
|-------|---------|
| `article_id` | Article being approved |
| `requested_by` | User who submitted |
| `status` | pending, approved, rejected, expired |
| `editor_notes` | Submitter's notes |
| `reviewed_by` | User who reviewed |
| `review_notes` | Reviewer's feedback |

---

## 6. LangGraph Features

### 6.1 Features Used

| Feature | Usage | Benefit |
|---------|-------|---------|
| **Conditional Edges** | Router decides which agent handles query | Dynamic workflow routing |
| **Subgraph Composition** | AnalystAgent contains nested graphs | Modular, reusable components |
| **Human-in-the-Loop** | `interrupt_before` for publish approval | Native HITL support |
| **Parallel Execution** | Research agents run in parallel | Faster data gathering |
| **Checkpointing** | Save workflow state to Redis | Resume interrupted workflows |
| **Streaming** | Stream intermediate agent outputs | Real-time UI updates |
| **Tool Calling** | ReAct pattern with structured tools | Reliable tool execution |
| **State Reducers** | Message accumulation | Clean state management |

### 6.2 Workflow Graph Structure

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        LANGGRAPH WORKFLOW                                │
│                                                                          │
│    START                                                                 │
│      │                                                                   │
│      ▼                                                                   │
│  ┌────────┐                                                              │
│  │ Router │ ─────────────────────────────────────────────────────────┐  │
│  └────┬───┘                                                           │  │
│       │                                                               │  │
│       │ Conditional Edges                                             │  │
│       │                                                               │  │
│  ┌────┴─────┬──────────────┬──────────────┐                          │  │
│  │          │              │              │                           │  │
│  ▼          ▼              ▼              ▼                           │  │
│ ┌────┐  ┌────────┐  ┌──────────┐  ┌──────────┐                       │  │
│ │Read│  │Analyst │  │  Editor  │  │ General  │                       │  │
│ │    │  │        │  │          │  │          │                       │  │
│ └──┬─┘  └────┬───┘  └────┬─────┘  └────┬─────┘                       │  │
│    │         │           │             │                              │  │
│    │    ┌────┴────┐      │             │                              │  │
│    │    │ SUBGRAPH│      │             │                              │  │
│    │    │         │      │             │                              │  │
│    │    │ ┌─────┐ │ ┌────┴────┐        │                              │  │
│    │    │ │Web  │ │ │INTERRUPT│        │                              │  │
│    │    │ │Srch │ │ │ BEFORE  │        │                              │  │
│    │    │ └──┬──┘ │ │(publish)│        │                              │  │
│    │    │ ┌──┴──┐ │ └────┬────┘        │                              │  │
│    │    │ │Data │ │      │             │                              │  │
│    │    │ │Down │ │      │             │                              │  │
│    │    │ └──┬──┘ │      │             │                              │  │
│    │    │    ▼    │      │             │                              │  │
│    │    │ ┌─────┐ │      │             │                              │  │
│    │    │ │Write│ │      │             │                              │  │
│    │    │ │Artcl│ │      │             │                              │  │
│    │    │ └─────┘ │      │             │                              │  │
│    │    └────┬────┘      │             │                              │  │
│    │         │           │             │                              │  │
│    └─────────┴───────────┴─────────────┘                              │  │
│                         │                                              │  │
│                         ▼                                              │  │
│                       END                                              │  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Related Documentation

- [Authentication](./01-authentication.md) - OAuth and JWT system
- [Authorization](./02-authorization_concept.md) - Permissions and access control
- [User Management](./04-user-management.md) - User roles and groups
- [Resources](./10-resources-concept.md) - Resource management
- [Celery Workers](./09-celery-workers.md) - Background task processing

---

## Glossary

| Term | Definition |
|------|------------|
| **HITL** | Human-in-the-loop - requiring human approval for critical actions |
| **Scope** | Permission string in format `{topic}:{role}` |
| **Topic** | Content category (macro, equity, fixed_income, esg) |
| **Tonality** | Writing style/tone configuration for prompts |
| **Workflow** | Multi-step operation tracked via WorkflowContext |
