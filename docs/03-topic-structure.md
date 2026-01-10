# Topic Structure

## Overview

The platform organizes research content into distinct **topic domains**, each functioning as a self-contained research vertical. Topics provide organizational boundaries for content, resources, permissions, and AI agent expertise. This topic-based architecture enables specialized research workflows while maintaining consistent patterns across the platform.

---

## What is a Topic?

A **topic** represents a research domain or subject area. Each topic has:

- **Dedicated content**: Articles written specifically for that research area
- **Specialized resources**: Data files, charts, and documents relevant to the topic
- **Permission groups**: Role-based access control scoped to the topic
- **AI expertise**: Agents with domain-specific knowledge and tools

Think of topics as separate "departments" within a research organization, each with its own team, resources, and workflow.

---

## Research Topics

### Primary Research Domains

| Topic | Identifier | Research Focus |
|-------|------------|----------------|
| **Macroeconomic** | `macro` | GDP, inflation, monetary policy, fiscal policy, economic indicators, central bank actions |
| **Equity** | `equity` | Stock analysis, company valuations, sector trends, earnings, market movements |
| **Fixed Income** | `fixed_income` | Bond markets, yields, credit spreads, duration, sovereign debt, interest rates |
| **ESG** | `esg` | Environmental, social, governance factors, sustainable investing, impact metrics |

### Global Scope

| Topic | Identifier | Purpose |
|-------|------------|---------|
| **Global** | `global` | System-wide settings, shared resources, cross-topic content, user management |

The `global` topic is special - it doesn't represent research content but rather platform-wide administration and shared resources.

---

## Topic-Based Organization

### Content Organization

Every article belongs to exactly one topic:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Platform Content                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐ │
│  │    Macro      │  │    Equity     │  │ Fixed Income  │  │     ESG      │ │
│  ├───────────────┤  ├───────────────┤  ├───────────────┤  ├──────────────┤ │
│  │               │  │               │  │               │  │              │ │
│  │ • Inflation   │  │ • Tech sector │  │ • Treasury    │  │ • Carbon     │ │
│  │   outlook     │  │   analysis    │  │   yields      │  │   markets    │ │
│  │               │  │               │  │               │  │              │ │
│  │ • GDP growth  │  │ • Earnings    │  │ • Credit      │  │ • ESG        │ │
│  │   forecast    │  │   previews    │  │   spreads     │  │   ratings    │ │
│  │               │  │               │  │               │  │              │ │
│  │ • Central     │  │ • IPO         │  │ • Duration    │  │ • Green      │ │
│  │   bank policy │  │   analysis    │  │   strategies  │  │   bonds      │ │
│  │               │  │               │  │               │  │              │ │
│  └───────────────┘  └───────────────┘  └───────────────┘  └──────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Resource Organization

Resources are associated with topics through group membership:

| Resource Location | Accessible To |
|-------------------|---------------|
| `macro:admin` group | Users with any macro role |
| `equity:admin` group | Users with any equity role |
| `global:admin` group | Only global administrators |

---

## Permission Structure

### Role Hierarchy Within a Topic

Each topic has four permission levels forming a hierarchy:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Within Each Topic                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│     ┌─────────────────────────────────────────────────────────────────┐     │
│     │                         {topic}:admin                            │     │
│     │                                                                  │     │
│     │  • Full control over the topic                                   │     │
│     │  • Manage topic resources                                        │     │
│     │  • Assign users to topic groups                                  │     │
│     │  • All analyst + editor capabilities                             │     │
│     └─────────────────────────────────┬───────────────────────────────┘     │
│                                       │                                      │
│     ┌─────────────────────────────────▼───────────────────────────────┐     │
│     │                       {topic}:analyst                            │     │
│     │                                                                  │     │
│     │  • Create new draft articles                                     │     │
│     │  • Edit own draft articles                                       │     │
│     │  • Submit drafts for review                                      │     │
│     │  • Manage topic resources                                        │     │
│     └─────────────────────────────────┬───────────────────────────────┘     │
│                                       │                                      │
│     ┌─────────────────────────────────▼───────────────────────────────┐     │
│     │                        {topic}:editor                            │     │
│     │                                                                  │     │
│     │  • View all articles (including drafts)                          │     │
│     │  • Edit articles in "editor" status                              │     │
│     │  • Approve or reject submissions                                 │     │
│     │  • Publish approved articles                                     │     │
│     └─────────────────────────────────┬───────────────────────────────┘     │
│                                       │                                      │
│     ┌─────────────────────────────────▼───────────────────────────────┐     │
│     │                        {topic}:reader                            │     │
│     │                                                                  │     │
│     │  • View published articles only                                  │     │
│     │  • No editing or creation capabilities                           │     │
│     │  • Access to chatbot for topic questions                         │     │
│     └─────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cross-Topic Access

The `global:admin` role transcends topic boundaries:

```
                    ┌─────────────────────────────┐
                    │       global:admin          │
                    │                             │
                    │   • Access to ALL topics    │
                    │   • Bypass all checks       │
                    │   • System administration   │
                    └──────────────┬──────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
   ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
   │    Macro    │          │   Equity    │          │  Fixed Inc  │
   │   (full)    │          │   (full)    │          │   (full)    │
   └─────────────┘          └─────────────┘          └─────────────┘
```

### Role Capabilities Matrix

| Capability | Reader | Editor | Analyst | Admin | Global Admin |
|------------|--------|--------|---------|-------|--------------|
| View published content | Yes | Yes | Yes | Yes | Yes (all topics) |
| View drafts | No | Yes | Yes | Yes | Yes (all topics) |
| Create new articles | No | No | Yes | Yes | Yes (all topics) |
| Edit own drafts | No | No | Yes | Yes | Yes (all topics) |
| Edit others' content | No | In review | No | Yes | Yes (all topics) |
| Submit for review | No | No | Yes | Yes | Yes (all topics) |
| Approve/Reject | No | Yes | No | Yes | Yes (all topics) |
| Publish articles | No | Yes | No | Yes | Yes (all topics) |
| Manage resources | No | No | Topic | Topic | All topics |
| Manage users | No | No | No | Topic | All users |

---

## Editorial Workflow

### Article Status Flow

Articles progress through a defined workflow within each topic:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Article Lifecycle                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                          Analyst creates                                     │
│                               │                                              │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                           DRAFT                                          ││
│  │                                                                          ││
│  │  • Analyst can edit freely                                               ││
│  │  • Not visible to readers                                                ││
│  │  • Can be revised multiple times                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                               │                                              │
│                    Analyst submits for review                                │
│                               │                                              │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                          EDITOR                                          ││
│  │                                                                          ││
│  │  • Editor can review and edit                                            ││
│  │  • Analyst cannot edit (locked)                                          ││
│  │  • Not visible to readers                                                ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                               │                                              │
│             ┌─────────────────┼─────────────────┐                           │
│             │                                   │                            │
│      Editor rejects                      Editor approves                     │
│             │                                   │                            │
│             ▼                                   ▼                            │
│      Back to DRAFT                    ┌────────────────────────────────────┐│
│      (with feedback)                  │         PUBLISHED                   ││
│                                       │                                     ││
│                                       │  • Visible to all readers           ││
│                                       │  • Indexed for search               ││
│                                       │  • Available to chatbot             ││
│                                       │  • Generates HTML/PDF resources     ││
│                                       └────────────────────────────────────┘│
│                                                                              │
│                      Admin can recall to DRAFT for updates                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Status Transition Rules

| Current Status | Next Status | Who Can Do It | When |
|----------------|-------------|---------------|------|
| (new) | Draft | Analyst | Creating new article |
| Draft | Editor | Analyst | Submitting for review |
| Editor | Draft | Editor | Rejecting for revision |
| Editor | Published | Editor | Approving for publication |
| Published | Draft | Admin | Recalling for updates |

---

## AI Agent Specialization

### Topic-to-Agent Mapping

The multi-agent system routes queries to specialists based on topic expertise:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Query Routing                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User Query: "What's the impact of rising interest rates?"                 │
│                               │                                              │
│                               ▼                                              │
│                    ┌────────────────────┐                                   │
│                    │    Router Agent    │                                   │
│                    │                    │                                   │
│                    │  Analyzes query    │                                   │
│                    │  content and       │                                   │
│                    │  determines topic  │                                   │
│                    └─────────┬──────────┘                                   │
│                              │                                              │
│     ┌────────────────────────┼────────────────────────┐                    │
│     │                        │                        │                     │
│     ▼                        ▼                        ▼                     │
│ ┌───────────────┐    ┌───────────────┐    ┌───────────────┐                │
│ │  Economist    │    │    Equity     │    │ Fixed Income  │                │
│ │    Agent      │    │    Agent      │    │    Agent      │                │
│ │               │    │               │    │               │                │
│ │ Macro topics: │    │ Equity topics:│    │ FI topics:    │                │
│ │ • GDP         │    │ • Stocks      │    │ • Bonds       │                │
│ │ • Inflation   │    │ • Sectors     │    │ • Yields      │                │
│ │ • Rates       │    │ • Valuations  │    │ • Credit      │                │
│ └───────────────┘    └───────────────┘    └───────────────┘                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent Expertise Areas

| Agent | Topic Focus | Example Queries |
|-------|-------------|-----------------|
| **Economist Agent** | Macro | "What's driving inflation?", "Fed policy outlook", "GDP growth forecast" |
| **Equity Agent** | Equity | "Tech sector analysis", "Company valuation", "Earnings expectations" |
| **Fixed Income Agent** | Fixed Income | "Treasury yield curve", "Credit spreads", "Duration strategies" |

