# Celery Background Workers

## Overview

Heavy agent workflows run in **Celery workers** to avoid blocking the chat API. This architecture separates quick, synchronous responses from long-running research and publishing tasks.

---

## Architecture

### Execution Model

| Agent | Execution | Reason |
|-------|-----------|--------|
| **MainChatAgent** | Synchronous (FastAPI) | Quick response needed |
| **ArticleQueryAgent** | Celery Worker | Used by AnalystAgent for article creation |
| **AnalystAgent** | Celery Worker | Heavy research, can take minutes |
| **WebSearchAgent** | Celery Worker | External API calls |
| **DataDownloadAgent** | Celery Worker | External API calls |
| **EditorSubAgent** | Celery Worker | HITL workflow, async |

### Task Flow

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
│  │  │ Celery       │                                                │   │
│  │  │ task.delay() │────────────────────────────────────┐           │   │
│  │  └──────────────┘                                     │           │   │
│  │         │                                             │           │   │
│  │         │ Return task_id                              │           │   │
│  │         ▼                                             │           │   │
│  │  ┌──────────────┐                                     │           │   │
│  │  │ Response:    │                                     │           │   │
│  │  │ "Research    │                                     │           │   │
│  │  │  started..." │                                     │           │   │
│  │  │ task_id: xxx │                                     │           │   │
│  │  └──────────────┘                                     │           │   │
│  │                                                        │           │   │
│  └────────────────────────────────────────────────────────┼───────────┘   │
│                                                            │               │
│  ┌────────────────────────────────────────────────────────┼───────────┐   │
│  │                    Redis (Message Broker)               │           │   │
│  │                                                         │           │   │
│  │  Queue: agent_tasks                                     │           │   │
│  │  ┌───────────────────────────────────────────────────┐ │           │   │
│  │  │ {task_id, user_id, agent_type, params, state}     │◀┘           │   │
│  │  └───────────────────────────────────────────────────┘             │   │
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
│  │  │                └───────────────┘                             │    │   │
│  │  │                                                              │    │   │
│  │  └──────────────────────────────────────────────────────────────┘    │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Notification System                                │   │
│  │                                                                       │   │
│  │  On task completion:                                                  │   │
│  │  - Update task status in Redis                                        │   │
│  │  - Send WebSocket notification to user                                │   │
│  │  - Store result in database                                           │   │
│  │  - Trigger HITL interrupt (if publishing)                             │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Queue Configuration

### Task Queues

| Queue | Purpose | Tasks |
|-------|---------|-------|
| `analyst` | Research workflows | AnalystAgent orchestration |
| `research` | External searches | WebSearchAgent, news search |
| `websearch` | Web-specific searches | Google/DuckDuckGo queries |
| `datadownload` | Data fetching | Stock data, economic indicators |
| `articles` | Article operations | ArticleQueryAgent tasks |
| `editor` | Publishing workflow | EditorSubAgent, HITL |

### Task Routing

Tasks are routed to appropriate queues based on their type:

| Task Type | Queue | Concurrency |
|-----------|-------|-------------|
| Analyst research | `analyst` | 2 workers |
| Web search | `research` | 4 workers |
| Data download | `datadownload` | 4 workers |
| Article creation | `articles` | 2 workers |
| Editor workflow | `editor` | 2 workers |

---

## Deployment

### Docker Architecture

FastAPI and Celery workers run in **separate containers** using the same Docker image but different entrypoint commands:

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  backend (FastAPI)                                      │ │
│  │  - Handles HTTP requests                                │ │
│  │  - Runs MainChatAgent synchronously                     │ │
│  │  - Dispatches tasks to Celery                           │ │
│  │  - Receives WebSocket connections                       │ │
│  └────────────────────────────────────────────────────────┘ │
│                          │                                   │
│                          ▼                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  redis                                                  │ │
│  │  - Message broker for Celery                            │ │
│  │  - Result backend for task status                       │ │
│  │  - LangGraph checkpointing                              │ │
│  │  - Conversation memory                                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                          │                                   │
│                          ▼                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  celery-worker                                          │ │
│  │  - Same image as backend                                │ │
│  │  - Different entrypoint (celery command)                │ │
│  │  - Processes background tasks                           │ │
│  │  - Runs research agents                                 │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Demo vs Production

**Demo Configuration** (resource-efficient):
- Single Celery worker handles all queues
- Concurrency set to 2
- Suitable for development and demos

**Production Configuration**:
- Separate workers per queue type
- Higher concurrency for research tasks
- Independent scaling based on queue depth

### Benefits of Separate Containers

| Benefit | Description |
|---------|-------------|
| **Independent scaling** | Scale workers based on queue depth without affecting API |
| **Resource isolation** | Worker OOM/crash doesn't bring down the API |
| **Clean deployment** | Roll out worker changes without API downtime |
| **Queue prioritization** | Different concurrency per task type |

---

## Task Lifecycle

### 1. Task Creation

When a user requests research or analysis:

1. MainChatAgent routes the query
2. If heavy processing needed, creates Celery task
3. Returns task_id immediately to user
4. User sees "Research started..." message

### 2. Task Execution

In the Celery worker:

1. Task picked up from queue
2. Agent workflow executes
3. Sub-agents (WebSearch, DataDownload) run
4. Resources created and attached
5. Article written or updated

### 3. Task Completion

When task finishes:

1. Result stored in Redis backend
2. Task status updated
3. WebSocket notification sent to user
4. Database records updated

### 4. Status Checking

Users can check task status:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/tasks/{task_id}` | Check task status |
| WebSocket | Real-time notifications |

Task statuses:
- `PENDING` - In queue, not started
- `STARTED` - Currently executing
- `SUCCESS` - Completed successfully
- `FAILURE` - Failed with error

---

## WebSocket Notifications

### Connection Management

- Each user maintains a WebSocket connection
- Connection tracked by user_id
- Automatic reconnection on disconnect

### Notification Types

| Type | When Sent | Payload |
|------|-----------|---------|
| `task_started` | Task begins processing | task_id, agent_type |
| `task_progress` | Intermediate updates | task_id, progress info |
| `task_complete` | Task finished | task_id, result summary |
| `task_failed` | Task errored | task_id, error message |
| `hitl_pending` | Awaiting approval | article_id, approval_id |

---

## Error Handling

### Retry Configuration

| Setting | Value | Purpose |
|---------|-------|---------|
| `max_retries` | 3 | Number of retry attempts |
| `retry_backoff` | True | Exponential backoff |
| `retry_delay` | 60s | Base delay between retries |

### Failure Scenarios

| Scenario | Handling |
|----------|----------|
| External API timeout | Retry with backoff |
| Database connection error | Retry with backoff |
| Agent exception | Log, notify user, mark failed |
| Worker crash | Task requeued automatically |

---

## Monitoring

### Key Metrics

| Metric | Purpose |
|--------|---------|
| Queue depth | Tasks waiting to process |
| Task duration | Time to complete tasks |
| Success rate | Percentage of successful tasks |
| Worker utilization | CPU/memory usage |

### Health Checks

- Celery worker heartbeat
- Redis connection status
- Queue backlog monitoring
- Task timeout detection

---

## Related Documentation

- [Multi-Agent Architecture](./08-multi-agent-architecture.md) - Agent hierarchy and workflows
- [Redis Cache](./12-redis-cache.md) - Redis configuration
- [Databases](./11-databases.md) - Database architecture
