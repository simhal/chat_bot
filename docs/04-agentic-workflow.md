# Agentic Workflow

## Overview

The platform implements a sophisticated **multi-agent AI system** that routes user queries to specialized domain experts. Rather than using a single general-purpose AI, the system employs multiple specialist agents - each with deep expertise in a specific research domain. A routing layer analyzes incoming queries and delegates them to the most appropriate specialist, resulting in more focused and accurate responses.

---

## Why Multi-Agent Architecture?

### The Challenge

A single general-purpose AI model faces limitations when handling diverse research domains:

- **Expertise depth**: Difficult to be an expert in macroeconomics, equity analysis, AND fixed income simultaneously
- **Tool usage**: Different domains require different tools (economic indicators vs. stock data vs. bond yields)
- **Context relevance**: Mixing content from unrelated domains can confuse responses
- **Prompt optimization**: One prompt style doesn't fit all domains

### The Solution

The multi-agent architecture addresses these challenges by:

- **Specialization**: Each agent is optimized for its specific domain
- **Focused context**: Agents only receive relevant research articles
- **Domain tools**: Each agent has access to tools specific to its expertise
- **Intelligent routing**: The right specialist handles each query

---

## System Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Query                                      │
│                    "What's driving inflation higher?"                        │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MainChatAgent                                      │
│                                                                              │
│   • Manages conversation memory (Redis)                                      │
│   • Loads user preferences (tonality)                                        │
│   • Coordinates the multi-agent workflow                                     │
│   • Returns response with metadata                                           │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          MultiAgentGraph                                     │
│                      (LangGraph State Machine)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         Router Agent                                 │   │
│   │                                                                      │   │
│   │   Analyzes query content and selects the best specialist:           │   │
│   │   • Macroeconomic concepts → Economist Agent                        │   │
│   │   • Stock/company topics → Equity Agent                             │   │
│   │   • Bond/yield topics → Fixed Income Agent                          │   │
│   └───────────────────────────────┬─────────────────────────────────────┘   │
│                                   │                                          │
│             ┌─────────────────────┼─────────────────────┐                   │
│             │                     │                     │                    │
│             ▼                     ▼                     ▼                    │
│   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐          │
│   │   Economist     │   │     Equity      │   │  Fixed Income   │          │
│   │     Agent       │   │     Agent       │   │     Agent       │          │
│   │                 │   │                 │   │                 │          │
│   │ GDP, inflation  │   │ Stocks, sectors │   │ Bonds, yields   │          │
│   │ central banks   │   │ valuations      │   │ credit spreads  │          │
│   └────────┬────────┘   └────────┬────────┘   └────────┬────────┘          │
│            │                     │                     │                    │
│            └─────────────────────┴─────────────────────┘                    │
│                                  │                                           │
│                                  ▼                                           │
│                        ┌─────────────────┐                                  │
│                        │    Response     │                                  │
│                        └─────────────────┘                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       ChromaDB Context Retrieval                             │
│                                                                              │
│   Semantic search finds relevant published articles to ground the response   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Deep Dive

### Main Chat Agent

The **MainChatAgent** is the orchestration layer that ties everything together:

| Responsibility | What It Does |
|----------------|--------------|
| **Memory Management** | Loads conversation history from Redis, saves new exchanges |
| **User Context** | Retrieves user preferences (tonality settings) |
| **Workflow Execution** | Invokes the multi-agent graph with prepared state |
| **Context Retrieval** | Searches ChromaDB for relevant research articles |
| **Response Assembly** | Combines agent response with metadata |

#### Conversation Flow

```
User sends message
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. Load conversation history from Redis                       │
│    (Last N messages for context continuity)                   │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. Prepare initial state:                                     │
│    • Messages = history + new message                         │
│    • User preferences (tonality)                              │
│    • User ID for personalization                              │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 3. Run multi-agent workflow                                   │
│    • Router selects specialist                                │
│    • Specialist generates response                            │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 4. Search ChromaDB for related content                        │
│    • Embed user query                                         │
│    • Find similar published articles                          │
│    • Return top 3-5 relevant articles                         │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 5. Save to memory                                             │
│    • Add user message to Redis                                │
│    • Add agent response to Redis                              │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 6. Return response                                            │
│    • Agent's answer text                                      │
│    • Which specialist was selected                            │
│    • Why that specialist was chosen                           │
│    • Related articles for reference                           │
└───────────────────────────────────────────────────────────────┘
```

