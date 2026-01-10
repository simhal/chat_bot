# Multi-Agent Architecture

## Overview

The platform uses a **multi-agent AI system** built on LangGraph for intelligent query routing and specialized domain expertise. This document describes the architecture, agent hierarchy, and workflows that power the system.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Graph Architecture](#2-graph-architecture)
3. [State Management](#3-state-management)
4. [Permission Model](#4-permission-model)
5. [Human-in-the-Loop Workflow](#5-human-in-the-loop-workflow)
6. [LangGraph Features](#6-langgraph-features)

---

## 1. Architecture Overview

### 1.1 Design Goals

| Goal | Description |
|------|-------------|
| **Simplicity** | Single entry point (`invoke_chat`), singleton graph pattern |
| **Performance** | Graph compiled once at startup, reused for all requests |
| **Security** | Intent-based routing with permission checks per node |
| **Traceability** | Full audit trail via LangSmith integration |
| **Extensibility** | Easy addition of new handler nodes |
| **Human Oversight** | Critical actions (publishing) require human approval |

### 1.2 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Graph Instance | Singleton pattern | Graph built once at startup, reused for all requests |
| Entry Point | Single `invoke_chat()` function | Clean API, no wrapper classes |
| State Schema | Pydantic + TypedDict | Pydantic for API validation, TypedDict for LangGraph |
| Routing | Intent classification | Router node classifies intent, routes to handler nodes |
| Checkpointing | Redis (production) / Memory (dev) | HITL state persistence across restarts |

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
│  │  /api/chat          │  │  /api/approvals/*   │  │  /ws/{user}   │   │
│  │  (chat endpoint)    │  │  (HITL workflows)   │  │  (WebSocket)  │   │
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
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        AGENT SERVICE LAYER                               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  AgentService.chat()                                             │    │
│  │  └── invoke_chat(message, user_context, navigation_context)      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                  │                                       │
│                                  ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Singleton Chat Graph (built once at startup)                    │    │
│  │                                                                   │    │
│  │  START → router_node → [handler nodes] → response_builder → END  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                       ┌────────────────────┐
                       │  Redis             │
                       │  - Checkpoints     │
                       │  - Session Cache   │
                       │  - HITL State      │
                       └────────────────────┘
```

### 1.4 Request Data Flow

1. **Client Request** - User sends a message via chat interface
2. **JWT Validation** - Extract user scopes and permissions
3. **Build UserContext** - Load user preferences, scopes, and tonality settings
4. **Build NavigationContext** - Capture frontend context (section, topic, article)
5. **invoke_chat()** - Single entry point to the graph
6. **Router Node** - Classify intent and route to appropriate handler
7. **Handler Node** - Process request (ui_action, content_gen, editor, general, entitlements)
8. **Response Builder** - Assemble final ChatResponse with metadata
9. **Return** - Response with agent_type, ui_action, articles, etc.

---

## 2. Graph Architecture

### 2.1 Singleton Graph Pattern

The chat graph is built **once at startup** and reused for all requests:

```python
# agents/graph.py

_GRAPH = None  # Singleton instance

def get_graph():
    """Get the singleton graph instance, building it if necessary."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH

def invoke_chat(
    message: str,
    user_context: UserContext,
    navigation_context: Optional[NavigationContext] = None,
    thread_id: Optional[str] = None,
) -> ChatResponse:
    """Single entry point for all chat processing."""
    graph = get_graph()
    state = create_initial_state(user_context, messages, navigation_context)
    result = graph.invoke(state, config)
    return ChatResponse(...)
```

### 2.2 Graph Structure

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CHAT GRAPH STRUCTURE                              │
│                                                                          │
│    START                                                                 │
│      │                                                                   │
│      ▼                                                                   │
│  ┌────────────┐                                                          │
│  │   router   │  (Classifies user intent)                                │
│  └──────┬─────┘                                                          │
│         │                                                                │
│         │ route_by_intent() - Conditional edges                          │
│         │                                                                │
│  ┌──────┴──────┬──────────────┬──────────────┬──────────────┐           │
│  │             │              │              │              │            │
│  ▼             ▼              ▼              ▼              ▼            │
│ ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐       │
│ │ui_action│ │content_  │ │ editor_  │ │ general_ │ │entitlements│       │
│ │         │ │generation│ │ workflow │ │   chat   │ │            │       │
│ └────┬────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └─────┬──────┘       │
│      │           │            │            │             │               │
│      └───────────┴────────────┴────────────┴─────────────┘               │
│                               │                                          │
│                               ▼                                          │
│                     ┌─────────────────┐                                  │
│                     │response_builder │  (Assembles ChatResponse)        │
│                     └────────┬────────┘                                  │
│                              │                                           │
│                              ▼                                           │
│                             END                                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Handler Nodes

| Node | Intent Type | Purpose |
|------|-------------|---------|
| **router_node** | - | Classifies user intent using LLM |
| **ui_action_node** | `ui_action` | Navigation, button clicks, tab switches |
| **content_generation_node** | `content_generation` | Article writing (analyst workflow) |
| **editor_workflow_node** | `editor_workflow` | Review, publish, reject (HITL) |
| **general_chat_node** | `general_chat` | Q&A, topic queries, article search |
| **entitlements_node** | `entitlements` | Permission questions ("what can I do?") |
| **response_builder_node** | - | Assembles final response from state |

### 2.4 Intent Classification

The router node uses LLM to classify user intent:

```python
IntentType = Literal[
    "navigation",        # → ui_action_node
    "ui_action",         # → ui_action_node
    "content_generation", # → content_generation_node
    "editor_workflow",   # → editor_workflow_node
    "general_chat",      # → general_chat_node
    "entitlements"       # → entitlements_node
]
```

---

## 3. State Management

### 3.1 State Schema

The system uses a dual approach:
- **Pydantic models** for API validation and response structure
- **TypedDict** for LangGraph state management

```python
# Pydantic model for API responses
class ChatResponse(BaseModel):
    response: str
    agent_type: str = "general"
    routing_reason: str = ""
    articles: List[Dict[str, Any]] = []
    ui_action: Optional[Dict[str, Any]] = None
    navigation: Optional[Dict[str, Any]] = None
    editor_content: Optional[Dict[str, Any]] = None
    confirmation: Optional[Dict[str, Any]] = None

# TypedDict for LangGraph state
class AgentState(TypedDict):
    # Input
    messages: Annotated[List[BaseMessage], operator.add]
    user_context: Optional[UserContext]
    navigation_context: Optional[NavigationContext]

    # Routing
    selected_agent: Optional[str]
    routing_reason: Optional[str]
    intent: Optional[IntentClassification]

    # Output
    response_text: Optional[str]
    ui_action: Optional[Dict[str, Any]]
    navigation: Optional[Dict[str, Any]]
    editor_content: Optional[Dict[str, Any]]
    confirmation: Optional[Dict[str, Any]]
    referenced_articles: List[Dict[str, Any]]

    # Control Flow
    is_final: bool
    requires_hitl: bool
    hitl_decision: Optional[str]
    error: Optional[str]
```

### 3.2 UserContext Fields

| Field | Description |
|-------|-------------|
| `user_id`, `name`, `email` | User identity |
| `scopes` | Authorization scopes (e.g., "macro:analyst") |
| `highest_role` | Highest role: admin > analyst > editor > reader |
| `topic_roles` | Role per topic (e.g., {"macro": "analyst"}) |
| `chat_tonality_text` | User's preferred chat communication style |
| `content_tonality_text` | User's preferred article writing style |

### 3.3 NavigationContext Fields

| Field | Description |
|-------|-------------|
| `section` | Current section: home, analyst, editor, admin, profile |
| `topic` | Current topic slug (if selected) |
| `role` | Current role context: reader, analyst, editor, admin |
| `article_id` | Current article being viewed/edited |
| `article_headline` | Current article headline |
| `article_status` | Article status: draft, editor, pending_approval, published |
| `sub_nav` | Sub-navigation state |
| `view_mode` | View mode (e.g., "list", "detail") |
| `admin_view` | Admin view type (for global admin) |

### 3.4 State Flow

```
Request Start
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  invoke_chat()                                               │
│  ├── Get singleton graph                                    │
│  ├── Create initial state with UserContext                  │
│  └── Generate thread_id for checkpointing                   │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  router_node                                                 │
│  ├── Classify intent using LLM                              │
│  ├── Set selected_agent and routing_reason                  │
│  └── Return to graph for conditional routing                │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  handler_node (ui_action, content_gen, editor, etc.)         │
│  ├── Check user permissions                                 │
│  ├── Process request based on intent                        │
│  ├── Set response_text, ui_action, etc.                     │
│  └── Return updated state                                   │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  response_builder_node                                       │
│  ├── Assemble final response from state fields              │
│  ├── Validate response structure                            │
│  └── Mark is_final = True                                   │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  Return ChatResponse                                         │
│  ├── Convert state to ChatResponse Pydantic model           │
│  └── Return to API layer                                    │
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
│            │ LangGraph checkpoint + interrupt        │        │      │
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

The system uses LangGraph's native checkpointing for human approval:

1. **Trigger**: When editor_workflow_node handles a publish request
2. **Checkpoint**: Workflow state is saved to Redis
3. **Response**: ChatResponse includes `confirmation` object with buttons
4. **Review**: Human reviews via web UI
5. **Resume**: `resume_chat(thread_id, decision, user_context)` continues workflow

```python
# Resume a paused workflow
from agents.graph import resume_chat

response = resume_chat(
    thread_id="chat_123_abc12345",
    hitl_decision="approve",  # or "reject"
    user_context=user_ctx,
)
```

### 5.3 Confirmation Response Structure

```python
class ConfirmationPrompt(BaseModel):
    id: str              # Unique confirmation ID
    type: str            # e.g., "publish_approval"
    title: str           # "Confirm Publication"
    message: str         # Explanation of what will happen
    article_id: int      # Related article
    confirm_label: str   # "Publish Now"
    cancel_label: str    # "Cancel"
    confirm_endpoint: str # API endpoint for confirmation
```

---

## 6. LangGraph Features

### 6.1 Features Used

| Feature | Usage | Benefit |
|---------|-------|---------|
| **Singleton Graph** | Graph compiled once at startup | Performance, consistency |
| **Conditional Edges** | Router decides which handler processes query | Dynamic workflow routing |
| **Checkpointing** | Save workflow state to Redis | Resume HITL workflows |
| **State Reducers** | Message accumulation with `operator.add` | Clean state management |
| **Pydantic Integration** | ChatResponse validation | Type-safe API responses |

### 6.2 Entry Points

| Function | Purpose |
|----------|---------|
| `invoke_chat()` | Synchronous chat processing |
| `ainvoke_chat()` | Async chat processing |
| `resume_chat()` | Resume paused HITL workflow |
| `get_graph()` | Get singleton graph instance |

### 6.3 Module Structure

```
backend/agents/
├── graph.py              # Singleton graph, invoke_chat(), resume_chat()
├── state.py              # Pydantic models, TypedDict schemas
├── nodes/                # Handler node implementations
│   ├── __init__.py
│   ├── router_node.py    # Intent classification
│   ├── ui_action_node.py # Navigation, UI triggers
│   ├── content_gen_node.py # Article writing
│   ├── editor_node.py    # Review, publish (HITL)
│   ├── general_chat_node.py # Q&A, search
│   ├── entitlements_node.py # Permission questions
│   └── response_builder.py # Final response assembly
├── analyst_agent.py      # Research workflows
├── editor_sub_agent.py   # Editorial sub-agent
└── ...                   # Other specialist agents
```

---

## Related Documentation

- [Authentication](./01-authentication.md) - OAuth and JWT system
- [Authorization](./02-authorization_concept.md) - Permissions and access control
- [User Management](./04-user-management.md) - User roles and groups
- [UI Actions](./14-ui-actions.md) - Frontend UI action handling
- [Unit Testing](./07-unit-testing.md) - Testing strategies

---

## Glossary

| Term | Definition |
|------|------------|
| **HITL** | Human-in-the-loop - requiring human approval for critical actions |
| **Scope** | Permission string in format `{topic}:{role}` |
| **Topic** | Content category (macro, equity, fixed_income, esg) |
| **Tonality** | Writing style/tone configuration for prompts |
| **Intent** | Classified user request type (ui_action, content_generation, etc.) |
| **Handler Node** | LangGraph node that processes a specific intent type |
| **Singleton Graph** | Single graph instance reused for all requests |
