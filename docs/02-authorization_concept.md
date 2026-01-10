# Authorization

## Overview

The platform uses **role-based access control (RBAC)** with topic-scoped permissions. Users are assigned roles within specific topics (e.g., `macro:analyst`, `equity:editor`), and these roles determine what actions they can perform. Authorization is enforced at the API layer, agent tools, and UI actions.

---

## Scope Format

Permissions are encoded as **scopes** in the JWT token using the format `{topic}:{role}`:

| Example Scope | Description |
|---------------|-------------|
| `global:admin` | System-wide administrator with full access |
| `macro:admin` | Administrator for the Macro topic |
| `macro:analyst` | Analyst with content creation access for Macro |
| `equity:editor` | Editor with publishing rights for Equity |
| `fixed_income:reader` | Read-only access to Fixed Income content |

Users can have multiple scopes: `["macro:analyst", "equity:reader", "esg:analyst"]`

---

## Role Hierarchy

Roles follow a hierarchy where higher roles inherit lower role permissions:

```
                    global:admin
                         │
        (Full access to all topics and system settings)
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
    ▼                    ▼                    ▼
{topic}:admin      {topic}:admin       {topic}:admin
    │                    │                    │
    │  (Full topic control: all roles + admin actions)
    │
    ├──────────────┬──────────────┐
    │              │              │
    ▼              ▼              ▼
{topic}:analyst  {topic}:editor  {topic}:reader
    │              │              │
    │              │              │
    │              │    (View published content,
    │              │     search, rate, chat)
    │              │
    │    (Review articles, request
    │     changes, publish)
    │
(Create articles, edit drafts,
 research, submit for review)
```

### Role Levels

| Role | Level | Inherits From | Primary Function |
|------|-------|---------------|------------------|
| `admin` | 4 | analyst, editor, reader | Topic management |
| `analyst` | 3 | reader | Content creation |
| `editor` | 2 | reader | Content review & publishing |
| `reader` | 1 | - | Content consumption |

**Note:** Analyst and Editor are parallel roles (neither inherits from the other). Admin inherits from both.

---

## Role Capabilities

### Reader (`{topic}:reader`)

| Capability | Description |
|------------|-------------|
| View published articles | Browse and read published content |
| Search articles | Full-text and semantic search |
| Rate articles | Submit 1-5 star ratings |
| Download PDF | Export articles as PDF |
| Chat interaction | Ask questions, get recommendations |

### Analyst (`{topic}:analyst`)

All Reader capabilities, plus:

| Capability | Description |
|------------|-------------|
| Create articles | Start new draft articles |
| Edit own drafts | Modify articles in DRAFT status |
| Regenerate content | Use AI to regenerate headline, content, keywords |
| Create resources | Upload and manage article resources |
| Research | Web search, data retrieval for articles |
| Submit for review | Move article from DRAFT to EDITOR status |

### Editor (`{topic}:editor`)

All Reader capabilities, plus:

| Capability | Description |
|------------|-------------|
| View pending articles | See articles in EDITOR status |
| Review articles | Read and evaluate submitted articles |
| Request changes | Send article back to analyst (EDITOR to DRAFT) |
| Publish articles | Approve and publish (with HITL confirmation) |
| Download PDF | Generate PDFs for review |

### Topic Admin (`{topic}:admin`)

All Analyst and Editor capabilities, plus:

| Capability | Description |
|------------|-------------|
| Recall articles | Unpublish article (PUBLISHED to DRAFT) |
| Deactivate articles | Hide article from readers |
| Reactivate articles | Restore deactivated article |
| Purge articles | Permanently delete article |
| Manage topic users | Assign roles within the topic |

### Global Admin (`global:admin`)

All Topic Admin capabilities for all topics, plus:

| Capability | Description |
|------------|-------------|
| Manage topics | Create, edit, delete topics |
| Manage all users | Assign any role to any user |
| Manage groups | Create and configure user groups |
| System prompts | Edit AI system prompts |
| Tonality settings | Configure content tone options |

