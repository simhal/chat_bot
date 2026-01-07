# Authorization & Permissions

## Overview

The platform uses a **role-based access control (RBAC)** system with topic-scoped permissions. Users are assigned roles within specific topics, and these roles determine what actions they can perform. The permission model is enforced at both the API layer and the agent system.

---

## Scope Format

Permissions are encoded as **scopes** in the format `{topic}:{role}`:

| Example Scope | Description |
|---------------|-------------|
| `global:admin` | System-wide administrator with full access |
| `macro:admin` | Administrator for the Macro topic |
| `macro:analyst` | Analyst with content creation access for Macro |
| `equity:editor` | Editor with publishing rights for Equity |
| `fixed_income:reader` | Read-only access to Fixed Income content |

Users can have multiple scopes, e.g., `["macro:analyst", "equity:reader", "esg:analyst"]`.

---

## Role Hierarchy

The role hierarchy defines which roles inherit permissions from lower roles:

```
global:admin
    │
    │  (Full access to all topics and system settings)
    │
    └── {topic}:admin
            │
            │  (Full access within the topic)
            │
            ├── {topic}:analyst
            │       │
            │       │  (Create and edit articles, research)
            │       │
            │       └── {topic}:reader
            │               │
            │               │  (View published content)
            │
            └── {topic}:editor
                    │
                    │  (Review and publish articles)
                    │
                    └── {topic}:reader
                            │
                            │  (View published content)
```

### Role Levels

| Role | Level | Inherits From |
|------|-------|---------------|
| `admin` | 4 | analyst, editor, reader |
| `analyst` | 3 | reader |
| `editor` | 2 | reader |
| `reader` | 1 | - |

A higher-level role can perform all actions of lower-level roles within the same topic.

---

## Permission Checks

### API Endpoint Structure

The API uses role-based URL prefixes:

| Prefix | Required Role | Description |
|--------|---------------|-------------|
| `/api/reader/{topic}/...` | Any authenticated user | Read operations |
| `/api/analyst/{topic}/...` | `{topic}:analyst` or higher | Content creation |
| `/api/editor/{topic}/...` | `{topic}:editor` or higher | Editorial operations |
| `/api/admin/...` | `global:admin` | System administration |
| `/api/resources/{hash}` | None (public) | Public resource access |

### Permission Check Logic

When a protected endpoint is accessed:

1. **JWT Validation**: Token signature and expiration verified
2. **Token Registry Check**: Token ID must exist in Redis (for revocation support)
3. **Global Admin Bypass**: If user has `global:admin`, access granted
4. **Topic Admin Check**: If user has `{topic}:admin`, access granted for that topic
5. **Role Check**: User must have the required role level for the topic
6. **Denial**: If no matching scope, request rejected with 403 Forbidden

### Permission Check Flow

```
Request to /api/analyst/{topic}/article/{id}
                    │
                    ▼
            ┌───────────────────┐
            │ Extract JWT Token │
            └─────────┬─────────┘
                      │
                      ▼
            ┌───────────────────┐
            │ Validate Token    │
            │ (signature, exp)  │
            └─────────┬─────────┘
                      │
                      ▼
            ┌───────────────────┐
            │ Check Redis       │
            │ Token Registry    │
            └─────────┬─────────┘
                      │
                      ▼
            ┌───────────────────┐
            │ Has global:admin? │──── Yes ───► GRANT ACCESS
            └─────────┬─────────┘
                      │ No
                      ▼
            ┌───────────────────────┐
            │ Has {topic}:admin or  │
            │ {topic}:analyst?      │──── Yes ───► GRANT ACCESS
            └─────────┬─────────────┘
                      │ No
                      ▼
                 DENY (403)
```

---

## Role Capabilities

### By Operation

| Operation | Required Role | Topic Scoped |
|-----------|---------------|--------------|
| View published articles | Any authenticated | Yes |
| Search articles | Any authenticated | Yes |
| Rate articles | Any authenticated | Yes |
| Download PDF | Any authenticated | Yes |
| Create draft article | `{topic}:analyst` | Yes |
| Edit draft article | `{topic}:analyst` | Yes |
| Create resources | `{topic}:analyst` | Yes |
| Submit for review | `{topic}:analyst` | Yes |
| View drafts (as editor) | `{topic}:editor` | Yes |
| Request changes | `{topic}:editor` | Yes |
| Publish article | `{topic}:editor` | Yes |
| Recall published article | `{topic}:admin` | Yes |
| Deactivate article | `{topic}:admin` | Yes |
| Purge article | `{topic}:admin` | Yes |
| Manage topics | `global:admin` | No |
| Manage users | `global:admin` | No |
| Manage system prompts | `global:admin` | No |

