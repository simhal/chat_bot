# Sections & Navigation

This document describes the navigation section system used throughout the application. Sections define the structure of the frontend routes and available UI actions.

## Table of Contents

1. [Overview](#overview)
2. [Shared Configuration](#shared-configuration)
3. [Section Definitions](#section-definitions)
4. [Global Actions](#global-actions)
5. [Section-Specific Actions](#section-specific-actions)
6. [Navigation Context](#navigation-context)
7. [URL Routing](#url-routing)
8. [Backend Integration](#backend-integration)

---

## Overview

The application uses a unified section-based navigation system where:

- **Sections** define distinct areas of the application (e.g., `reader_topic`, `analyst_dashboard`)
- **Global actions** are available everywhere (goto, select_topic, select_article, logout)
- **Section-specific actions** are available only within their respective sections
- Configuration is shared between frontend and backend via JSON files

### Design Principles

1. **Combined section names** - Section names combine area + view (e.g., `reader_topic`, `analyst_dashboard`)
2. **Explicit flags** - Each section has `requires_topic` and `requires_article` booleans
3. **Defined UI actions** - Each section has a list of available UI actions
4. **Single source of truth** - Configuration in `shared/` directory used by both frontend and backend

---

## Shared Configuration

Configuration is stored in two JSON files in the `shared/` directory:

### `shared/sections.json`

Contains section definitions:

```json
{
  "sections": {
    "home": {
      "name": "Home",
      "route": "/",
      "required_role": "any",
      "requires_topic": false,
      "requires_article": false,
      "ui_actions": []
    },
    "reader_topic": {
      "name": "Topic Articles",
      "route": "/reader/[topic]",
      "required_role": "{topic}:reader",
      "requires_topic": true,
      "requires_article": false,
      "ui_actions": ["open_article", "search_articles"]
    }
  }
}
```

### `shared/ui_actions.json`

Contains action definitions:

```json
{
  "global_actions": [
    {
      "action": "goto",
      "description": "Navigate to any section",
      "params": {
        "section": { "type": "string", "required": true },
        "topic": { "type": "string", "required": false },
        "article_id": { "type": "number", "required": false }
      }
    }
  ],
  "section_actions": {
    "open_article": {
      "description": "Open article modal",
      "params": {
        "article_id": { "type": "number", "required": true }
      }
    }
  }
}
```

---

## Section Definitions

### All Sections

| Section | Name | Route | Required Role | Topic | Article |
|---------|------|-------|---------------|-------|---------|
| `home` | Home | `/` | any | No | No |
| `reader_search` | Search | `/reader/search` | any | No | No |
| `reader_topic` | Topic Articles | `/reader/[topic]` | {topic}:reader | Yes | No |
| `reader_article` | Article View | `/reader/[topic]/article/[id]` | {topic}:reader | Yes | Yes |
| `analyst_dashboard` | Analyst Dashboard | `/analyst/[topic]` | {topic}:analyst | Yes | No |
| `analyst_editor` | Article Editor | `/analyst/[topic]/edit/[id]` | {topic}:analyst | Yes | Yes |
| `analyst_article` | Article Preview | `/analyst/[topic]/article/[id]` | {topic}:analyst | Yes | Yes |
| `editor_dashboard` | Editor Dashboard | `/editor/[topic]` | {topic}:editor | Yes | No |
| `editor_article` | Article Review | `/editor/[topic]/article/[id]` | {topic}:editor | Yes | Yes |
| `admin_articles` | Article Management | `/admin/[topic]/articles` | {topic}:admin | Yes | No |
| `admin_resources` | Resource Management | `/admin/[topic]/resources` | {topic}:admin | Yes | No |
| `admin_prompts` | Topic Prompts | `/admin/[topic]/prompts` | {topic}:admin | Yes | No |
| `root_users` | User Management | `/root/users` | global:admin | No | No |
| `root_groups` | Group Management | `/root/groups` | global:admin | No | No |
| `root_topics` | Topic Management | `/root/topics` | global:admin | No | No |
| `root_prompts` | Global Prompts | `/root/prompts` | global:admin | No | No |
| `root_tonalities` | Tonality Options | `/root/tonalities` | global:admin | No | No |
| `root_resources` | Global Resources | `/root/resources` | global:admin | No | No |
| `user_profile` | My Profile | `/user/profile` | any | No | No |
| `user_settings` | Settings | `/user/settings` | any | No | No |

### Column Legend

- **Required Role**: `any` = any authenticated, `{topic}:role` = topic-specific role, `global:admin` = global admin
- **Topic**: Yes = requires `{topic}` parameter, No = no topic needed
- **Article**: Yes = requires `{article_id}` parameter, No = no article needed

### Section Prefixes and Roles

Section names follow the pattern `{role}_{view}`:

| Prefix | Role | Description |
|--------|------|-------------|
| `reader_` | reader | Read-only article access |
| `analyst_` | analyst | Content creation |
| `editor_` | editor | Editorial review |
| `admin_` | admin | Topic administration |
| `root_` | admin | Global administration |
| `user_` | any | User profile/settings |
| `home` | reader | Landing page |

---

## Global Actions

Available in all sections:

| Action | Description | Parameters |
|--------|-------------|------------|
| `goto` | Navigate to any section | `section` (required), `topic`, `article_id` |
| `goto_back` | Navigate to previous page | - |
| `select_topic` | Change current topic context | `topic` (required) |
| `select_article` | Select/highlight an article | `article_id` (required) |
| `logout` | Log out user | - |

### The `goto` Action

The unified `goto` action handles all navigation. Parameters depend on the target section:

```json
// Navigate to home
{ "action": "goto", "params": { "section": "home" } }

// Navigate to advanced search page
{ "action": "goto", "params": { "section": "reader_search" } }

// Navigate to reader topic (e.g., "goto macro", "take me to Test")
{ "action": "goto", "params": { "section": "reader_topic", "topic": "macro" } }

// Navigate to article editor
{ "action": "goto", "params": { "section": "analyst_editor", "topic": "equity", "article_id": 123 } }

// Navigate to global admin
{ "action": "goto", "params": { "section": "root_users" } }
```

### Navigation Action Types

The backend maps chat requests to these internal navigation types:

| Internal Type | Target Section | Example Chat Messages |
|---------------|----------------|----------------------|
| `goto_back` | (previous page) | "go back", "back", "previous page" |
| `goto_home` | `home` | "go home", "main page" |
| `goto_search` | `reader_search` | "go to search", "open search" |
| `goto_reader_topic` | `reader_topic` | "goto macro", "take me to Test", "show equity articles" |
| `goto_analyst_topic` | `analyst_dashboard` | "analyst dashboard", "my articles" |
| `goto_editor_topic` | `editor_dashboard` | "editor queue", "review articles" |
| `goto_admin_topic` | `admin_articles` | "admin panel", "topic admin" |
| `goto_root` | `root_users` | "global admin", "manage users" |
| `goto_user_profile` | `user_profile` | "my profile", "profile page" |
| `goto_user_settings` | `user_settings` | "settings", "my settings" |

**Go Back:** The `goto_back` action uses browser history to return to the previous page. If no history exists, it navigates to home.

**Topic Detection:** When navigating to `reader_topic`, the system detects topic names from the message. All active topics are navigable regardless of `access_mainchat` setting.

---

## Section-Specific Actions

### Reader Sections

**reader_search:**
- `search_articles` - Execute search with query
- `clear_search` - Clear search filters
- `open_article` - Open article modal

**reader_topic:**
- `open_article` - Open article modal
- `search_articles` - Search within topic

**reader_article:**
- `close_modal` - Close article modal
- `rate_article` - Rate the article (1-5)
- `download_pdf` - Download article as PDF

### Analyst Sections

**analyst_dashboard:**
- `create_article` - Create new article
- `edit_article` - Open article in editor
- `open_article` - Preview article
- `delete_article` - Delete draft article
- `submit_article` - Submit article for review

**analyst_editor:**
- `save_draft` - Save current changes
- `submit_for_review` - Submit to editor queue
- `switch_view_editor` - Switch to markdown editor tab
- `switch_view_preview` - Switch to preview tab
- `switch_view_resources` - Switch to resources tab
- `link_resource` - Link resource to article
- `unlink_resource` - Unlink resource from article
- `browse_resources` - Open resource browser

**analyst_article:**
- `close_modal` - Close article modal
- `edit_article` - Open in editor

### Editor Sections

**editor_dashboard:**
- `open_article` - Preview article
- `publish_article` - Publish article
- `reject_article` - Reject and return to analyst

**editor_article:**
- `close_modal` - Close article modal
- `publish_article` - Publish article
- `reject_article` - Reject and return to analyst
- `download_pdf` - Download article as PDF

### Admin Sections

**admin_articles:**
- `deactivate_article` - Soft delete article
- `reactivate_article` - Restore deactivated article
- `recall_article` - Return published article to draft
- `purge_article` - Permanently delete article

**admin_resources:**
- `delete_resource` - Delete resource
- `upload_resource` - Upload new resource

**admin_prompts:**
- `edit_prompt` - Edit topic prompt
- `save_prompt` - Save prompt changes

### Root (Global Admin) Sections

**root_users:**
- `create_user` - Create new user
- `ban_user` - Ban user
- `unban_user` - Unban user
- `delete_user` - Delete user
- `assign_group` - Assign user to group
- `remove_group` - Remove user from group

**root_groups:**
- `create_group` - Create new group
- `delete_group` - Delete group
- `assign_user` - Add user to group
- `remove_user` - Remove user from group

**root_topics:**
- `create_topic` - Create new topic
- `edit_topic` - Edit topic settings
- `delete_topic` - Delete topic
- `reorder_topics` - Change topic order

**root_prompts:**
- `edit_prompt` - Edit global prompt
- `save_prompt` - Save prompt changes

**root_tonalities:**
- `create_tonality` - Create new tonality option
- `edit_tonality` - Edit tonality
- `delete_tonality` - Delete tonality
- `set_default` - Set default tonality

**root_resources:**
- `delete_resource` - Delete global resource
- `upload_resource` - Upload new resource

### User Sections

**user_profile:**
- (view only - no specific actions)

**user_settings:**
- `save_tonality` - Save tonality preferences
- `delete_account` - Delete user account

---

## Navigation Context

The navigation context tracks the user's current location and is sent with each chat message.

### Context Structure

```typescript
interface NavigationContext {
  section: SectionName;          // Current section (e.g., 'analyst_editor')
  topic: string | null;          // Topic slug (e.g., 'macro')
  articleId: number | null;      // Article ID
  articleHeadline: string | null;
  articleKeywords: string | null;
  articleStatus: string | null;  // 'draft', 'editor', 'published'
  resourceId: number | null;
  resourceName: string | null;
  resourceType: string | null;
  viewMode: string | null;       // 'editor', 'preview', 'resources'
}
```

### API Payload

When sending to the backend, the context is converted to snake_case:

```json
{
  "section": "analyst_editor",
  "topic": "macro",
  "article_id": 42,
  "article_headline": "Q4 Outlook",
  "article_status": "draft",
  "view_mode": "editor"
}
```

---

## URL Routing

### Route Patterns

Routes use SvelteKit's file-based routing with dynamic segments:

| Pattern | Example | Section |
|---------|---------|---------|
| `/` | `/` | home |
| `/reader/search` | `/reader/search` | reader_search |
| `/reader/[topic]` | `/reader/macro` | reader_topic |
| `/reader/[topic]/article/[id]` | `/reader/macro/article/42` | reader_article |
| `/analyst/[topic]` | `/analyst/equity` | analyst_dashboard |
| `/analyst/[topic]/edit/[id]` | `/analyst/equity/edit/15` | analyst_editor |
| `/editor/[topic]` | `/editor/macro` | editor_dashboard |
| `/admin/[topic]/articles` | `/admin/macro/articles` | admin_articles |
| `/root/users` | `/root/users` | root_users |
| `/user/profile` | `/user/profile` | user_profile |

### Redirect Routes

These routes redirect to default sections:

| Route | Redirects To |
|-------|--------------|
| `/reader` | `/reader/[first-entitled-topic]` |
| `/analyst` | `/analyst/[first-entitled-topic]` |
| `/editor` | `/editor/[first-entitled-topic]` |
| `/admin` | `/admin/[first-entitled-topic]/articles` |
| `/admin/[topic]` | `/admin/[topic]/articles` |
| `/root` | `/root/users` |
| `/user` | `/user/profile` |

---

## Backend Integration

### State Module

The backend loads configuration from the shared JSON files at startup:

```python
from agents.builds.v2.state import (
    SECTION_CONFIG,           # Section definitions from shared/sections.json
    GLOBAL_ACTIONS,           # Global action configs from shared/ui_actions.json
    ACTION_CONFIG,            # Section action configs from shared/ui_actions.json
    get_section_actions,      # Get full action configs for a section
    get_section_action_names, # Get just action names for a section
)
```

### Action Validator Module

The action validator uses section configuration to enforce action permissions:

```python
from agents.builds.v2.action_validator import (
    validate_action,          # Check if action allowed in section
    validate_action_for_role, # Check action + role combination
    is_action_allowed_globally, # Check if global action
    is_navigation_action,     # Check if goto navigation action
    find_sections_with_action, # Find sections where action available
    get_role_from_section,    # Extract role from section prefix
    detect_content_action,    # Detect content action from message
    is_content_request,       # Check if content-related request
    is_resource_request,      # Check if resource-related request
    ALWAYS_ALLOWED_ACTIONS,   # Global actions list
    ROLE_HIERARCHY,           # Role level mapping
)
```

### Router Node

The router extracts the user's role from the section name for routing decisions:

```python
def _extract_role_from_section(section: str) -> str:
    """Extract role from section name prefix."""
    if not section:
        return "reader"

    prefix = section.split("_")[0] if "_" in section else section
    role_map = {
        "reader": "reader",
        "analyst": "analyst",
        "editor": "editor",
        "admin": "admin",
        "root": "admin",   # root_ sections map to admin role
        "user": "user",    # user_ sections get user node
        "home": "reader"   # home gets reader role
    }
    return role_map.get(prefix, "reader")
```

**Routing Priority:**
1. Navigation intent → ALWAYS routes to `navigation_node`
2. Entitlements intent → routes to `user_node`
3. User/profile sections → routes to `user_node`
4. Role-based routing → routes to corresponding role node (reader, analyst, editor, admin)
5. Fallback → routes to `general_chat_node`

### Navigation Node

The navigation node handles all `goto` actions with **TARGET-based permission checking**:

```python
def _check_navigation_permission(target_action: str, user_context: dict, topic: str = None):
    """
    Check permission to navigate to TARGET section.

    CRITICAL: Permission check is on the TARGET section, NOT the current section.
    Users can ALWAYS try to navigate from any page.
    """
    config = NAVIGATION_PERMISSIONS.get(target_action)
    if not config:
        return {"allowed": False, "message": f"Unknown navigation: {target_action}"}

    # Global admin can access everything
    if "global:admin" in user_context.get("scopes", []):
        return {"allowed": True}

    # Check if user has required role for target
    required_roles = config.get("roles", [])
    # ... permission logic
```

### Intent Classifier

The intent classifier uses the unified `goto` action format:

```python
# Navigation intent structure
{
    "intent_type": "navigation",
    "details": {
        "action_type": "goto_home",  # or goto_analyst_topic, goto_root, etc.
        "topic": "macro",            # optional
        "article_id": 123            # optional
    }
}

# UI action converts to goto
{
    "type": "goto",
    "params": {
        "section": "analyst_dashboard",
        "topic": "macro"
    }
}
```

---

## Related Documentation

- [UI Actions](./14-ui-actions.md) - Detailed action documentation
- [User Workflows](./13-user-workflows.md) - Complete workflow guides
- [Frontend](./12-frontend.md) - Page structure and components
- [Authorization](./02-authorization_concept.md) - Role and scope definitions