---

## Permission Check Flow

When a protected endpoint is accessed:

```
API Request to /api/analyst/{topic}/article/{id}
                    │
                    ▼
            ┌───────────────────┐
            │ 1. Validate JWT   │
            │    (signature,    │
            │     expiration)   │
            └─────────┬─────────┘
                      │
                      ▼
            ┌───────────────────┐
            │ 2. Check Redis    │
            │    Token Registry │
            └─────────┬─────────┘
                      │
                      ▼
            ┌───────────────────┐
            │ 3. Has            │
            │    global:admin?  │──── Yes ───► GRANT ACCESS
            └─────────┬─────────┘
                      │ No
                      ▼
            ┌───────────────────────┐
            │ 4. Has {topic}:admin  │
            │    or {topic}:analyst?│──── Yes ───► GRANT ACCESS
            └─────────┬─────────────┘
                      │ No
                      ▼
                 DENY (403)
```

### Check Order

1. **JWT Validation** - Token signature and expiration verified
2. **Token Registry** - Token ID must exist in Redis (revocation check)
3. **Global Admin Bypass** - `global:admin` grants immediate access
4. **Topic Admin Check** - `{topic}:admin` grants access for that topic
5. **Role Check** - User must have required role level for the topic
6. **Denial** - No matching scope results in 403 Forbidden

---

## Article Access Rules

### By Status

| Article Status | Who Can View | Who Can Edit |
|----------------|--------------|--------------|
| **DRAFT** | Author, topic analysts, admins | Author, topic admin |
| **EDITOR** | Author, topic editors, admins | Topic editor (for feedback) |
| **PENDING_APPROVAL** | Topic editors, admins | Nobody (awaiting HITL) |
| **PUBLISHED** | All authenticated users | Nobody (recall first) |
| **DEACTIVATED** | Topic admins, global admin | Topic admin (to reactivate) |

### Status Transitions

```
DRAFT ──────────────────────────────────────────────────────┐
  │                                                         │
  │ submit_for_review() [analyst]                           │
  ▼                                                         │
EDITOR ◄────────────────────────────────────────────────────┤
  │                                                         │
  │ publish() [editor]          reject() [editor]           │
  ▼                                  │                      │
PENDING_APPROVAL                     └──────────────────────┘
  │
  │ HITL approve                HITL reject
  ▼                                  │
PUBLISHED ◄──────────────────────────┘
  │
  │ recall() [admin]
  ▼
DRAFT (back to beginning)
```

---

## API Endpoint Authorization

### URL Prefix Patterns

| Prefix | Required Role | Description |
|--------|---------------|-------------|
| `/api/reader/...` | Any authenticated | Read operations |
| `/api/analyst/{topic}/...` | `{topic}:analyst` | Content creation |
| `/api/editor/{topic}/...` | `{topic}:editor` | Editorial operations |
| `/api/admin/...` | `global:admin` | System administration |
| `/api/resources/{hash}` | Public | Resource access |

### Common Endpoints

| Endpoint | Required Role | Description |
|----------|---------------|-------------|
| `GET /api/reader/articles` | Any authenticated | List published articles |
| `POST /api/analyst/{topic}/article` | `{topic}:analyst` | Create draft |
| `PUT /api/analyst/{topic}/article/{id}` | `{topic}:analyst` | Edit draft |
| `POST /api/analyst/{topic}/article/{id}/submit` | `{topic}:analyst` | Submit for review |
| `GET /api/editor/{topic}/pending` | `{topic}:editor` | List pending articles |
| `POST /api/editor/{topic}/article/{id}/publish` | `{topic}:editor` | Publish article |
| `POST /api/editor/{topic}/article/{id}/reject` | `{topic}:editor` | Reject article |
| `POST /api/admin/article/{id}/recall` | `{topic}:admin` | Recall published |
| `DELETE /api/admin/article/{id}` | `{topic}:admin` | Purge article |

---

## Agent Tool Permissions

The multi-agent system enforces permissions at the tool level:

### Tool Permission Metadata