### By Role

| Role | Capabilities |
|------|--------------|
| **Reader** | View published articles, search, rate, download PDFs, use chat |
| **Analyst** | All Reader + create articles, edit own drafts, create resources, submit for review |
| **Editor** | Reader + view pending articles, request changes, publish articles |
| **Topic Admin** | All Analyst + Editor + recall articles, deactivate, purge, manage topic users |
| **Global Admin** | All Topic Admin for all topics + manage system settings, topics, users, prompts |

---

## Agent Tool Permissions

The multi-agent system also enforces permissions at the tool level:

### Tool Registry

All agent tools are registered with permission metadata:

| Metadata | Purpose |
|----------|---------|
| `required_role` | Minimum role to use the tool |
| `topic_scoped` | Whether topic permission is required |
| `global_admin_override` | Whether global:admin bypasses checks |
| `requires_hitl` | Whether tool triggers human approval |

### Runtime Tool Filtering

When an agent is invoked:

1. User's scopes are extracted from UserContext
2. Tool registry is filtered to include only permitted tools
3. Agent sees only tools the user is authorized to use
4. Attempting to use a filtered tool results in an error

### Example Tool Permissions

| Tool | Required Role | Topic Scoped |
|------|---------------|--------------|
| `search_articles` | reader | Yes |
| `get_article` | reader | No |
| `create_article` | analyst | Yes |
| `edit_article` | analyst | Yes |
| `web_search` | analyst | No |
| `create_resource` | analyst | Yes |
| `submit_for_review` | analyst | Yes |
| `request_changes` | editor | Yes |
| `publish_article` (HITL) | editor | Yes |
| `recall_article` | admin | Yes |

---

## Article Access Rules

Articles have topic-based access controls:

### Read Access

| Article Status | Who Can View |
|----------------|--------------|
| DRAFT | Author, topic analysts, topic admins, global admin |
| EDITOR | Author, topic editors, topic admins, global admin |
| PUBLISHED | All authenticated users with topic access |
| DEACTIVATED | Topic admins, global admin only |

### Write Access

| Action | Who Can Perform |
|--------|-----------------|
| Create draft | Topic analyst or higher |
| Edit draft | Article author, topic admin, global admin |
| Submit for review | Article author, topic analyst |
| Request changes | Topic editor or higher |
| Publish | Topic editor or higher |
| Recall | Topic admin or higher |
| Deactivate | Topic admin or higher |
| Purge | Topic admin or higher |

---

## JWT Token Scopes

User scopes are embedded in the JWT access token:

### Token Claims

| Claim | Description |
|-------|-------------|
| `sub` | User's unique identifier |
| `email` | User's email address |
| `name` | User's display name |
| `scopes` | Array of permission scopes |
| `jti` | Token ID (for revocation lookup) |
| `exp` | Expiration timestamp |

### Example Token Scopes

```json
{
  "sub": "user-uuid-123",
  "email": "analyst@example.com",
  "name": "Jane Analyst",
  "scopes": ["macro:analyst", "equity:reader"],
  "jti": "token-id-456",
  "exp": 1704067200
}
```

This user can:
- Create/edit articles in Macro topic
- Read published articles in Equity topic
- Use chat with context from both topics

---

## Error Responses

| HTTP Status | Meaning | User Action |
|-------------|---------|-------------|
| 401 Unauthorized | Invalid or expired token | Re-authenticate |
| 403 Forbidden | Insufficient permissions | Request access from admin |
| 404 Not Found | Resource doesn't exist or not visible | Check topic access |

### Permission Error Messages

- "Analyst access required for {topic}" - Need `{topic}:analyst` scope
- "Editor access required for {topic}" - Need `{topic}:editor` scope
- "Admin access required" - Need `global:admin` scope
- "Article belongs to different topic" - Article-topic mismatch

---

## Related Documentation

- [Authentication](./01-authentication.md) - OAuth flow and JWT tokens
- [User Management](./04-user-management.md) - Group assignments
- [Multi-Agent Architecture](./08-multi-agent-architecture.md) - Tool permissions
- [UI Actions](./15-ui-actions.md) - Page access requirements
