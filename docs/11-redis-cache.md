# Redis: Memory & Authorization Layer

## Overview

Redis serves as the **high-speed memory layer** for the platform, providing three critical functions:

| Function | Purpose | Why Redis? |
|----------|---------|------------|
| **Authorization Management** | Token validation and session control | Sub-millisecond lookups for every API request |
| **Agentic Memory** | Conversation history for AI agents | Fast read/write for real-time chat context |
| **Content Caching** | Frequently accessed articles and search results | Reduce database load, improve response times |

Redis operates as an in-memory data store, making it ideal for data that needs to be accessed frequently and quickly, but doesn't require the durability guarantees of a traditional database.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Redis Server                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐  │
│  │  Authorization       │  │   Agentic Memory     │  │  Content Cache   │  │
│  │                      │  │                      │  │                  │  │
│  │  • Access tokens     │  │  • Conversation      │  │  • Articles      │  │
│  │  • Refresh tokens    │  │    history           │  │  • Topic lists   │  │
│  │  • Session state     │  │  • Agent context     │  │  • Search results│  │
│  │                      │  │  • User preferences  │  │                  │  │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────┘  │
│                                                                              │
│           ▲                          ▲                        ▲             │
│           │                          │                        │             │
└───────────┼──────────────────────────┼────────────────────────┼─────────────┘
            │                          │                        │
     Every API Request          AI Chat Sessions         Page Loads
```

---

## Authorization Management

### The Challenge

Every API request to the platform must be authenticated. With potentially thousands of requests per second, looking up user credentials in PostgreSQL for each request would create unacceptable latency and database load.

### The Solution: Token Cache

When a user authenticates via LinkedIn OAuth, the system generates a JWT (JSON Web Token) containing the user's identity and permissions. However, JWTs alone have a limitation: they cannot be revoked until they expire. To enable instant token revocation (for security events like password changes or compromised accounts), the system maintains a token registry in Redis.

**How it works:**

1. **Login**: User authenticates → JWT generated → Token ID registered in Redis
2. **API Request**: JWT presented → Token ID checked in Redis → If present, request proceeds
3. **Logout/Revoke**: Token ID removed from Redis → Future requests with that JWT fail

### Token Lifecycle

```
User Login
    │
    ▼
Generate JWT with unique Token ID
    │
    ├──► Store Token ID in Redis (with TTL)
    │
    └──► Return JWT to client
           │
           ▼
    Client makes API request
           │
           ▼
    Validate JWT signature
           │
           ▼
    Check Token ID exists in Redis ──► Not found? → Reject request
           │
           ▼
    Process request
```

### Token Types

| Token | Purpose | Lifetime | Revocation |
|-------|---------|----------|------------|
| **Access Token** | Authorize API requests | Short (hours) | Immediate via Redis deletion |
| **Refresh Token** | Obtain new access tokens | Long (days) | Immediate via Redis deletion |

### Security Scenarios

**User logs out:**
- Access and refresh token IDs are deleted from Redis
- Any existing tokens become immediately invalid

**Suspicious activity detected:**
- All token IDs for the user can be deleted at once
- User is forced to re-authenticate on all devices

**Session management:**
- Administrators can view active sessions (token count per user)
- Individual sessions can be terminated without affecting others

---

## Agentic Memory

### The Challenge

AI agents in the platform (Router Agent, Specialist Agents) need to maintain conversation context across multiple exchanges. Without memory, each message would be treated in isolation, losing the thread of discussion.

### The Solution: Conversation Memory

Redis stores the conversation history for each user, allowing AI agents to:
- Remember what was discussed earlier in the conversation
- Maintain context about the user's research interests
- Avoid repeating information already provided
- Build on previous answers for more coherent dialogue

### How Agentic Memory Works

```
User sends message
        │
        ▼
Load conversation history from Redis
        │
        ▼
Combine: System prompt + History + New message
        │
        ▼
Send to AI Agent (with full context)
        │
        ▼
Agent responds
        │
        ▼
Append user message + agent response to Redis
        │
        ▼
Return response to user
```

### Memory Structure

Each conversation maintains a rolling window of recent exchanges:

| Component | Description |
|-----------|-------------|
| **User Messages** | What the user asked or said |
| **Agent Responses** | How the AI responded |
| **Timestamps** | When each exchange occurred |
| **Context Markers** | Topic switches, clarifications, etc. |

### Memory Management

**Window Size**: Conversations maintain a fixed number of recent messages (e.g., last 50 exchanges) to balance context richness with performance and token costs.

**Time-to-Live (TTL)**: Conversation history expires after a period of inactivity. This ensures:
- Privacy: Old conversations don't persist indefinitely
- Performance: Memory doesn't grow unbounded
- Fresh starts: Users can begin new topics without stale context

**Per-User Isolation**: Each user's conversation history is completely separate, ensuring privacy and preventing context bleeding between users.

### Agent Context Enrichment

Beyond raw conversation history, the agentic memory can store:

| Data | Purpose |
|------|---------|
| **User Preferences** | Preferred topics, communication style, tonality settings |
| **Research Focus** | Current areas of interest (e.g., "user is researching inflation") |
| **Cited Articles** | Resources already referenced to avoid repetition |
| **Pending Follow-ups** | Questions the agent promised to address |

---

## Content Caching

### The Challenge

Article pages, topic listings, and search results are frequently accessed. Loading each from PostgreSQL and ChromaDB for every request is inefficient, especially for published content that rarely changes.

### The Solution: Multi-Level Cache

Redis caches three types of content:

| Cache Type | What It Stores | When Invalidated |
|------------|----------------|------------------|
| **Article Cache** | Full article content and metadata | When article is updated |
| **Topic Cache** | Lists of articles per topic | When any article in topic changes |
| **Search Cache** | Results for specific queries | When underlying articles change |

### Cache Flow

```
User requests article
        │
        ▼