| Metadata | Purpose |
|----------|---------|
| `required_role` | Minimum role to use the tool |
| `topic_scoped` | Whether topic permission is required |
| `global_admin_override` | Whether `global:admin` bypasses checks |
| `requires_hitl` | Whether tool triggers human approval |

### Tool Examples

| Tool | Required Role | Topic Scoped | HITL |
|------|---------------|--------------|------|
| `search_articles` | reader | Yes | No |
| `get_article` | reader | No | No |
| `create_article` | analyst | Yes | No |
| `edit_article` | analyst | Yes | No |
| `web_search` | analyst | No | No |
| `submit_for_review` | analyst | Yes | No |
| `request_changes` | editor | Yes | No |
| `publish_article` | editor | Yes | **Yes** |
| `recall_article` | admin | Yes | No |

### Runtime Tool Filtering

When an agent is invoked:
1. User's scopes extracted from JWT
2. Tool registry filtered to permitted tools only
3. Agent sees only authorized tools
4. Attempting unauthorized tool results in error

---

## UI Action Permissions

Frontend UI actions are also permission-controlled:

### Navigation Actions

| Action | Required Role | Description |
|--------|---------------|-------------|
| `goto_home` | Any authenticated | Navigate to home |
| `goto_analyst` | `{topic}:analyst` (any) | Navigate to analyst hub |
| `goto_editor` | `{topic}:editor` (any) | Navigate to editor hub |
| `goto_topic_admin` | `{topic}:admin` (any) | Navigate to topic admin |
| `goto_admin_global` | `global:admin` | Navigate to global admin |

### Editor Actions (in analyst section)

| Action | Required Role | Context |
|--------|---------------|---------|
| `save_draft` | `{topic}:analyst` | Topic-scoped |
| `submit_for_review` | `{topic}:analyst` | Topic-scoped |
| `browse_resources` | `{topic}:analyst` | Topic-scoped |

### Editorial Actions (in editor section)

| Action | Required Role | Context |
|--------|---------------|---------|
| `publish_article` | `{topic}:editor` | Topic-scoped |
| `reject_article` | `{topic}:editor` | Topic-scoped |

### Admin Actions

| Action | Required Role | Context |
|--------|---------------|---------|
| `delete_article` | `{topic}:admin` | Requires confirmation |
| `recall_article` | `{topic}:admin` | Requires confirmation |
| `purge_article` | `{topic}:admin` | Requires confirmation |

---

## Error Responses

| HTTP Status | Meaning | User Action |
|-------------|---------|-------------|
| 401 Unauthorized | Invalid/expired token | Re-authenticate |
| 403 Forbidden | Insufficient permissions | Request access from admin |
| 404 Not Found | Resource not visible | Check topic access |

### Permission Error Messages

- "Analyst access required for {topic}" - Need `{topic}:analyst` scope
- "Editor access required for {topic}" - Need `{topic}:editor` scope
- "Admin access required" - Need `global:admin` scope
- "Article belongs to different topic" - Article-topic mismatch

---

## Example Token Scopes

### Analyst User

```json
{
  "scopes": ["macro:analyst", "equity:reader"]
}
```

Can:
- Create/edit articles in Macro topic
- Read published articles in Equity topic
- Use chat with context from both topics

### Editor User

```json
{
  "scopes": ["macro:editor", "equity:editor"]
}
```

Can:
- Review and publish articles in Macro and Equity
- Read all content in both topics
- Cannot create new articles

### Multi-Role User

```json
{
  "scopes": ["macro:analyst", "equity:editor", "esg:admin"]
}
```

Can:
- Create articles in Macro
- Publish articles in Equity
- Full admin control in ESG

---

## Related Documentation

- [Authentication](./01-authentication.md) - OAuth flow and JWT tokens
- [User Management](./04-user-management.md) - Group assignments
- [Multi-Agent Architecture](./08-multi-agent-architecture.md) - Agent tool permissions
- [User Workflows](./13-user-workflows.md) - Role-specific workflows