---

### Router Agent

The **Router Agent** is the intelligent dispatcher that analyzes queries and selects specialists:

#### How Routing Works

```
Query: "What impact will rising interest rates have on tech stocks?"
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Router Agent Analysis                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Detected concepts:                                                          │
│  • "interest rates" → Could be macro OR fixed income                        │
│  • "tech stocks" → Equity domain                                            │
│                                                                              │
│  Primary focus determination:                                                │
│  • Query is asking about STOCK IMPACT                                       │
│  • Interest rates are the cause, stocks are the subject                     │
│                                                                              │
│  Decision: Route to EQUITY AGENT                                            │
│  Reason: "Query focuses on stock impact; equity specialist best suited"     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Routing Decision Factors

| Factor | What It Considers |
|--------|-------------------|
| **Keywords** | Domain-specific terminology (GDP, P/E ratio, yield curve) |
| **Question Focus** | What is the user ultimately asking about? |
| **Context** | Previous messages in the conversation |
| **Ambiguity Resolution** | When topics overlap, which is primary? |

#### Example Routing Patterns

| Query | Selected Agent | Reason |
|-------|----------------|--------|
| "Explain the Fed's latest rate decision" | Economist | Central bank policy is macro focus |
| "How will rate hikes affect Apple stock?" | Equity | Company-specific stock impact |
| "What's happening with Treasury yields?" | Fixed Income | Government bond analysis |
| "Is inflation transitory or persistent?" | Economist | Macroeconomic indicator analysis |
| "Which sectors perform well in high inflation?" | Equity | Sector allocation question |
| "How do credit spreads compare to 2019?" | Fixed Income | Bond market comparison |

---

### Specialist Agents

Each specialist agent is a domain expert with tailored capabilities:

#### Agent Comparison

| Agent | Domain | Expertise Areas | Available Tools |
|-------|--------|-----------------|-----------------|
| **Economist** | Macro | GDP, inflation, monetary policy, fiscal policy, central banks, economic indicators | Economic data APIs, central bank feeds, indicator lookups |
| **Equity** | Equity | Stock analysis, company valuations, sector trends, earnings, market movements | Stock price data, financial statements, sector analytics |
| **Fixed Income** | Bonds | Yields, credit spreads, duration, sovereign debt, interest rates | Bond yield data, credit ratings, curve analysis |

#### Agent Structure

Each specialist agent follows the same structural pattern:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Specialist Agent                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     System Prompt                                    │   │
│   │                                                                      │   │
│   │   "You are an expert {domain} analyst. Your role is to provide     │   │
│   │    accurate, data-driven insights about {expertise areas}..."       │   │
│   │                                                                      │   │
│   │   + User's tonality preference                                       │   │
│   │   + Domain-specific instructions                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     Domain Tools                                     │   │
│   │                                                                      │   │
│   │   • Data lookup tools (APIs for domain data)                        │   │
│   │   • Calculation tools (domain-specific metrics)                     │   │
│   │   • Web search (for current events)                                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     Context Retrieval                                │   │
│   │                                                                      │   │
│   │   • Search ChromaDB for relevant articles                           │   │
│   │   • Filter by topic and published status                            │   │
│   │   • Include article excerpts in prompt                              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### State Machine (LangGraph)

The multi-agent workflow is implemented as a **state machine** using LangGraph:

#### State Definition

The workflow maintains state that flows through each node:

| State Field | Purpose |
|-------------|---------|
| **messages** | Conversation history (user + agent messages) |
| **selected_agent** | Which specialist was chosen by router |
| **routing_reason** | Explanation of why that specialist was selected |
| **user_id** | For personalization and memory lookup |
| **user_custom_prompt** | Tonality preferences |
| **iterations** | Loop counter for safety (prevents infinite loops) |
| **is_final** | Flag indicating response is complete |

#### Graph Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LangGraph Workflow                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   START                                                                      │
│     │                                                                        │
│     ▼                                                                        │
│   ┌─────────────┐                                                           │
│   │   router    │ ─────────────────────────────────────────────────────────►│
│   └─────────────┘                                                           │
│         │                                                                    │
│         │ (conditional edge based on selected_agent)                        │
│         │                                                                    │
│         ├─── selected_agent == "economist" ───► ┌─────────────┐            │
│         │                                        │  economist  │ ───► END   │
│         │                                        └─────────────┘            │
│         │                                                                    │
│         ├─── selected_agent == "equity" ──────► ┌─────────────┐            │
│         │                                        │   equity    │ ───► END   │
│         │                                        └─────────────┘            │
│         │                                                                    │
│         └─── selected_agent == "fixed_income" ► ┌─────────────┐            │
│                                                  │fixed_income │ ───► END   │
│                                                  └─────────────┘            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Content Generation Agent

Separate from the chat workflow, a **Content Agent** generates full research articles:

### Content Agent vs Chat Agents

| Aspect | Chat Agents | Content Agent |
|--------|-------------|---------------|
| **Purpose** | Answer questions interactively | Generate complete articles |
| **Output Length** | Short to medium responses | 1000-2000 word articles |
| **Model Quality** | Standard model for speed | Higher-quality model for depth |
| **Structure** | Conversational | Formal article with sections |
| **Storage** | Response only | Creates database record |

### Article Generation Flow

```
Analyst requests article: "Write about current inflation trends"
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Build content prompt                                                      │
│    • Load topic-specific system prompt                                       │
│    • Apply user's content tonality preference                                │
│    • Include formatting requirements                                         │
└───────────────────────────────────────────────────────────────────────────┬─┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Retrieve context from ChromaDB                                            │
│    • Search for similar existing articles                                    │
│    • Filter by topic (macro, equity, etc.)                                  │
│    • Get top 5 relevant articles for reference                              │
└───────────────────────────────────────────────────────────────────────────┬─┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Generate article                                                          │
│    • LLM produces structured content                                         │
│    • Includes headline, body, keywords                                       │
│    • Professional tone with data references                                  │
└───────────────────────────────────────────────────────────────────────────┬─┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Store article                                                             │
│    • Create record in PostgreSQL (status: draft)                            │
│    • Store content in ChromaDB with embedding                               │
│    • Return article for analyst to review/edit                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Conversation Memory