### Context Retrieval by Topic

When an agent responds, it retrieves relevant context from articles within the topic:

```
Query: "What's the outlook for Treasury yields?"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Fixed Income Agent activated                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Search ChromaDB for similar content                                      │
│     Filter: topic = "fixed_income", status = "published"                    │
│                                                                              │
│  2. Retrieve top 3-5 relevant articles:                                      │
│     • "Fed Rate Path and Treasury Implications"                             │
│     • "Credit Market Analysis Q3 2024"                                      │
│     • "Duration Management in Rising Rate Environment"                      │
│                                                                              │
│  3. Include article excerpts as context for LLM                             │
│                                                                              │
│  4. Generate response grounded in research content                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Resource Management by Topic

### Resource Ownership

Resources belong to topics through group association:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Resource Organization                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Macro Resources (macro:admin group)                                        │
│  ├── Economic indicator charts                                              │
│  ├── Central bank policy documents                                          │
│  ├── GDP forecast models                                                    │
│  └── Inflation data tables                                                  │
│                                                                              │
│  Equity Resources (equity:admin group)                                      │
│  ├── Company financial reports                                              │
│  ├── Valuation model templates                                              │
│  ├── Sector analysis documents                                              │
│  └── Earnings calendar data                                                 │
│                                                                              │
│  Fixed Income Resources (fixed_income:admin group)                          │
│  ├── Yield curve data                                                       │
│  ├── Credit spread charts                                                   │
│  ├── Duration analysis tools                                                │
│  └── Sovereign debt comparisons                                             │
│                                                                              │
│  Global Resources (global:admin group)                                      │
│  ├── System prompt templates                                                │
│  ├── Shared reference documents                                             │
│  └── Cross-topic datasets                                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Resource Access Rules

| User Has | Can Access Resources In |
|----------|------------------------|
| `macro:reader` | Macro resources linked to published articles |
| `macro:analyst` | All macro resources |
| `global:admin` | All resources across all topics |

---

## Frontend Topic Navigation

### URL Structure

The frontend uses topic-aware routing:

| Route Pattern | Purpose | Required Permission |
|---------------|---------|---------------------|
| `/analyst/{topic}` | Topic article list (analyst view) | `{topic}:analyst` or higher |
| `/analyst/edit/{id}` | Article editor | `{topic}:analyst` for the article's topic |
| `/editor/{topic}` | Topic article list (editor view) | `{topic}:editor` or higher |
| `/reader/{topic}` | Published articles | `{topic}:reader` or higher |

### Topic Selection

Users see only topics they have access to:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Topic Navigation                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User with: macro:analyst, equity:reader                                   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Analyst View:                                                      │   │
│   │  [Macro ✓]  [Equity ✗]  [Fixed Income ✗]  [ESG ✗]                 │   │
│   │                                                                     │   │
│   │  Only Macro is clickable - user can create/edit                    │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  Reader View:                                                       │   │
│   │  [Macro ✓]  [Equity ✓]  [Fixed Income ✗]  [ESG ✗]                 │   │
│   │                                                                     │   │
│   │  Both Macro and Equity clickable - user can read                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Topic Display Names

Topics are displayed with user-friendly names:

| Identifier | Display Name |
|------------|--------------|
| `macro` | Macroeconomic Research |
| `equity` | Equity Research |
| `fixed_income` | Fixed Income Research |
| `esg` | ESG Research |

---

## Topic Configuration

### Adding New Topics

To add a new research topic, the following must be configured:

1. **Create Groups**: Add `{topic}:admin`, `{topic}:analyst`, `{topic}:editor`, `{topic}:reader`
2. **Configure Router**: Update routing logic to recognize the new topic area
3. **Create Agent** (optional): Implement a specialized agent with domain tools
4. **Update Frontend**: Add topic to navigation and display configuration

### Topic Validation

The platform validates topic values to ensure data integrity:

| Validation | Rule |
|------------|------|
| Article creation | Topic must be in valid list |
| Resource assignment | Group must exist for topic |
| Permission check | Scope must match valid topic pattern |

---

## Integration Points

### Cross-Topic References

While articles belong to one topic, they can reference:
- Resources from other topics (if user has access)
- Articles from other topics (via links)
- Data that spans multiple domains

### Topic-Agnostic Features

Some features work across all topics:

| Feature | Behavior |
|---------|----------|
| **Global Search** | Searches published articles across all topics user can access |
| **Chatbot** | Can answer questions spanning multiple topics |
| **Admin Panel** | Shows all topics for global administrators |

---

## Related Documentation

- [Authorization](./02-authorization_concept.md) - Permission system
- [User Management](./04-user-management.md) - Group assignments
- [Resources](./10-resources-concept.md) - Topic-based resource organization
- [Multi-Agent Architecture](./08-multi-agent-architecture.md) - Topic-specific agents
