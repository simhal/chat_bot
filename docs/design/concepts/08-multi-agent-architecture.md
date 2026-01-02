# Multi-Agent Architecture Design

**Version:** 1.0
**Status:** Draft
**Last Updated:** 2024-12-30

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Agent Hierarchy](#3-agent-hierarchy)
4. [State Management](#4-state-management)
5. [Permission Model](#5-permission-model)
6. [Tool Registry](#6-tool-registry)
7. [MCP Endpoint Specifications](#7-mcp-endpoint-specifications)
8. [Human-in-the-Loop Workflow](#8-human-in-the-loop-workflow)
9. [Data Models](#9-data-models)
10. [Implementation Guide](#10-implementation-guide)
11. [Migration Strategy](#11-migration-strategy)

---

## 1. Executive Summary

### 1.1 Purpose

This document describes the enhanced multi-agent architecture for the financial chatbot system. The new architecture introduces:

- **Permission-aware agents** with runtime tool filtering based on user scopes
- **Hierarchical sub-agent structure** for specialized workflows (research, analysis, editing)
- **Human-in-the-loop (HITL)** editorial workflow via webhooks for article publishing
- **Full MCP exposure** for all tools and prompts

### 1.2 Design Goals

| Goal | Description |
|------|-------------|
| **Security** | Tools filtered at runtime based on user's JWT scopes |
| **Flexibility** | Dynamic agent composition based on user role |
| **Traceability** | Full audit trail via workflow context |
| **Extensibility** | Easy addition of new agents and tools |
| **Human Oversight** | Critical actions (publishing) require human approval |

### 1.3 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tool Access Control | Runtime filtering | All tools registered, filtered per-request based on scopes |
| Resource Creation | Auto-create and attach | Research agent automatically creates DRAFT resources |
| Editor Approval | Webhook/callback | Async notification allows human review via web UI |
| State Management | Enhanced TypedDict | Maintains LangGraph compatibility |

---

## 1.4 LangGraph Features Showcase

This architecture demonstrates several advanced LangGraph capabilities:

| Feature | Usage | Benefit |
|---------|-------|---------|
| **Conditional Edges** | Router decides which agent handles query | Dynamic workflow routing |
| **Subgraph Composition** | AnalystAgent contains nested WebSearch/DataDownload graphs | Modular, reusable components |
| **Human-in-the-Loop** | `interrupt_before` for publish approval | Native HITL without webhooks |
| **Parallel Execution** | Research agents run in parallel | Faster data gathering |
| **Checkpointing** | Save workflow state to Redis | Resume interrupted workflows |
| **Streaming** | Stream intermediate agent outputs | Real-time UI updates |
| **Tool Calling** | ReAct pattern with structured tools | Reliable tool execution |
| **State Reducers** | `operator.add` for message accumulation | Clean state management |

### LangGraph Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        LANGGRAPH WORKFLOW                                │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                         StateGraph                                │   │
│  │                                                                   │   │
│  │    START                                                          │   │
│  │      │                                                            │   │
│  │      ▼                                                            │   │
│  │  ┌────────┐                                                       │   │
│  │  │ Router │ ─────────────────────────────────────────────────┐   │   │
│  │  └────┬───┘                                                   │   │   │
│  │       │                                                       │   │   │
│  │       │ Conditional Edges                                     │   │   │
│  │       │                                                       │   │   │
│  │  ┌────┴─────┬──────────────┬──────────────┐                  │   │   │
│  │  │          │              │              │                   │   │   │
│  │  ▼          ▼              ▼              ▼                   │   │   │
│  │ ┌────┐  ┌────────┐  ┌──────────┐  ┌──────────┐              │   │   │
│  │ │Read│  │Analyst │  │  Editor  │  │ General  │              │   │   │
│  │ │    │  │        │  │          │  │          │              │   │   │
│  │ └──┬─┘  └────┬───┘  └────┬─────┘  └────┬─────┘              │   │   │
│  │    │         │           │             │                     │   │   │
│  │    │         │           │             │                     │   │   │
│  │    │    ┌────┴────┐      │             │                     │   │   │
│  │    │    │ SUBGRAPH│      │             │                     │   │   │
│  │    │    │         │      │             │                     │   │   │
│  │    │    │ ┌─────┐ │      │             │                     │   │   │
│  │    │    │ │Web  │ │      │             │                     │   │   │
│  │    │    │ │Search│─┼──┐  │             │                     │   │   │
│  │    │    │ └─────┘ │  │  │             │                     │   │   │
│  │    │    │ ┌─────┐ │  │  │             │                     │   │   │
│  │    │    │ │Data │ │  │  │             │                     │   │   │
│  │    │    │ │Down │─┼──┤  │             │                     │   │   │
│  │    │    │ └─────┘ │  │  │             │                     │   │   │
│  │    │    │ ┌─────┐ │  │  │             │                     │   │   │
│  │    │    │ │Resrc│ │  │  │             │                     │   │   │
│  │    │    │ │Query│─┼──┤  │             │                     │   │   │
│  │    │    │ └─────┘ │  │  │             │                     │   │   │
│  │    │    │         │  │  │             │                     │   │   │
│  │    │    │   ▼     │  │  │             │                     │   │   │
│  │    │    │ ┌─────┐ │  │  │             │                     │   │   │
│  │    │    │ │Write│◄┼──┘  │             │                     │   │   │
│  │    │    │ │Artcl│ │     │             │                     │   │   │
│  │    │    │ └─────┘ │     │             │                     │   │   │
│  │    │    └────┬────┘     │             │                     │   │   │
│  │    │         │          │             │                     │   │   │
│  │    │         │     ┌────┴────┐        │                     │   │   │
│  │    │         │     │INTERRUPT│        │                     │   │   │
│  │    │         │     │ BEFORE  │        │                     │   │   │
│  │    │         │     │(publish)│        │                     │   │   │
│  │    │         │     └────┬────┘        │                     │   │   │
│  │    │         │          │             │                     │   │   │
│  │    └─────────┴──────────┴─────────────┘                     │   │   │
│  │                         │                                    │   │   │
│  │                         ▼                                    │   │   │
│  │                       END                                    │   │   │
│  │                                                              │   │   │
│  └──────────────────────────────────────────────────────────────┘   │   │
│                                                                      │   │
│  Features Used:                                                      │   │
│  ├── StateGraph with TypedDict state                                │   │
│  ├── add_conditional_edges() for routing                            │   │
│  ├── Subgraph composition for AnalystAgent                          │   │
│  ├── Parallel node execution (Web + Data + Resource)                │   │
│  ├── interrupt_before() for HITL publish                            │   │
│  ├── MemorySaver/RedisSaver for checkpointing                       │   │
│  └── astream_events() for streaming                                 │   │
│                                                                      │   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key LangGraph Code Patterns

**1. Conditional Routing:**
```python
workflow.add_conditional_edges(
    "router",
    route_by_intent_and_permission,
    {
        "read": "article_query",
        "research": "analyst",
        "edit": "editor",
        "general": "general_chat"
    }
)
```

**2. Subgraph Composition:**
```python
# Analyst subgraph with parallel research
analyst_graph = StateGraph(AnalystState)
analyst_graph.add_node("web_search", web_search_agent)
analyst_graph.add_node("data_download", data_download_agent)
analyst_graph.add_node("resource_query", resource_query_agent)
analyst_graph.add_node("write_article", write_article_node)

# Parallel execution: all three search nodes run simultaneously
analyst_graph.add_edge(START, "web_search")
analyst_graph.add_edge(START, "data_download")
analyst_graph.add_edge(START, "resource_query")
analyst_graph.add_edge(["web_search", "data_download", "resource_query"], "write_article")

# Embed as subgraph in main workflow
main_workflow.add_node("analyst", analyst_graph.compile())
```

**3. Human-in-the-Loop Interrupt:**
```python
# Interrupt before publish for human approval
workflow.add_node("publish", publish_article)
graph = workflow.compile(
    checkpointer=RedisSaver(redis_client),
    interrupt_before=["publish"]  # Pause here for human approval
)

# Resume after approval
result = graph.invoke(
    None,  # Resume with same state
    config={"configurable": {"thread_id": thread_id}}
)
```

**4. Streaming with Events:**
```python
async for event in graph.astream_events(
    initial_state,
    config={"configurable": {"thread_id": thread_id}},
    version="v2"
):
    if event["event"] == "on_chat_model_stream":
        # Stream tokens to client
        yield event["data"]["chunk"].content
    elif event["event"] == "on_tool_end":
        # Notify tool completion
        yield f"Tool {event['name']} completed"
```

**5. Checkpointing for Resume:**
```python
from langgraph.checkpoint.redis import RedisSaver

checkpointer = RedisSaver(redis_url="redis://localhost:6379")
graph = workflow.compile(checkpointer=checkpointer)

# First run (may be interrupted)
result = graph.invoke(state, config={"configurable": {"thread_id": "user_123"}})

# Later: resume from checkpoint
result = graph.invoke(None, config={"configurable": {"thread_id": "user_123"}})
```

---

## 1.5 Celery Background Task Architecture

Heavy agent workflows run in Celery workers to avoid blocking the chat API:

| Agent | Execution | Reason |
|-------|-----------|--------|
| **MainChatAgent** | Synchronous (FastAPI) | Quick response needed |
| **ArticleQueryAgent** | Celery Worker | Used by AnalystAgent for article creation |
| **AnalystAgent** | Celery Worker | Heavy research, minutes |
| **WebSearchAgent** | Celery Worker | External API calls |
| **DataDownloadAgent** | Celery Worker | External API calls |
| **EditorSubAgent** | Celery Worker | HITL workflow, async |

### Demo Configuration

For resource-efficient demo deployment, a single Celery worker handles all queues:

```bash
# Single worker (demo - resource efficient)
celery -A celery_app worker -Q analyst,research,websearch,datadownload,articles,editor -l info --concurrency=2

# Production: separate workers per queue type
# celery -A celery_app worker -Q analyst -l info --concurrency=2
# celery -A celery_app worker -Q research,websearch,datadownload,articles -l info --concurrency=4
# celery -A celery_app worker -Q editor -l info --concurrency=2
```

### Celery Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CELERY TASK FLOW                                  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      FastAPI (Synchronous)                        │   │
│  │                                                                   │   │
│  │  User Request                                                     │   │
│  │       │                                                           │   │
│  │       ▼                                                           │   │
│  │  ┌──────────────┐     ┌─────────────────┐                        │   │
│  │  │ MainChat     │────▶│ ArticleQuery    │──▶ Response            │   │
│  │  │ Agent        │     │ Agent           │    (immediate)          │   │
│  │  └──────┬───────┘     └─────────────────┘                        │   │
│  │         │                                                         │   │
│  │         │ If research/analysis needed                            │   │
│  │         ▼                                                         │   │
│  │  ┌──────────────┐                                                │   │
│  │  │ Celery       │──────────────────────────────────────┐         │   │
│  │  │ task.delay() │                                       │         │   │
│  │  └──────────────┘                                       │         │   │
│  │         │                                               │         │   │
│  │         │ Return task_id                                │         │   │
│  │         ▼                                               │         │   │
│  │  ┌──────────────┐                                       │         │   │
│  │  │ Response:    │                                       │         │   │
│  │  │ "Research    │                                       │         │   │
│  │  │  started..." │                                       │         │   │
│  │  │ task_id: xxx │                                       │         │   │
│  │  └──────────────┘                                       │         │   │
│  │                                                          │         │   │
│  └──────────────────────────────────────────────────────────┼─────────┘   │
│                                                              │             │
│  ┌──────────────────────────────────────────────────────────┼─────────┐   │
│  │                    Redis (Message Broker)                 │         │   │
│  │                                                           │         │   │
│  │  Queue: agent_tasks                                       │         │   │
│  │  ┌─────────────────────────────────────────────────────┐ │         │   │
│  │  │ {task_id, user_id, agent_type, params, state}       │◀┘         │   │
│  │  └─────────────────────────────────────────────────────┘           │   │
│  │                          │                                          │   │
│  └──────────────────────────┼──────────────────────────────────────────┘   │
│                              │                                              │
│  ┌──────────────────────────┼──────────────────────────────────────────┐   │
│  │                    Celery Workers                                    │   │
│  │                          │                                           │   │
│  │                          ▼                                           │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │                    AnalystAgent Task                         │    │   │
│  │  │                                                              │    │   │
│  │  │  ┌────────────┐  ┌────────────┐  ┌────────────┐             │    │   │
│  │  │  │WebSearch   │  │DataDownload│  │ResourceQry │             │    │   │
│  │  │  │Agent       │  │Agent       │  │Agent       │             │    │   │
│  │  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘             │    │   │
│  │  │        │               │               │                     │    │   │
│  │  │        └───────────────┼───────────────┘                     │    │   │
│  │  │                        ▼                                     │    │   │
│  │  │                ┌───────────────┐                             │    │   │
│  │  │                │ Create        │                             │    │   │
│  │  │                │ Resources &   │                             │    │   │
│  │  │                │ Write Article │                             │    │   │
│  │  │                └───────┬───────┘                             │    │   │
│  │  │                        │                                     │    │   │
│  │  └────────────────────────┼─────────────────────────────────────┘    │   │
│  │                           │                                          │   │
│  │  ┌────────────────────────┼─────────────────────────────────────┐    │   │
│  │  │                EditorSubAgent Task                            │    │   │
│  │  │                        │                                      │    │   │
│  │  │                        ▼                                      │    │   │
│  │  │              ┌──────────────────┐                             │    │   │
│  │  │              │ interrupt_before │                             │    │   │
│  │  │              │ (HITL approval)  │                             │    │   │
│  │  │              └────────┬─────────┘                             │    │   │
│  │  │                       │                                       │    │   │
│  │  └───────────────────────┼───────────────────────────────────────┘    │   │
│  │                          │                                            │   │
│  └──────────────────────────┼────────────────────────────────────────────┘   │
│                              │                                                │
│  ┌──────────────────────────┼────────────────────────────────────────────┐   │
│  │                    Notification System                                 │   │
│  │                          │                                             │   │
│  │                          ▼                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────┐      │   │
│  │  │ On task completion:                                          │      │   │
│  │  │  - Update task status in Redis                               │      │   │
│  │  │  - Send WebSocket notification to user                       │      │   │
│  │  │  - Store result in database                                  │      │   │
│  │  │  - Trigger webhook (if HITL)                                 │      │   │
│  │  └─────────────────────────────────────────────────────────────┘      │   │
│  │                                                                        │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Celery Task Types

```python
# backend/tasks/agent_tasks.py

from celery import Celery, Task
from celery.result import AsyncResult

celery_app = Celery(
    "agent_tasks",
    broker="redis://localhost:6379/1",
    backend="redis://localhost:6379/2"
)

# Task routing by agent type
celery_app.conf.task_routes = {
    "tasks.analyst_task": {"queue": "analyst"},
    "tasks.research_task": {"queue": "research"},
    "tasks.editor_task": {"queue": "editor"},
}

# Separate worker pools for different workloads
# celery -A tasks worker -Q analyst --concurrency=2
# celery -A tasks worker -Q research --concurrency=4
# celery -A tasks worker -Q editor --concurrency=1


@celery_app.task(bind=True, max_retries=3)
def analyst_research_task(
    self,
    user_id: int,
    topic: str,
    query: str,
    article_id: Optional[int] = None
) -> dict:
    """
    Run AnalystAgent research workflow in background.

    Returns:
        {
            "status": "completed",
            "article_id": 123,
            "resources_created": [1, 2, 3],
            "content_preview": "..."
        }
    """
    from agents.analyst_agent import AnalystAgent
    from services.user_context_service import UserContextService

    # Build context
    user_context = UserContextService.build_from_id(user_id)

    # Run agent
    agent = AnalystAgent(topic, llm, db)
    result = agent.research_and_write(query, article_id, user_context)

    # Notify user via WebSocket
    notify_user(user_id, {
        "type": "task_complete",
        "task_id": self.request.id,
        "result": result
    })

    return result


@celery_app.task(bind=True)
def editor_publish_task(
    self,
    user_id: int,
    article_id: int
) -> dict:
    """
    Run EditorSubAgent publish workflow with HITL.
    Uses LangGraph interrupt_before for approval.
    """
    from agents.editor_sub_agent import EditorSubAgent

    agent = EditorSubAgent(topic, llm, db)

    # This will pause at interrupt_before("publish")
    # State is checkpointed to Redis
    result = agent.submit_for_approval(article_id, user_context)

    if result.get("status") == "awaiting_approval":
        # Task pauses here - will be resumed by approval endpoint
        return {
            "status": "awaiting_approval",
            "thread_id": result["thread_id"],
            "article_id": article_id
        }

    return result
```

### API Integration with Celery

```python
# backend/api/chat.py

@router.post("/api/chat")
async def chat(
    message: ChatMessage,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Main chat endpoint.
    Quick queries → synchronous response
    Research queries → Celery task + task_id
    """
    user_context = UserContextService.build(user, db)

    # MainChatAgent routes the query
    main_agent = MainChatAgent(llm, db)
    routing = main_agent.route_query(message.message, user_context)

    if routing["agent"] in ["general", "article_query"]:
        # Synchronous - quick response
        result = main_agent.process_sync(message.message, user_context)
        return ChatResponse(
            response=result["response"],
            agent_type=routing["agent"]
        )

    elif routing["agent"] == "analyst":
        # Async - start Celery task
        task = analyst_research_task.delay(
            user_id=user_context["user_id"],
            topic=routing["topic"],
            query=message.message
        )
        return ChatResponse(
            response=f"I'm starting research on this topic. I'll notify you when it's ready.",
            agent_type="analyst",
            task_id=task.id,
            status="processing"
        )

    elif routing["agent"] == "editor":
        # Async - start editor workflow
        task = editor_publish_task.delay(
            user_id=user_context["user_id"],
            article_id=routing["article_id"]
        )
        return ChatResponse(
            response=f"Starting the editorial review process.",
            agent_type="editor",
            task_id=task.id,
            status="processing"
        )


@router.get("/api/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    user: dict = Depends(get_current_user)
):
    """Check status of background agent task."""
    result = AsyncResult(task_id)

    return {
        "task_id": task_id,
        "status": result.status,  # PENDING, STARTED, SUCCESS, FAILURE
        "result": result.result if result.ready() else None
    }
```

### WebSocket Notifications

```python
# backend/api/websocket.py

from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    async def notify_user(self, user_id: int, message: dict):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(message)

manager = ConnectionManager()

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(user_id, websocket)
    try:
        while True:
            # Keep connection alive, receive any client messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        del manager.active_connections[user_id]


# Called from Celery tasks
def notify_user(user_id: int, message: dict):
    """Notify user of task completion via WebSocket."""
    import asyncio
    asyncio.run(manager.notify_user(user_id, message))
```

---

## 2. Architecture Overview

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  Web UI     │  │  MCP Client │  │  API Client │  │  CLI Tool   │    │
│  │  + WebSocket│  │             │  │             │  │             │    │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │
└─────────┼────────────────┼────────────────┼────────────────┼────────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           API LAYER                                      │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌───────────────┐   │
│  │  /mcp               │  │  /api/tools/*       │  │  /ws/{user}   │   │
│  │  (fastapi-mcp)      │  │  (REST endpoints)   │  │  (WebSocket)  │   │
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

---

### 2.2 Updated Component Summary

| Component | Execution | Queue | Concurrency |
|-----------|-----------|-------|-------------|
| MainChatAgent | Sync (FastAPI) | - | Thread pool |
| ArticleQueryAgent | Celery | `articles` | 2 workers* |
| AnalystAgent | Celery | `analyst` | 2 workers* |
| WebSearchAgent | Celery | `research` | 2 workers* |
| DataDownloadAgent | Celery | `research` | 2 workers* |
| EditorSubAgent | Celery | `editor` | 2 workers* |

*Demo mode: Single worker (concurrency=2) handles all queues for resource efficiency.

---

## 2.3 Original Architecture (reference)
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────┐      │
│  │                      MainChatAgent                             │      │
│  │  - UserContext injection                                       │      │
│  │  - Dynamic tonality composition                                │      │
│  │  - Permission-aware routing                                    │      │
│  │  - Tool filtering based on scopes                              │      │
│  └───────────────────────────────┬───────────────────────────────┘      │
│                                  │                                       │
│          ┌───────────────────────┼───────────────────────┐              │
│          │                       │                       │              │
│          ▼                       ▼                       ▼              │
│  ┌───────────────┐     ┌─────────────────┐     ┌─────────────────┐     │
│  │ ArticleQuery  │     │  AnalystAgent   │     │ EditorSubAgent  │     │
│  │    Agent      │     │                 │     │                 │     │
│  │  (reader+)    │     │  (analyst+)     │     │  (editor+)      │     │
│  ├───────────────┤     ├─────────────────┤     ├─────────────────┤     │
│  │ search        │     │ ┌─────────────┐ │     │ review          │     │
│  │ get           │     │ │ResourceQuery│ │     │ request_changes │     │
│  │ create_draft  │     │ └─────────────┘ │     │ publish (HITL)  │     │
│  │ write         │     │ ┌─────────────┐ │     └────────┬────────┘     │
│  └───────────────┘     │ │ResearchSub  │ │              │              │
│                        │ │   Agent     │ │              ▼              │
│                        │ └─────────────┘ │     ┌─────────────────┐     │
│                        │ ┌─────────────┐ │     │ Webhook Service │     │
│                        │ │ArticleQuery │ │     └────────┬────────┘     │
│                        │ └─────────────┘ │              │              │
│                        └─────────────────┘              │              │
└─────────────────────────────────────────────────────────┼──────────────┘
                                                          │
                                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       EXTERNAL SYSTEMS                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                      │
│  │ Human Editor│  │  Slack/     │  │  Email      │                      │
│  │  (Web UI)   │  │  Teams      │  │  System     │                      │
│  └──────┬──────┘  └─────────────┘  └─────────────┘                      │
│         │                                                                │
│         ▼                                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  /api/approvals/{article_id}  (Approval Callback)               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                        REQUEST FLOW                                   │
└──────────────────────────────────────────────────────────────────────┘

1. Client Request
   │
   ▼
2. JWT Validation → Extract User Scopes
   │
   ▼
3. Build UserContext
   │  ├── user_id, name, email
   │  ├── scopes: ["macro:analyst", "equity:reader", ...]
   │  ├── chat_tonality_text (from user preferences)
   │  └── content_tonality_text
   │
   ▼
4. Initialize AgentState
   │  ├── messages: [conversation history]
   │  ├── user_context: UserContext
   │  ├── workflow_context: None (or existing)
   │  └── available_tools: filtered by scopes
   │
   ▼
5. MainChatAgent.process()
   │  ├── Build dynamic system prompt (with tonality)
   │  ├── Filter tools for user
   │  ├── Route to sub-agent OR handle directly
   │  └── Return response
   │
   ▼
6. Response with metadata
   │  ├── response: str
   │  ├── agent_type: str
   │  ├── tools_used: List[str]
   │  └── workflow_state: Optional[WorkflowContext]
```

---

## 3. Agent Hierarchy

### 3.1 Agent Composition

```
MainChatAgent (Orchestrator)
│
├── Owns: ToolRegistry (filtered view)
├── Owns: PromptComposer (dynamic tonality)
├── Owns: UserContext (scopes, preferences)
│
├── Direct Sub-Agents (for readers):
│   │
│   └── ArticleQueryAgent [per topic] ─────────────────────────────────┐
│       ├── Required Role: reader                                       │
│       ├── Topic Scoped: Yes                                          │
│       ├── Purpose: Search and read articles (delivered to user)      │
│       └── Tools:                                                      │
│           ├── search_articles (reader+)                              │
│           └── get_article (reader+)                                  │
│                                                                       │
├── AnalystAgent [per topic] ◄──────────────────────────────────────────┘
│   │                        (can also query articles via ArticleQueryAgent)
│   ├── Required Role: analyst
│   ├── Topic Scoped: Yes
│   ├── Purpose: Research workflows, create articles with resources
│   │
│   ├── Composes Multiple Query Agents:
│   │   │
│   │   ├── ArticleQueryAgent ─────────────────────────────────────────┐
│   │   │   ├── Purpose: Create/write articles                         │
│   │   │   └── Tools:                                                 │
│   │   │       ├── create_draft_article (analyst+)                    │
│   │   │       └── write_article_content (analyst+)                   │
│   │   │                                                              │
│   │   ├── ResourceQueryAgent ────────────────────────────────────────┤
│   │   │   ├── Purpose: Find existing resources in ChromaDB           │
│   │   │   └── Tools:                                                 │
│   │   │       ├── search_text_resources                              │
│   │   │       ├── search_table_resources                             │
│   │   │       └── search_all_resources                               │
│   │   │                                                              │
│   │   ├── WebSearchAgent ────────────────────────────────────────────┤
│   │   │   ├── Purpose: Search web for current information            │
│   │   │   └── Tools:                                                 │
│   │   │       ├── web_search (DuckDuckGo/Google)                     │
│   │   │       ├── search_news                                        │
│   │   │       └── search_financial_news                              │
│   │   │                                                              │
│   │   └── DataDownloadAgent ─────────────────────────────────────────┤
│   │       ├── Purpose: Fetch structured data from APIs               │
│   │       └── Tools:                                                 │
│   │           ├── fetch_stock_data (yfinance)                        │
│   │           ├── fetch_economic_data (FRED/mock)                    │
│   │           ├── fetch_fx_rates                                     │
│   │           ├── fetch_treasury_yields                              │
│   │           └── download_pdf                                       │
│   │                                                                  │
│   └── Resource Creation (can create from any sub-agent results):     │
│       ├── create_text_resource                                       │
│       ├── create_table_resource                                      │
│       └── attach_resource_to_article                                 │
│                                                                      │
└── EditorSubAgent [per topic] ◄───────────────────────────────────────┘
    │                          (reviews articles created by analysts)
    ├── Required Role: editor
    ├── Topic Scoped: Yes
    ├── Purpose: Editorial review and publishing with HITL
    └── Tools:
        ├── review_article
        ├── request_changes (returns to DRAFT)
        ├── submit_for_approval (triggers webhook)
        └── approve_publish (HITL callback)
```

### 3.1.1 Agent Relationships

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER REQUEST                                     │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        MainChatAgent                                     │
│                                                                          │
│  1. Load UserContext (scopes determine available agents/tools)          │
│  2. Route query based on intent + permissions                           │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │  If user is reader:                                             │     │
│  │    → ArticleQueryAgent.search() → Return articles to user       │     │
│  │                                                                  │     │
│  │  If user is analyst + "research" intent:                        │     │
│  │    → AnalystAgent.research_and_write()                          │     │
│  │       ├── WebSearchAgent.search()                               │     │
│  │       ├── DataDownloadAgent.fetch()                             │     │
│  │       ├── ResourceQueryAgent.find_existing()                    │     │
│  │       ├── Create resources from results                         │     │
│  │       └── ArticleQueryAgent.create_and_write()                  │     │
│  │                                                                  │     │
│  │  If user is editor + "publish" intent:                          │     │
│  │    → EditorSubAgent.submit_for_approval() → HITL webhook        │     │
│  └────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Agent Responsibilities

#### MainChatAgent

**Purpose:** Primary orchestrator that leads all user conversations.

**Responsibilities:**
- Load and inject UserContext from JWT
- Compose dynamic system prompt with user's tonality preference
- Route queries to appropriate sub-agents based on intent and permissions
- Handle general conversation directly
- Maintain conversation memory

**Key Methods:**
```python
class MainChatAgent:
    async def process(self, state: AgentState) -> AgentState:
        """Main entry point for all user messages."""

    def _build_system_prompt(self, user_context: UserContext) -> str:
        """Compose prompt with base + topic + tonality + constraints."""

    async def _route_query(self, state: AgentState) -> RoutingDecision:
        """Determine which sub-agent should handle the query."""

    def _get_available_tools(self, user_context: UserContext) -> List[BaseTool]:
        """Filter tools based on user's scopes."""
```

#### ArticleQueryAgent

**Purpose:** Manage article search and creation for a specific topic.

**Responsibilities:**
- Search existing articles using semantic and keyword search
- Retrieve full article content
- Create new draft articles (analyst+)
- Write/update article content using resources (analyst+)

**Key Methods:**
```python
class ArticleQueryAgent:
    def __init__(self, topic: str, llm: ChatOpenAI, db: Session):
        self.topic = topic

    async def search_articles(self, query: str, limit: int = 10) -> List[Dict]:
        """Semantic + keyword search for articles in topic."""

    async def create_draft(self, headline: str) -> Dict:
        """Create empty draft article template."""

    async def write_content(
        self,
        article_id: int,
        content: str,
        resource_ids: List[int]
    ) -> Dict:
        """Write content to article, linking specified resources."""
```

#### AnalystAgent

**Purpose:** Orchestrate research and article writing workflows.

**Responsibilities:**
- Coordinate ResourceQueryAgent for finding existing resources
- Invoke ResearchSubAgent when more resources needed
- Delegate to ArticleQueryAgent for article operations
- Manage workflow state (current article, pending resources)

**Key Methods:**
```python
class AnalystAgent:
    def __init__(self, topic: str, llm: ChatOpenAI, db: Session):
        self.resource_query = ResourceQueryAgent(llm, db, topic)
        self.research_agent = ResearchSubAgent(topic, llm, db)
        self.article_agent = ArticleQueryAgent(topic, llm, db)

    async def research_and_write(
        self,
        query: str,
        article_id: Optional[int] = None
    ) -> Dict:
        """Full workflow: research → create resources → write article."""
```

#### ResearchSubAgent

**Purpose:** Create new resources when existing ones are insufficient.

**Responsibilities:**
- Perform web searches for current information
- Fetch economic/equity data from APIs
- Process PDFs into text/table resources
- Auto-create resources with DRAFT status
- Auto-attach resources to current article in workflow

**Key Methods:**
```python
class ResearchSubAgent:
    async def research(self, query: str, workflow: WorkflowContext) -> List[int]:
        """Research query and create resources. Returns resource IDs."""

    async def create_resource_with_auto_attach(
        self,
        resource_data: Dict,
        workflow: WorkflowContext
    ) -> int:
        """Create resource and attach to current article."""
```

#### EditorSubAgent

**Purpose:** Manage editorial review and publishing workflow with HITL.

**Responsibilities:**
- Review articles in EDITOR status
- Request changes (return to DRAFT)
- Submit for human approval (triggers webhook)
- Process approval callbacks

**Key Methods:**
```python
class EditorSubAgent:
    async def submit_for_approval(
        self,
        article_id: int,
        state: AgentState
    ) -> AgentState:
        """Submit article for human approval via webhook."""

    async def process_approval(
        self,
        article_id: int,
        approved: bool,
        notes: Optional[str]
    ) -> Dict:
        """Handle approval callback from human editor."""
```

---

## 4. State Management

### 4.1 State Schema

```python
from typing import TypedDict, List, Literal, Optional, Annotated, Dict, Any
from langchain_core.messages import BaseMessage
import operator


class UserContext(TypedDict):
    """
    Runtime user context loaded from JWT and database.
    Available to all agents and tools.
    """
    # Identity
    user_id: int
    name: str
    email: str

    # Authorization
    scopes: List[str]  # ["macro:analyst", "equity:reader", "global:admin"]
    role: str  # Highest role: admin > analyst > editor > reader

    # Preferences
    selected_chat_tonality_id: Optional[int]
    selected_content_tonality_id: Optional[int]
    chat_tonality_text: Optional[str]  # Actual tonality prompt text
    content_tonality_text: Optional[str]


class WorkflowContext(TypedDict):
    """
    Context for multi-step workflows (research, article creation, editing).
    Persisted across multiple agent invocations.
    """
    # Current workflow
    workflow_id: str  # UUID for tracking
    workflow_type: Literal["research", "write", "edit", "publish"]
    started_at: str  # ISO timestamp

    # Article context
    current_article_id: Optional[int]
    current_topic: Optional[str]

    # Resource tracking
    pending_resources: List[int]  # Resource IDs created during workflow
    attached_resources: List[int]  # Resources linked to article

    # HITL state
    approval_pending: bool
    approval_request_id: Optional[int]
    approval_callback_url: Optional[str]


class AgentState(TypedDict):
    """
    Enhanced state for permission-aware multi-agent system.
    Compatible with LangGraph StateGraph.
    """
    # === Message History ===
    # Uses operator.add for accumulation (appends, doesn't replace)
    messages: Annotated[List[BaseMessage], operator.add]

    # === User Context ===
    # Loaded once at request start, immutable during request
    user_context: UserContext

    # === Agent Routing ===
    selected_agent: Optional[str]  # Topic slug or "general"
    routing_reason: Optional[str]  # Why this agent was selected

    # === Workflow State ===
    # Tracks multi-step operations
    workflow_context: Optional[WorkflowContext]

    # === Tool Execution ===
    # Results from tool calls for audit/debugging
    tool_results: Dict[str, Any]
    last_tool_call: Optional[str]

    # === Available Tools ===
    # Filtered list of tool names based on user permissions
    available_tools: List[str]

    # === Control Flow ===
    iterations: int
    max_iterations: int  # Default: 10
    is_final: bool

    # === Error Handling ===
    last_error: Optional[str]
    error_count: int
```

### 4.2 State Initialization

```python
def create_initial_state(
    user: dict,  # From JWT
    message: str,
    db: Session
) -> AgentState:
    """Create initial state for a new request."""

    # Build UserContext from JWT and database
    user_context = UserContextService.build(user, db)

    # Filter available tools
    available_tools = ToolRegistry.get_tool_names_for_user(
        user_context['scopes']
    )

    # Load conversation history
    memory = create_conversation_memory(user_context['user_id'])
    history = memory.messages

    return AgentState(
        messages=history + [HumanMessage(content=message)],
        user_context=user_context,
        selected_agent=None,
        routing_reason=None,
        workflow_context=None,
        tool_results={},
        last_tool_call=None,
        available_tools=available_tools,
        iterations=0,
        max_iterations=10,
        is_final=False,
        last_error=None,
        error_count=0
    )
```

### 4.3 State Flow

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
│  ├── state.iterations += 1                                  │
│  ├── state.selected_agent = route_query()                   │
│  └── delegate to sub-agent OR handle direct                 │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  Sub-Agent.process(state)                                    │
│  ├── Check has_permission(state.user_context)               │
│  ├── Get tools: get_available_tools(state.user_context)     │
│  ├── Execute tools, update state.tool_results               │
│  ├── Update state.workflow_context if workflow              │
│  └── Append AI message to state.messages                    │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  state.is_final = True                                       │
│  Save to conversation memory                                 │
│  Return response                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Permission Model

### 5.1 Role Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                      ROLE HIERARCHY                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  global:admin ──────────────────────────────────────────┐   │
│       │                                                  │   │
│       │  (Full access to all topics and tools)          │   │
│       │                                                  │   │
│       ▼                                                  │   │
│  {topic}:admin ─────────────────────────────────────┐   │   │
│       │                                              │   │   │
│       │  (Full access within topic)                  │   │   │
│       │                                              │   │   │
│       ▼                                              │   │   │
│  {topic}:analyst ───────────────────────────────┐   │   │   │
│       │                                          │   │   │   │
│       │  (Create articles, resources, research)  │   │   │   │
│       │                                          │   │   │   │
│       ▼                                          │   │   │   │
│  {topic}:editor ────────────────────────────┐   │   │   │   │
│       │                                      │   │   │   │   │
│       │  (Edit articles, publish with HITL)  │   │   │   │   │
│       │                                      │   │   │   │   │
│       ▼                                      │   │   │   │   │
│  {topic}:reader ────────────────────────┐   │   │   │   │   │
│       │                                  │   │   │   │   │   │
│       │  (Read articles, search)         │   │   │   │   │   │
│       │                                  │   │   │   │   │   │
│       ▼                                  ▼   ▼   ▼   ▼   ▼   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    NO ACCESS                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘

Role Levels:
  admin    = 4
  analyst  = 3
  editor   = 2
  reader   = 1
  none     = 0
```

### 5.2 Scope Format

```
Scope Format: {groupname}:{role}

Examples:
  - global:admin     → System administrator (all access)
  - macro:analyst    → Macro topic analyst
  - equity:reader    → Equity topic reader
  - fixed_income:editor → Fixed income topic editor

Multiple Scopes:
  A user can have multiple scopes:
  ["macro:analyst", "equity:reader", "fixed_income:editor"]

  This means:
  - Analyst access to macro topic (create/write articles)
  - Reader access to equity topic (search/read only)
  - Editor access to fixed_income topic (edit/publish)
```

### 5.3 Permission Checking Algorithm

```python
def check_permission(
    user_scopes: List[str],
    required_role: str,
    topic: Optional[str] = None,
    global_admin_override: bool = True
) -> bool:
    """
    Check if user has required permission.

    Args:
        user_scopes: User's scopes from JWT
        required_role: Minimum role required (reader, editor, analyst, admin)
        topic: Optional topic for topic-scoped permissions
        global_admin_override: If True, global:admin bypasses all checks

    Returns:
        True if user has permission
    """
    ROLE_LEVELS = {"admin": 4, "analyst": 3, "editor": 2, "reader": 1}
    required_level = ROLE_LEVELS.get(required_role, 0)

    # Global admin override
    if global_admin_override and "global:admin" in user_scopes:
        return True

    # Topic-scoped check
    if topic:
        for scope in user_scopes:
            parts = scope.split(":")
            if len(parts) == 2:
                scope_group, scope_role = parts
                if scope_group == topic or scope_group == "global":
                    scope_level = ROLE_LEVELS.get(scope_role, 0)
                    if scope_level >= required_level:
                        return True
        return False

    # Non-topic-scoped: check highest role across all scopes
    max_level = 0
    for scope in user_scopes:
        parts = scope.split(":")
        if len(parts) == 2:
            role = parts[1]
            level = ROLE_LEVELS.get(role, 0)
            max_level = max(max_level, level)

    return max_level >= required_level
```

### 5.4 Permission Matrix

| Operation | Required Role | Topic Scoped | Global Admin Override |
|-----------|---------------|--------------|----------------------|
| Search articles | reader | Yes | Yes |
| Get article | reader | No | Yes |
| Search resources | reader | No | Yes |
| Get tonalities | reader | No | Yes |
| Create draft article | analyst | Yes | Yes |
| Write article content | analyst | Yes | Yes |
| Create text resource | analyst | Yes | Yes |
| Create table resource | analyst | Yes | Yes |
| Attach resource | analyst | Yes | Yes |
| Web search | analyst | No | Yes |
| Submit for review | analyst | Yes | Yes |
| Request changes | editor | Yes | Yes |
| Publish article (HITL) | editor | Yes | Yes |
| Approve publish | editor | Yes | Yes |
| Get topic prompts | admin | Yes | Yes |
| Edit prompts | admin | Yes | No |

---

## 6. Tool Registry

### 6.1 Tool Permission Metadata

```python
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ToolPermission:
    """Permission requirements for a tool."""

    required_role: str  # Minimum role: reader, editor, analyst, admin
    topic_scoped: bool  # If True, requires topic-specific permission
    global_admin_override: bool = True  # If True, global:admin can always use
    requires_hitl: bool = False  # If True, triggers human-in-the-loop

    # Optional: specific scopes that can use this tool
    # If None, uses role hierarchy check
    allowed_scopes: Optional[List[str]] = None


# Tool permission definitions
TOOL_PERMISSIONS = {
    # Reader tools
    "search_articles": ToolPermission(
        required_role="reader",
        topic_scoped=True
    ),
    "get_article": ToolPermission(
        required_role="reader",
        topic_scoped=False
    ),
    "search_text_resources": ToolPermission(
        required_role="reader",
        topic_scoped=False
    ),
    "search_table_resources": ToolPermission(
        required_role="reader",
        topic_scoped=False
    ),
    "get_tonalities": ToolPermission(
        required_role="reader",
        topic_scoped=False
    ),

    # Analyst tools
    "create_draft_article": ToolPermission(
        required_role="analyst",
        topic_scoped=True
    ),
    "write_article_content": ToolPermission(
        required_role="analyst",
        topic_scoped=True
    ),
    "create_text_resource": ToolPermission(
        required_role="analyst",
        topic_scoped=True
    ),
    "create_table_resource": ToolPermission(
        required_role="analyst",
        topic_scoped=True
    ),
    "attach_resource": ToolPermission(
        required_role="analyst",
        topic_scoped=True
    ),
    "web_search": ToolPermission(
        required_role="analyst",
        topic_scoped=False
    ),
    "fetch_economic_data": ToolPermission(
        required_role="analyst",
        topic_scoped=False
    ),
    "submit_for_review": ToolPermission(
        required_role="analyst",
        topic_scoped=True
    ),

    # Editor tools
    "review_article": ToolPermission(
        required_role="editor",
        topic_scoped=True
    ),
    "request_changes": ToolPermission(
        required_role="editor",
        topic_scoped=True
    ),
    "publish_article": ToolPermission(
        required_role="editor",
        topic_scoped=True,
        requires_hitl=True
    ),

    # Admin tools
    "get_topic_prompts": ToolPermission(
        required_role="admin",
        topic_scoped=True
    ),
    "edit_prompts": ToolPermission(
        required_role="admin",
        topic_scoped=True,
        global_admin_override=False  # Even global admin needs topic:admin
    ),
}
```

### 6.2 Tool Registry Class

```python
from typing import Dict, List, Optional, Callable
from langchain_core.tools import BaseTool


class ToolRegistry:
    """
    Central registry for all agent tools with permission metadata.
    Supports runtime filtering based on user scopes.
    """

    _instance: Optional["ToolRegistry"] = None
    _tools: Dict[str, BaseTool] = {}
    _permissions: Dict[str, ToolPermission] = {}

    @classmethod
    def instance(cls) -> "ToolRegistry":
        """Singleton access."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        name: str,
        tool: BaseTool,
        permission: ToolPermission
    ) -> None:
        """Register a tool with its permission requirements."""
        self._tools[name] = tool
        self._permissions[name] = permission

        # Attach metadata to tool for introspection
        tool.metadata = {
            "required_role": permission.required_role,
            "topic_scoped": permission.topic_scoped,
            "requires_hitl": permission.requires_hitl,
        }

    def get_tools_for_user(
        self,
        scopes: List[str],
        topic: Optional[str] = None
    ) -> List[BaseTool]:
        """
        Get all tools available to a user based on their scopes.

        Args:
            scopes: User's scopes from JWT
            topic: Optional topic context (for topic-scoped filtering)

        Returns:
            List of tools the user can use
        """
        available = []

        for name, tool in self._tools.items():
            permission = self._permissions[name]

            if self._user_has_permission(scopes, permission, topic):
                available.append(tool)

        return available

    def get_tool_names_for_user(
        self,
        scopes: List[str],
        topic: Optional[str] = None
    ) -> List[str]:
        """Get tool names only (for state.available_tools)."""
        return [
            name for name, perm in self._permissions.items()
            if self._user_has_permission(scopes, perm, topic)
        ]

    def _user_has_permission(
        self,
        scopes: List[str],
        permission: ToolPermission,
        topic: Optional[str]
    ) -> bool:
        """Check if user can use tool with given permission."""
        return check_permission(
            user_scopes=scopes,
            required_role=permission.required_role,
            topic=topic if permission.topic_scoped else None,
            global_admin_override=permission.global_admin_override
        )

    def get_all_tools(self) -> Dict[str, BaseTool]:
        """Get all registered tools (for MCP registration)."""
        return self._tools.copy()

    def get_permission(self, tool_name: str) -> Optional[ToolPermission]:
        """Get permission metadata for a tool."""
        return self._permissions.get(tool_name)
```

### 6.3 Tool Registration

```python
# backend/agents/tools/__init__.py

from agents.tools.tool_registry import ToolRegistry, ToolPermission
from agents.tools.article_tools import (
    search_articles,
    get_article,
    create_draft_article,
    write_article_content,
    submit_for_review,
)
from agents.tools.resource_tools import (
    search_text_resources,
    search_table_resources,
    create_text_resource,
    create_table_resource,
    attach_resource,
)
from agents.tools.research_tools import (
    web_search,
    fetch_economic_data,
    fetch_equity_data,
)
from agents.tools.editor_tools import (
    review_article,
    request_changes,
    publish_article,
)
from agents.tools.prompt_tools import (
    get_tonalities,
    set_user_tonality,
    get_topic_prompts,
)


def register_all_tools():
    """Register all tools with the registry."""
    registry = ToolRegistry.instance()

    # Article tools
    registry.register("search_articles", search_articles, ToolPermission(
        required_role="reader", topic_scoped=True
    ))
    registry.register("get_article", get_article, ToolPermission(
        required_role="reader", topic_scoped=False
    ))
    registry.register("create_draft_article", create_draft_article, ToolPermission(
        required_role="analyst", topic_scoped=True
    ))
    registry.register("write_article_content", write_article_content, ToolPermission(
        required_role="analyst", topic_scoped=True
    ))
    registry.register("submit_for_review", submit_for_review, ToolPermission(
        required_role="analyst", topic_scoped=True
    ))

    # Resource tools
    registry.register("search_text_resources", search_text_resources, ToolPermission(
        required_role="reader", topic_scoped=False
    ))
    registry.register("search_table_resources", search_table_resources, ToolPermission(
        required_role="reader", topic_scoped=False
    ))
    registry.register("create_text_resource", create_text_resource, ToolPermission(
        required_role="analyst", topic_scoped=True
    ))
    registry.register("create_table_resource", create_table_resource, ToolPermission(
        required_role="analyst", topic_scoped=True
    ))
    registry.register("attach_resource", attach_resource, ToolPermission(
        required_role="analyst", topic_scoped=True
    ))

    # Research tools
    registry.register("web_search", web_search, ToolPermission(
        required_role="analyst", topic_scoped=False
    ))
    registry.register("fetch_economic_data", fetch_economic_data, ToolPermission(
        required_role="analyst", topic_scoped=False
    ))
    registry.register("fetch_equity_data", fetch_equity_data, ToolPermission(
        required_role="analyst", topic_scoped=False
    ))

    # Editor tools
    registry.register("review_article", review_article, ToolPermission(
        required_role="editor", topic_scoped=True
    ))
    registry.register("request_changes", request_changes, ToolPermission(
        required_role="editor", topic_scoped=True
    ))
    registry.register("publish_article", publish_article, ToolPermission(
        required_role="editor", topic_scoped=True, requires_hitl=True
    ))

    # Prompt tools
    registry.register("get_tonalities", get_tonalities, ToolPermission(
        required_role="reader", topic_scoped=False
    ))
    registry.register("set_user_tonality", set_user_tonality, ToolPermission(
        required_role="reader", topic_scoped=False
    ))
    registry.register("get_topic_prompts", get_topic_prompts, ToolPermission(
        required_role="admin", topic_scoped=True
    ))


# Auto-register on import
register_all_tools()
```

---

## 7. MCP Endpoint Specifications

### 7.1 Endpoint Overview

| Category | Endpoint | Method | Permission | HITL |
|----------|----------|--------|------------|------|
| **Articles** | `/api/tools/articles/search` | POST | reader | No |
| | `/api/tools/articles/{id}` | GET | reader | No |
| | `/api/tools/articles/create` | POST | analyst | No |
| | `/api/tools/articles/{id}/write` | POST | analyst | No |
| | `/api/tools/articles/{id}/submit` | POST | analyst | No |
| | `/api/tools/articles/{id}/request-changes` | POST | editor | No |
| | `/api/tools/articles/{id}/publish` | POST | editor | Yes |
| **Resources** | `/api/tools/resources/search/text` | POST | reader | No |
| | `/api/tools/resources/search/tables` | POST | reader | No |
| | `/api/tools/resources/create/text` | POST | analyst | No |
| | `/api/tools/resources/create/table` | POST | analyst | No |
| | `/api/tools/resources/{id}/attach` | POST | analyst | No |
| | `/api/tools/resources/{id}/detach` | POST | analyst | No |
| **Research** | `/api/tools/research/web-search` | POST | analyst | No |
| | `/api/tools/research/economic-data` | POST | analyst | No |
| | `/api/tools/research/equity-data` | POST | analyst | No |
| **Workflow** | `/api/tools/workflow/pending-approvals` | GET | editor | No |
| | `/api/approvals/{id}` | POST | editor | Callback |
| **Prompts** | `/api/tools/prompts/tonalities` | GET | reader | No |
| | `/api/tools/prompts/user-tonality` | POST | reader | No |
| | `/api/tools/prompts/topic/{slug}` | GET | admin | No |

### 7.2 Request/Response Schemas

#### Article Search

```python
# POST /api/tools/articles/search

class ArticleSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    topic: str = Field(..., description="Topic slug (macro, equity, etc.)")
    limit: int = Field(default=10, ge=1, le=50)
    include_drafts: bool = Field(default=False)

class ArticleSearchResponse(BaseModel):
    success: bool
    articles: List[ArticleSummary]
    total_count: int

class ArticleSummary(BaseModel):
    id: int
    headline: str
    topic: str
    status: str
    author: Optional[str]
    created_at: str
    similarity_score: Optional[float]
```

#### Create Draft Article

```python
# POST /api/tools/articles/create

class CreateDraftRequest(BaseModel):
    topic: str = Field(..., description="Topic slug")
    headline: str = Field(..., min_length=1, max_length=500)
    keywords: Optional[str] = None

class CreateDraftResponse(BaseModel):
    success: bool
    article_id: int
    headline: str
    status: str = "draft"
```

#### Write Article Content

```python
# POST /api/tools/articles/{article_id}/write

class WriteArticleRequest(BaseModel):
    content: str = Field(..., description="Article content (markdown)")
    resource_ids: List[int] = Field(default=[], description="Resources to attach")

class WriteArticleResponse(BaseModel):
    success: bool
    article_id: int
    content_length: int
    attached_resources: List[int]
```

#### Publish Article (HITL)

```python
# POST /api/tools/articles/{article_id}/publish

class PublishArticleRequest(BaseModel):
    editor_notes: Optional[str] = None

class PublishArticleResponse(BaseModel):
    success: bool
    article_id: int
    status: str  # "pending_approval"
    approval_request_id: int
    message: str  # "Article submitted for approval. Webhook notification sent."
```

#### Approval Callback

```python
# POST /api/approvals/{article_id}

class ApprovalRequest(BaseModel):
    approved: bool
    notes: Optional[str] = None

class ApprovalResponse(BaseModel):
    success: bool
    article_id: int
    new_status: str  # "published" or "editor"
    message: str
```

#### Create Text Resource

```python
# POST /api/tools/resources/create/text

class CreateTextResourceRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., description="Text content")
    topic: Optional[str] = Field(None, description="Topic to associate with")
    article_id: Optional[int] = Field(None, description="Article to auto-attach")
    description: Optional[str] = None

class CreateTextResourceResponse(BaseModel):
    success: bool
    resource_id: int
    name: str
    chromadb_id: Optional[str]
    attached_to_article: Optional[int]
```

### 7.3 MCP Server Configuration

```python
# backend/main.py

from fastapi_mcp import FastApiMCP

# Initialize MCP server with all tool endpoints
mcp = FastApiMCP(
    app,
    name="Financial Analyst MCP Server",
    description="MCP server exposing financial analysis, article management, and research tools",
    include_operations=[
        # Articles
        "search_articles_endpoint",
        "get_article_endpoint",
        "create_draft_article_endpoint",
        "write_article_endpoint",
        "submit_article_endpoint",
        "request_changes_endpoint",
        "publish_article_endpoint",
        # Resources
        "search_text_resources_endpoint",
        "search_table_resources_endpoint",
        "create_text_resource_endpoint",
        "create_table_resource_endpoint",
        "attach_resource_endpoint",
        "detach_resource_endpoint",
        # Research
        "web_search_endpoint",
        "fetch_economic_data_endpoint",
        "fetch_equity_data_endpoint",
        # Workflow
        "get_pending_approvals_endpoint",
        # Prompts
        "get_tonalities_endpoint",
        "set_user_tonality_endpoint",
        "get_topic_prompts_endpoint",
    ]
)
mcp.mount()
```

---

## 8. Human-in-the-Loop Workflow

### 8.1 Editorial Workflow Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ARTICLE LIFECYCLE                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐                                                       │
│  │  DRAFT   │ ◄─────────────────────────────────────────────┐      │
│  └────┬─────┘                                                │      │
│       │                                                      │      │
│       │ submit_for_review()                                  │      │
│       │ (analyst+)                                           │      │
│       ▼                                                      │      │
│  ┌──────────┐                                                │      │
│  │  EDITOR  │ ─────────────────────────────────────┐        │      │
│  └────┬─────┘                                       │        │      │
│       │                                             │        │      │
│       │ publish_article()                           │        │      │
│       │ (editor+, triggers HITL)    request_changes()       │      │
│       ▼                             (editor+)        │        │      │
│  ┌───────────────────┐                              │        │      │
│  │ PENDING_APPROVAL  │                              │        │      │
│  └─────────┬─────────┘                              │        │      │
│            │                                         │        │      │
│            │ Webhook Notification ───────────────────┼────────┼──┐  │
│            │                                         │        │  │  │
│            ▼                                         │        │  │  │
│  ┌──────────────────────────────────────────────────┴────────┘  │  │
│  │                    HUMAN REVIEW                               │  │
│  │  ┌─────────────┐           ┌─────────────┐                   │  │
│  │  │   Approve   │           │   Reject    │                   │  │
│  │  └──────┬──────┘           └──────┬──────┘                   │  │
│  └─────────┼─────────────────────────┼──────────────────────────┘  │
│            │                         │                              │
│            │ /api/approvals/{id}     │ /api/approvals/{id}         │
│            │ {approved: true}        │ {approved: false}            │
│            ▼                         ▼                              │
│  ┌──────────────┐           ┌──────────┐                           │
│  │  PUBLISHED   │           │  EDITOR  │ ───────────────────────────┘
│  └──────────────┘           └──────────┘
│
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 Webhook Configuration

```python
# Database model for webhook configuration

class WebhookConfig(Base):
    """Configuration for HITL webhook notifications."""
    __tablename__ = 'webhook_configs'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)

    # Event type this webhook handles
    event_type = Column(String(50), nullable=False)
    # Values: "approval_required", "article_published", "article_rejected"

    # Webhook URL
    url = Column(String(500), nullable=False)

    # Optional HMAC secret for signature verification
    secret_key = Column(String(255), nullable=True)

    # HTTP method (usually POST)
    method = Column(String(10), default="POST")

    # Custom headers (JSON)
    headers = Column(Text, nullable=True)

    # Active flag
    is_active = Column(Boolean, default=True)

    # Optional topic filter (None = all topics)
    topic_id = Column(Integer, ForeignKey('topics.id'), nullable=True)

    # Retry configuration
    max_retries = Column(Integer, default=3)
    retry_delay_seconds = Column(Integer, default=60)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

### 8.3 Webhook Payload Specification

#### Event: approval_required

Sent when an article is submitted for publishing.

```json
{
  "event": "approval_required",
  "timestamp": "2024-01-15T10:30:00Z",
  "webhook_id": "wh_abc123",

  "article": {
    "id": 123,
    "topic": "macro",
    "headline": "Q4 2024 Economic Outlook: Fed Policy Impact",
    "status": "pending_approval",
    "content_preview": "First 500 characters of article...",
    "word_count": 1500,
    "resource_count": 3,
    "created_at": "2024-01-10T08:00:00Z",
    "submitted_at": "2024-01-15T10:30:00Z"
  },

  "submitter": {
    "id": 45,
    "email": "analyst@example.com",
    "name": "John Doe",
    "role": "analyst"
  },

  "editor_notes": "Ready for publication, includes latest Fed data.",

  "callback": {
    "approve_url": "https://api.example.com/api/approvals/123",
    "method": "POST",
    "payload_approve": {"approved": true, "notes": "optional"},
    "payload_reject": {"approved": false, "notes": "reason for rejection"}
  },

  "ui": {
    "review_url": "https://app.example.com/admin/articles/123/review",
    "article_preview_url": "https://app.example.com/preview/articles/123"
  }
}
```

#### Event: article_published

Sent after successful publication.

```json
{
  "event": "article_published",
  "timestamp": "2024-01-15T14:00:00Z",

  "article": {
    "id": 123,
    "topic": "macro",
    "headline": "Q4 2024 Economic Outlook: Fed Policy Impact",
    "status": "published",
    "public_url": "https://app.example.com/articles/123"
  },

  "approved_by": {
    "id": 78,
    "email": "editor@example.com",
    "name": "Jane Smith"
  },

  "approval_notes": "Great analysis, approved for publication."
}
```

### 8.4 Webhook Service Implementation

```python
# backend/services/webhook_service.py

import httpx
import hmac
import hashlib
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from models import WebhookConfig, ApprovalRequest, ContentArticle
from services.content_service import ContentService


class WebhookNotificationService:
    """
    Service for sending HITL webhook notifications.
    Supports HMAC signing, retries, and multiple webhook targets.
    """

    def __init__(self, db: Session):
        self.db = db

    async def notify_approval_required(
        self,
        article_id: int,
        submitter_id: int,
        editor_notes: Optional[str] = None
    ) -> ApprovalRequest:
        """
        Send webhook notification when article needs approval.
        Creates ApprovalRequest record for tracking.

        Returns:
            ApprovalRequest record
        """
        # Get article
        article = ContentService.get_article(self.db, article_id)
        if not article:
            raise ValueError(f"Article {article_id} not found")

        # Get submitter
        submitter = self.db.query(User).filter(User.id == submitter_id).first()

        # Create approval request record
        approval_request = ApprovalRequest(
            article_id=article_id,
            requested_by=submitter_id,
            status="pending",
            editor_notes=editor_notes
        )
        self.db.add(approval_request)
        self.db.commit()
        self.db.refresh(approval_request)

        # Build payload
        payload = self._build_approval_payload(
            article, submitter, approval_request, editor_notes
        )

        # Get active webhooks for this event
        webhooks = self._get_webhooks("approval_required", article.get("topic"))

        # Send to all configured webhooks
        for webhook in webhooks:
            asyncio.create_task(
                self._send_with_retry(webhook, payload)
            )

        return approval_request

    def _build_approval_payload(
        self,
        article: Dict,
        submitter: User,
        approval_request: ApprovalRequest,
        editor_notes: Optional[str]
    ) -> Dict[str, Any]:
        """Build webhook payload for approval_required event."""
        base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")

        return {
            "event": "approval_required",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "webhook_id": f"wh_{approval_request.id}",

            "article": {
                "id": article["id"],
                "topic": article["topic"],
                "headline": article["headline"],
                "status": "pending_approval",
                "content_preview": article.get("content", "")[:500],
                "word_count": len(article.get("content", "").split()),
                "resource_count": len(article.get("resources", [])),
                "created_at": article.get("created_at"),
                "submitted_at": datetime.utcnow().isoformat() + "Z"
            },

            "submitter": {
                "id": submitter.id,
                "email": submitter.email,
                "name": f"{submitter.name} {submitter.surname}".strip(),
                "role": "analyst"
            },

            "editor_notes": editor_notes,

            "callback": {
                "approve_url": f"{base_url}/api/approvals/{article['id']}",
                "method": "POST",
                "payload_approve": {"approved": True, "notes": "optional"},
                "payload_reject": {"approved": False, "notes": "reason"}
            },

            "ui": {
                "review_url": f"{frontend_url}/admin/articles/{article['id']}/review",
                "article_preview_url": f"{frontend_url}/preview/articles/{article['id']}"
            }
        }

    async def _send_with_retry(
        self,
        webhook: WebhookConfig,
        payload: Dict[str, Any]
    ) -> bool:
        """Send webhook with retry logic."""
        for attempt in range(webhook.max_retries):
            try:
                success = await self._send_webhook(webhook, payload)
                if success:
                    return True

                # Wait before retry
                await asyncio.sleep(webhook.retry_delay_seconds * (attempt + 1))

            except Exception as e:
                logger.error(f"Webhook attempt {attempt + 1} failed: {e}")
                if attempt < webhook.max_retries - 1:
                    await asyncio.sleep(webhook.retry_delay_seconds * (attempt + 1))

        return False

    async def _send_webhook(
        self,
        webhook: WebhookConfig,
        payload: Dict[str, Any]
    ) -> bool:
        """Send single webhook request."""
        headers = {"Content-Type": "application/json"}

        # Parse custom headers
        if webhook.headers:
            try:
                custom_headers = json.loads(webhook.headers)
                headers.update(custom_headers)
            except json.JSONDecodeError:
                pass

        # Add HMAC signature if secret configured
        if webhook.secret_key:
            payload_bytes = json.dumps(payload, sort_keys=True).encode()
            signature = hmac.new(
                webhook.secret_key.encode(),
                payload_bytes,
                hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=webhook.method,
                    url=webhook.url,
                    json=payload,
                    headers=headers,
                    timeout=30.0
                )

                success = 200 <= response.status_code < 300

                if not success:
                    logger.warning(
                        f"Webhook {webhook.name} returned {response.status_code}"
                    )

                return success

        except Exception as e:
            logger.error(f"Webhook {webhook.name} failed: {e}")
            return False

    def _get_webhooks(
        self,
        event_type: str,
        topic: Optional[str] = None
    ) -> List[WebhookConfig]:
        """Get active webhooks for event type."""
        query = self.db.query(WebhookConfig).filter(
            WebhookConfig.event_type == event_type,
            WebhookConfig.is_active == True
        )

        # Include webhooks with matching topic OR no topic filter
        if topic:
            topic_obj = self.db.query(Topic).filter(Topic.slug == topic).first()
            topic_id = topic_obj.id if topic_obj else None

            query = query.filter(
                (WebhookConfig.topic_id == None) |
                (WebhookConfig.topic_id == topic_id)
            )

        return query.all()
```

### 8.5 Approval Request Model

```python
# backend/models.py (addition)

class ApprovalRequest(Base):
    """Track pending approval requests for HITL workflow."""
    __tablename__ = 'approval_requests'

    id = Column(Integer, primary_key=True)

    # Article being approved
    article_id = Column(Integer, ForeignKey('content_articles.id'), nullable=False)
    article = relationship('ContentArticle', backref='approval_requests')

    # Who requested approval
    requested_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    requester = relationship('User', foreign_keys=[requested_by])
    requested_at = Column(DateTime(timezone=True), server_default=func.now())

    # Request status
    status = Column(String(20), default='pending')
    # Values: pending, approved, rejected, expired

    # Editor notes from submitter
    editor_notes = Column(Text, nullable=True)

    # Review information
    reviewed_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    reviewer = relationship('User', foreign_keys=[reviewed_by])
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)

    # Expiration (optional)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Indexes
    __table_args__ = (
        Index('ix_approval_article_status', 'article_id', 'status'),
    )
```

---

## 9. Data Models

### 9.1 Article Status Enum Update

```python
# backend/models.py (modification)

class ArticleStatus(str, enum.Enum):
    """Article lifecycle status."""
    DRAFT = "draft"
    EDITOR = "editor"
    PENDING_APPROVAL = "pending_approval"  # NEW: Waiting for human approval
    PUBLISHED = "published"
```

### 9.2 Database Migration

```python
# backend/alembic/versions/xxx_add_hitl_models.py

"""Add HITL models for editorial workflow

Revision ID: xxx
Revises: previous_revision
Create Date: 2024-12-30
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    # Add new article status value
    # PostgreSQL requires special handling for enum updates
    op.execute("""
        ALTER TYPE articlestatus ADD VALUE IF NOT EXISTS 'pending_approval'
    """)

    # Create webhook_configs table
    op.create_table(
        'webhook_configs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('secret_key', sa.String(255), nullable=True),
        sa.Column('method', sa.String(10), default='POST'),
        sa.Column('headers', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('topic_id', sa.Integer(), sa.ForeignKey('topics.id'), nullable=True),
        sa.Column('max_retries', sa.Integer(), default=3),
        sa.Column('retry_delay_seconds', sa.Integer(), default=60),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create approval_requests table
    op.create_table(
        'approval_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('article_id', sa.Integer(), sa.ForeignKey('content_articles.id'), nullable=False),
        sa.Column('requested_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('editor_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create indexes
    op.create_index(
        'ix_approval_article_status',
        'approval_requests',
        ['article_id', 'status']
    )
    op.create_index(
        'ix_webhook_event_type',
        'webhook_configs',
        ['event_type', 'is_active']
    )


def downgrade():
    op.drop_table('approval_requests')
    op.drop_table('webhook_configs')
    # Note: Cannot easily remove enum value in PostgreSQL
```

---

## 10. Implementation Guide

### 10.1 File Structure

```
backend/
├── agents/
│   ├── __init__.py                    # Updated exports
│   ├── state.py                       # MODIFY: Enhanced state schema
│   ├── base_agent.py                  # MODIFY: Permission-aware base
│   ├── main_chat_agent.py             # MODIFY: UserContext integration
│   │
│   ├── # Query Agents (used by MainChat and/or Analyst)
│   ├── article_query_agent.py         # NEW: Article search/create/write
│   ├── resource_query_agent.py        # EXISTING: Semantic resource search
│   ├── web_search_agent.py            # NEW: Web/news search
│   ├── data_download_agent.py         # NEW: Data API fetching
│   │
│   ├── # Workflow Agents
│   ├── analyst_agent.py               # NEW: Composes query agents for research
│   ├── editor_sub_agent.py            # NEW: HITL publishing workflow
│   │
│   └── tools/
│       ├── __init__.py                # NEW: Tool registration
│       ├── tool_registry.py           # NEW: Permission registry
│       │
│       ├── # Article Tools
│       ├── article_tools.py           # NEW: search, create, write, submit
│       │
│       ├── # Resource Tools
│       ├── resource_tools.py          # MODIFY: Add create/attach tools
│       │
│       ├── # Research Tools (used by WebSearchAgent)
│       ├── web_search_tools.py        # NEW: web_search, search_news
│       │
│       ├── # Data Tools (used by DataDownloadAgent)
│       ├── data_download_tools.py     # NEW: fetch_stock, fetch_economic, etc.
│       │
│       ├── # Editor Tools
│       ├── editor_tools.py            # NEW: review, request_changes, publish
│       │
│       ├── # Prompt Tools
│       ├── prompt_tools.py            # NEW: tonality, topic prompts
│       │
│       └── # Existing tools (kept for compatibility)
│           ├── equity_tools.py
│           ├── economic_tools.py
│           └── fixed_income_tools.py
│
├── api/
│   ├── mcp_tools.py                   # MODIFY: Extended endpoints
│   └── approvals.py                   # NEW: HITL approval API
│
├── services/
│   ├── user_context_service.py        # NEW: UserContext builder
│   ├── webhook_service.py             # NEW: Webhook notifications
│   └── ...existing services...
│
├── models.py                          # MODIFY: HITL models
│
└── alembic/versions/
    └── xxx_add_hitl_models.py         # NEW: Migration
```

### 10.2 Implementation Order

1. **Phase 1: Foundation**
   - Create concept document (this file)
   - Modify `state.py` with new schemas
   - Modify `models.py` with HITL models
   - Create database migration
   - Create `tool_registry.py`

2. **Phase 2: Services**
   - Create `user_context_service.py`
   - Create `webhook_service.py`
   - Modify `base_agent.py` with permissions

3. **Phase 3: Agents**
   - Create `article_query_agent.py`
   - Create `analyst_agent.py`
   - Create `research_sub_agent.py`
   - Create `editor_sub_agent.py`

4. **Phase 4: Tools**
   - Create `article_tools.py`
   - Create `research_tools.py`
   - Create `editor_tools.py`
   - Create `prompt_tools.py`
   - Update tool `__init__.py` with registration

5. **Phase 5: API**
   - Extend `mcp_tools.py` with new endpoints
   - Create `approvals.py` for HITL callbacks
   - Update `main.py` MCP configuration

6. **Phase 6: Integration**
   - Modify `main_chat_agent.py`
   - Update `agent_service.py`
   - Integration testing

---

## 11. Migration Strategy

### 11.1 Backward Compatibility

The new architecture maintains backward compatibility:

1. **Existing endpoints continue to work** - No breaking changes to `/api/chat`
2. **Gradual agent replacement** - New agents can run alongside old ones
3. **Feature flags** - Environment variables control new features

```python
# Environment variables for gradual rollout
ENABLE_NEW_AGENT_SYSTEM=false  # Toggle new agent architecture
ENABLE_HITL_WORKFLOW=false     # Toggle HITL for publishing
ENABLE_TOOL_PERMISSIONS=false  # Toggle permission filtering
```

### 11.2 Rollout Plan

| Phase | Users | Features | Duration |
|-------|-------|----------|----------|
| Alpha | Admin only | All new features | 1 week |
| Beta | Analysts | Article creation workflow | 1 week |
| RC | Editors | HITL publishing | 1 week |
| GA | All users | Full release | - |

### 11.3 Rollback Plan

If issues arise:
1. Set feature flags to `false`
2. System falls back to existing agent architecture
3. No data migration needed (HITL models are additive)

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **HITL** | Human-in-the-loop - requiring human approval for critical actions |
| **MCP** | Model Context Protocol - standard for exposing tools to AI models |
| **Scope** | Permission string in format `{group}:{role}` |
| **Topic** | Content category (macro, equity, fixed_income, esg) |
| **Tonality** | Writing style/tone configuration for prompts |
| **Workflow** | Multi-step operation tracked via WorkflowContext |

---

## Appendix B: Related Documentation

- [01-authentication.md](../01-authentication.md) - OAuth and JWT system
- [02-user-management.md](../02-user-management.md) - User roles and groups
- [04-agentic-workflow.md](../04-agentic-workflow.md) - Current agent system
- [05-resources-pdf.md](../05-resources-pdf.md) - Resource management