### Memory Architecture

Conversation memory enables contextual, multi-turn dialogues:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Conversation Memory (Redis)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Key: conversation:{user_id}                                               │
│                                                                              │
│   Value: [                                                                   │
│     { role: "user", content: "What's happening with inflation?" }          │
│     { role: "assistant", content: "Current inflation..." }                  │
│     { role: "user", content: "How does that compare to 2023?" }            │
│     { role: "assistant", content: "Compared to last year..." }             │
│     ...                                                                      │
│   ]                                                                          │
│                                                                              │
│   TTL: Expires after period of inactivity                                   │
│   Max Messages: Rolling window (e.g., last 50 exchanges)                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Memory Benefits

| Benefit | How It Works |
|---------|--------------|
| **Context continuity** | Agent knows what was discussed before |
| **Reference resolution** | "How does that compare..." - agent knows what "that" refers to |
| **Personalization** | Agent can adapt based on user's interests |
| **Avoiding repetition** | Agent remembers what it already explained |

### Memory Operations

| Operation | When It Happens |
|-----------|-----------------|
| **Load** | At start of each new message processing |
| **Append** | After each user message and agent response |
| **Trim** | Automatically keep only recent N messages |
| **Clear** | User can reset conversation, or TTL expiration |

---

## Context Retrieval (RAG)

### How Context Enriches Responses

The system uses **Retrieval-Augmented Generation (RAG)** to ground responses in actual research content:

```
User Query: "What are the implications of rising Treasury yields?"
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Embed the query                                                           │
│    • Convert query to 1536-dimensional vector                               │
│    • Same embedding model used for article storage                          │
└───────────────────────────────────────────────────────────────────────────┬─┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Semantic search in ChromaDB                                               │
│    • Compare query vector to all article vectors                            │
│    • Filter: status = "published", topic = relevant domain                  │
│    • Rank by cosine similarity                                              │
└───────────────────────────────────────────────────────────────────────────┬─┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Retrieve top matches                                                      │
│                                                                              │
│    Article 1: "Treasury Yield Analysis Q4 2024" (similarity: 0.89)         │
│    Article 2: "Fed Policy and Bond Market Impact" (similarity: 0.85)       │
│    Article 3: "Fixed Income Outlook 2025" (similarity: 0.82)               │
└───────────────────────────────────────────────────────────────────────────┬─┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Include in agent prompt                                                   │
│                                                                              │
│    System: "You are a fixed income expert..."                               │
│    Context: "Based on our research:                                          │
│              - Article 1 excerpt...                                          │
│              - Article 2 excerpt..."                                         │
│    User: "What are the implications of rising Treasury yields?"             │
└───────────────────────────────────────────────────────────────────────────┬─┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. Generate grounded response                                                │
│                                                                              │
│    Agent response is informed by actual research articles,                   │
│    not just general knowledge                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Prompt Composition

### How Prompts Are Built

Agent prompts are constructed from modular components:

| Component | Purpose | Source |
|-----------|---------|--------|
| **Base System Prompt** | Core agent personality and capabilities | Database (PromptModule) |
| **Domain Instructions** | Topic-specific guidelines | Database (PromptModule) |
| **User Tonality** | Communication style preference | User settings |
| **Retrieved Context** | Relevant research articles | ChromaDB search |
| **Conversation History** | Previous exchanges | Redis memory |
| **Current Query** | What the user is asking now | User input |

### Prompt Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Complete Agent Prompt                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   [System Prompt]                                                            │
│   You are an expert macroeconomic analyst. Your role is to provide          │
│   accurate, data-driven insights about economic trends...                   │
│                                                                              │
│   [Tonality Instructions]                                                    │
│   Respond in a professional tone. Use formal language and precise           │
│   terminology appropriate for institutional investors...                    │
│                                                                              │
│   [Research Context]                                                         │
│   The following research articles may be relevant:                          │
│   - "Inflation Trends Q4 2024": Current CPI readings show...               │
│   - "Fed Policy Outlook": The Federal Reserve is expected to...             │
│                                                                              │
│   [Conversation History]                                                     │
│   User: What's happening with inflation?                                     │
│   Assistant: Current inflation trends show...                                │
│                                                                              │
│   [Current Query]                                                            │
│   User: How does that compare to expectations?                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Fallback Behavior

### When Multi-Agent is Disabled

The system can fall back to a simpler single-agent mode:

| Scenario | Behavior |
|----------|----------|
| Multi-agent disabled via config | Use general-purpose chatbot agent |
| Router fails to select agent | Default to economist agent |
| Specialist agent fails | Return error with graceful message |
| ChromaDB unavailable | Proceed without context (reduced quality) |

### Error Handling

| Error Type | Response |
|------------|----------|
| **Router timeout** | Select default agent, log warning |
| **Agent exception** | Return user-friendly error, log details |
| **Memory failure** | Proceed without history, log warning |
| **Context retrieval failure** | Proceed without context, log warning |

---

## Performance Considerations

### Latency Breakdown

| Step | Typical Latency | Optimization |
|------|-----------------|--------------|
| Memory load | 1-5 ms | Redis in-memory |
| Routing decision | 200-500 ms | Optimized prompt |
| Context retrieval | 50-200 ms | Vector index |
| Agent response | 1-5 seconds | Streaming available |
| Memory save | 1-5 ms | Async write |

### Scaling Considerations

| Component | Scaling Strategy |
|-----------|------------------|
| Router | Stateless, horizontally scalable |
| Specialists | Can run in parallel for different users |
| Memory (Redis) | Cluster mode for high volume |
| Context (ChromaDB) | Replicated for read scaling |
