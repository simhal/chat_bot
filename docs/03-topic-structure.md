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
+-----------------------------------------------------------------------------+
|                           Platform Content                                   |
+-----------------------------------------------------------------------------+
|                                                                              |
|  +---------------+  +---------------+  +---------------+  +--------------+  |
|  |    Macro      |  |    Equity     |  | Fixed Income  |  |     ESG      |  |
|  +---------------+  +---------------+  +---------------+  +--------------+  |
|  |               |  |               |  |               |  |              |  |
|  | - Inflation   |  | - Tech sector |  | - Treasury    |  | - Carbon     |  |
|  |   outlook     |  |   analysis    |  |   yields      |  |   markets    |  |
|  |               |  |               |  |               |  |              |  |
|  | - GDP growth  |  | - Earnings    |  | - Credit      |  | - ESG        |  |
|  |   forecast    |  |   previews    |  |   spreads     |  |   ratings    |  |
|  |               |  |               |  |               |  |              |  |
|  | - Central     |  | - IPO         |  | - Duration    |  | - Green      |  |
|  |   bank policy |  |   analysis    |  |   strategies  |  |   bonds      |  |
|  |               |  |               |  |               |  |              |  |
|  +---------------+  +---------------+  +---------------+  +--------------+  |
|                                                                              |
+-----------------------------------------------------------------------------+
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

Each topic has four permission levels forming a hierarchy: reader, analyst, editor, and admin. The `global:admin` role transcends topic boundaries with access to all topics.

| Role Level | Key Capabilities |
|------------|------------------|
| **Reader** | View published articles, access chatbot |
| **Analyst** | Create drafts, edit own content, submit for review |
| **Editor** | Review submissions, approve/reject, publish articles |
| **Admin** | Full topic control, manage users and resources |

For detailed role definitions, capabilities matrix, and scope format, see Authorization documentation.

---

## Article Workflow Summary

Articles progress through a defined workflow within each topic:

| Status | Description |
|--------|-------------|
| **Draft** | Analyst creates and edits; not visible to readers |
| **Editor** | Under editorial review; analyst cannot edit |
| **Published** | Visible to all readers; indexed for search |

Editors can approve articles for publication or reject them back to draft status with feedback. Admins can recall published articles for updates.

For detailed workflow diagrams and transition rules, see User Workflows documentation.

---

## Resource Management by Topic

### Resource Ownership

Resources belong to topics through group association:

| Topic | Example Resources |
|-------|-------------------|
| **Macro** | Economic indicator charts, central bank documents, GDP forecasts |
| **Equity** | Company financial reports, valuation models, sector analysis |
| **Fixed Income** | Yield curve data, credit spread charts, duration tools |
| **Global** | System prompt templates, shared reference documents |

### Resource Access Rules

| User Has | Can Access Resources In |
|----------|------------------------|
| `macro:reader` | Macro resources linked to published articles |
| `macro:analyst` | All macro resources |
| `global:admin` | All resources across all topics |

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

- Authorization (02-authorization_concept.md) - Permission system, role definitions, scope format
- User Management (04-user-management.md) - Group assignments
- User Workflows (13-user-workflows.md) - Detailed editorial workflow diagrams
- Resources (09-resources-concept.md) - Topic-based resource organization
- Multi-Agent Architecture (08-multi-agent-architecture.md) - Topic-specific agents, query routing
- Frontend (12-frontend.md) - Topic navigation, URL structure