Check Redis cache ──────────────────────────┐
        │                                    │
        │ Cache hit?                         │
        │                                    │
   ┌────┴────┐                               │
   │   Yes   │                               │
   │         ▼                               │
   │  Return cached                          │
   │  content                                │
   │                                         │
   │   No                                    │
   │         ▼                               │
   └──► Query PostgreSQL + ChromaDB          │
                │                            │
                ▼                            │
        Store result in Redis ───────────────┘
                │
                ▼
        Return content
```

### Cache Invalidation Strategy

Caches are invalidated (deleted) when underlying data changes:

| Action | Caches Invalidated |
|--------|-------------------|
| Article created | Topic list cache |
| Article updated | Article cache + Topic list cache |
| Article published | Article cache + Topic list cache |
| Article deleted | Article cache + Topic list cache |
| Bulk import | All caches for affected topics |

**Key Principle**: It's better to invalidate too much than too little. A cache miss means a database query (slow but correct). A stale cache means showing outdated data (fast but wrong).

---

## Why Redis for Each Role?

### Authorization: Speed is Security

Token validation happens on every single API request. Even a 10ms database lookup would add noticeable latency across the platform. Redis provides sub-millisecond lookups, making authentication effectively invisible to users.

Additionally, Redis's atomic operations ensure that token revocation is immediate and consistent - there's no window where a revoked token might still work.

### Agentic Memory: Ephemeral by Nature

Conversation history is:
- **Temporary**: Not needed after the session ends
- **User-specific**: Isolated per user
- **Frequently accessed**: Every message needs the full history
- **Regularly updated**: Every exchange adds new entries

These characteristics match Redis perfectly - fast reads and writes for data that doesn't need long-term persistence.

### Content Cache: Predictable Access Patterns

Article content follows the 80/20 rule: a small percentage of articles receive most of the traffic. Caching these hot items in Redis dramatically reduces database load while providing near-instant page loads for popular content.

---

## Graceful Degradation

When Redis is unavailable, the system continues operating in degraded mode:

| Function | Fallback Behavior |
|----------|-------------------|
| **Authorization** | Validate JWT signature only (no revocation check) |
| **Agentic Memory** | Each message treated independently (no history) |
| **Content Cache** | All requests go to database (slower but functional) |

The platform logs warnings when Redis is unavailable and automatically reconnects when it becomes available again.

---

## Memory Lifecycle Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Data Lifecycle in Redis                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Authorization Tokens                                                        │
│  ════════════════════                                                        │
│  Created: User login                                                         │
│  Expires: After configured lifetime (hours/days)                             │
│  Deleted: User logout, admin revocation, security event                      │
│                                                                              │
│  Conversation Memory                                                         │
│  ════════════════════                                                        │
│  Created: First message in session                                           │
│  Updated: Every message exchange                                             │
│  Expires: After period of inactivity                                         │
│  Deleted: User clears history, TTL expiration                                │
│                                                                              │
│  Content Cache                                                               │
│  ════════════════════                                                        │
│  Created: First request for content                                          │
│  Expires: After configured TTL (typically 1 hour)                            │
│  Deleted: Content update triggers invalidation                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Integration with Other Systems

| System | How Redis Connects |
|--------|-------------------|
| **Authentication (OAuth)** | Stores validated tokens after successful login |
| **API Gateway** | Checks token validity on every request |
| **AI Agents** | Read/write conversation history during chat |
| **Content Service** | Cache-through pattern for article retrieval |
| **Admin Panel** | Session management, cache statistics |

---

## Key Design Principles

1. **TTL Everything**: All Redis keys have expiration times to prevent unbounded memory growth

2. **Fail Open for Cache**: If cache read fails, proceed to database (availability over speed)

3. **Fail Closed for Auth**: If token validation fails, reject the request (security over availability)

4. **Atomic Operations**: Use Redis transactions for operations that must be all-or-nothing

5. **Key Prefixes**: All keys use prefixes to organize data and enable pattern-based operations

---

## Related Documentation

- [Authentication](./01-authentication.md) - Token management
- [Databases](./10-databases.md) - Storage architecture
- [Multi-Agent Architecture](./08-multi-agent-architecture.md) - LangGraph checkpointing
