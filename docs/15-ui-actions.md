# UI Actions - Chatbot-Triggered Commands

This document describes all UI actions that can be triggered by the main chat agent to control the frontend interface. These actions allow the chatbot to navigate between pages, open articles, trigger workflows, and perform administrative tasks.

## Table of Contents

1. [Overview](#overview)
2. [Required Roles](#required-roles)
3. [Navigation Context](#navigation-context)
4. [Actions by Page](#actions-by-page)
5. [Common Actions](#common-actions)
6. [Confirmation Actions](#confirmation-actions)
7. [Action Results](#action-results)
8. [Backend Integration](#backend-integration)

---

## Overview

The UI action system allows the chatbot to trigger frontend interactions programmatically. Actions are dispatched from the backend via the chat response and executed by the appropriate page component.

### How It Works

1. **Backend**: The main chat agent includes a `ui_action` in its response
2. **Frontend**: The `ChatPanel` component receives the action and dispatches it to the `actionStore`
3. **Page Component**: The currently active page component handles the action via registered handlers
4. **Result**: The action result is reported back to the chat for confirmation

### Action Structure

Actions consist of:

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | The action type (e.g., "open_article", "select_topic") |
| `params` | object | Optional parameters for the action |
| `timestamp` | number | When the action was dispatched |

Common parameters include: `article_id`, `topic`, `rating`, `search_query`, `resource_id`, `tab`, `view`, `confirmed`.

---

## Required Roles

Access to pages and actions is controlled by user scopes. Each user can have multiple scopes assigned through groups.

### Scope Format

Scopes follow the pattern `{topic}:{role}` or `global:{role}`:

- `macro:reader` - Reader access to the "macro" topic
- `macro:analyst` - Analyst access to the "macro" topic
- `macro:editor` - Editor access to the "macro" topic
- `macro:admin` - Admin access to the "macro" topic
- `global:admin` - Global administrator (access to all topics and system settings)

### Page Access Requirements

| Page | Required Scope | Description |
|------|----------------|-------------|
| `/` (Home) | Any authenticated user | Main reader interface |
| `/analyst` | `{topic}:analyst` | Analyst hub - select topic first |
| `/analyst/[topic]` | `{topic}:analyst` | Create and manage draft articles for specific topic |
| `/analyst/edit/[id]` | `{topic}:analyst` | Edit a specific article |
| `/editor` | `{topic}:editor` | Editor hub - select topic first |
| `/editor/[topic]` | `{topic}:editor` | Review and publish articles for specific topic |
| `/admin` | `{topic}:admin` or `global:admin` | Topic-specific administration |
| `/admin/global` | `global:admin` | System-wide administration |
| `/profile` | Any authenticated user | User profile and settings |

### Action Permission Matrix

| Action Category | Required Role | Notes |
|-----------------|---------------|-------|
| Read articles | `{topic}:reader` or higher | Basic reader access |
| Create/edit articles | `{topic}:analyst` | Content creation |
| Submit for review | `{topic}:analyst` | Workflow transition |
| Publish/reject articles | `{topic}:editor` | Editorial control |
| Deactivate/recall articles | `{topic}:admin` | Content moderation |
| Purge articles | `{topic}:admin` | Permanent deletion |
| Manage users/groups | `global:admin` | System administration |
| Manage prompts/topics | `global:admin` | System configuration |

---

## Navigation Context

The navigation context tracks where the user is in the application and what they're focused on. This information is sent to the backend with each chat message to provide context-aware responses.

### Context Variables

The navigation context includes:

**Location:**
- `section` - Current page section (home, search, analyst, editor, admin, profile)
- `topic` - Current topic slug (e.g., 'macro', 'equity')
- `subNav` - Sub-navigation state (e.g., 'articles', 'resources')

**Article Focus:**
- `articleId` - ID of focused article
- `articleHeadline` - Headline for display
- `articleKeywords` - Keywords for context
- `articleStatus` - Article workflow status (draft, editor, published)

**Resource Focus:**
- `resourceId` - ID of focused resource
- `resourceName` - Resource name
- `resourceType` - Resource type (text, pdf, image, etc.)

**View State:**
- `viewMode` - Current view mode (editor, preview, resources)
- `role` - User's current role (reader, analyst, editor, admin)

### Context Variable Details

| Variable | Type | Description | Example Values |
|----------|------|-------------|----------------|
| `section` | string | Current page section | `'home'`, `'analyst'`, `'editor'`, `'admin'`, `'profile'` |
| `topic` | string | Selected topic slug | `'macro'`, `'equity'`, `'fixed_income'` |
| `subNav` | string | Sub-navigation state | `'articles'`, `'resources'`, `'drafts'`, `'pending'` |
| `articleId` | number | Currently focused article | `42`, `null` |
| `articleHeadline` | string | Article headline | `'Q4 Economic Outlook'` |
| `articleKeywords` | string | Article keywords | `'economy, forecast, GDP'` |
| `articleStatus` | string | Article workflow status | `'draft'`, `'editor'`, `'published'` |
| `resourceId` | number | Currently focused resource | `15`, `null` |
| `resourceName` | string | Resource name | `'GDP Chart.png'` |
| `resourceType` | string | Resource type | `'image'`, `'pdf'`, `'text'`, `'table'` |
| `viewMode` | string | Current view mode | `'editor'`, `'preview'`, `'resources'` |
| `role` | string | User's role in context | `'reader'`, `'analyst'`, `'editor'`, `'admin'` |

### Context Usage by Page

| Page | Key Context Variables | Purpose |
|------|----------------------|---------|
| Home | `section`, `topic`, `articleId` | Track topic tab and viewed article |
| Analyst Hub | `section`, `topic`, `articleId`, `articleStatus` | Track draft articles |
| Analyst Edit | `section`, `topic`, `articleId`, `viewMode` | Track editing state |
| Editor Hub | `section`, `topic`, `articleId`, `articleStatus` | Track articles under review |
| Topic Admin | `section`, `topic`, `subNav`, `articleId` | Track admin view and article |
| Global Admin | `section`, `subNav` | Track admin panel view |
| Profile | `section`, `subNav` | Track profile tab |

### API Payload

The context is sent to the backend with each chat message, including fields like `section`, `topic`, `article_id`, `article_headline`, `article_keywords`, `article_status`, `sub_nav`, `role`, `resource_id`, `resource_name`, `resource_type`, and `view_mode`. This allows the chatbot to understand the user's current context and provide relevant responses.

---

## Actions by Page

### Home Page (`/`)

The main reader interface for browsing and reading articles.

| Action | Description | Parameters |
|--------|-------------|------------|
| `select_topic_tab` | Switch to a specific topic tab | `topic: string` |
| `select_topic` | Select a topic (alias for select_topic_tab) | `topic: string` |
| `search_articles` | Perform an article search | `search_query: string` |
| `clear_search` | Clear the current search and show all articles | - |
| `open_article` | Open an article in the modal viewer | `article_id: number` |
| `select_article` | Focus on an article (update navigation context) | `article_id: number` |
| `rate_article` | Open the rating modal for an article | `article_id: number` |
| `download_pdf` | Download the PDF for the current article | `article_id: number` |
| `close_modal` | Close any open modal | - |

**Example:** To open article #42, the chatbot returns action type `open_article` with params containing `article_id: 42`.

---

### Analyst Hub (`/analyst/[topic]`)

The analyst workspace for creating and managing draft articles.

| Action | Description | Parameters |
|--------|-------------|------------|
| `create_new_article` | Open the new article creation form | - |
| `view_article` | Open an article in the preview modal | `article_id: number` |
| `edit_article` | Navigate to the article editor | `article_id: number` |
| `submit_article` | Submit an article for editor review | `article_id: number` |
| `select_topic` | Switch to a different topic | `topic: string` |
| `select_article` | Focus on an article (update navigation context) | `article_id: number` |
| `download_pdf` | Download the PDF for an article | `article_id: number` |
| `close_modal` | Close any open modal | - |

---

### Analyst Edit (`/analyst/edit/[id]`)

The article editor for writing and editing content.

| Action | Description | Parameters |
|--------|-------------|------------|
| `save_draft` | Save the current article as draft | - |
| `submit_for_review` | Submit the article for editor review | - |
| `switch_view_editor` | Switch to the Markdown editor view | - |
| `switch_view_preview` | Switch to the HTML preview view | - |
| `switch_view_resources` | Switch to the resources management view | - |
| `open_resource_modal` | Open the resource browser modal | - |
| `browse_resources` | Browse available resources | `scope?: 'global' \| 'topic' \| 'article' \| 'all'` |

---

### Editor Hub (`/editor/[topic]`)

The editor workspace for reviewing and publishing articles.

| Action | Description | Parameters |
|--------|-------------|------------|
| `view_article` | Open an article in the preview modal | `article_id: number` |
| `publish_article` | Publish an article (make it visible to readers) | `article_id: number` |
| `reject_article` | Reject an article and return it to draft | `article_id: number` |
| `select_topic` | Switch to a different topic | `topic: string` |
| `select_article` | Focus on an article (update navigation context) | `article_id: number` |
| `download_pdf` | Download the PDF for an article | `article_id: number` |
| `close_modal` | Close any open modal | - |

---

### Topic Admin (`/admin`)

Administrative interface for managing topic-specific articles and resources.

| Action | Description | Parameters |
|--------|-------------|------------|
| `select_topic` | Switch to a different topic | `topic: string` |
| `focus_article` | Focus on an article in the articles table | `article_id: number` |
| `deactivate_article` | Deactivate an article (soft delete) | `article_id: number`, `confirmed: true` |
| `reactivate_article` | Reactivate a deactivated article | `article_id: number`, `confirmed: true` |
| `recall_article` | Recall a published article back to draft | `article_id: number`, `confirmed: true` |
| `purge_article` | Permanently delete an article | `article_id: number`, `confirmed: true` |

**Note:** Administrative actions require `confirmed: true` in params to bypass confirmation dialogs.

---

### Global Admin (`/admin/global`)

Administrative interface for system-wide settings (requires `global:admin` role).

| Action | Description | Parameters |
|--------|-------------|------------|
| `switch_global_view` | Switch between admin views | `view: 'users' \| 'groups' \| 'prompts' \| 'resources' \| 'topics'` |
| `select_topic` | Navigate to Topic Admin for a specific topic | `topic: string` |
| `select_resource` | Focus on a resource | `resource_id: number` |
| `delete_resource` | Delete a global resource | `resource_id: number`, `confirmed: true` |

---

### Profile Page (`/profile`)

User profile and settings management.

| Action | Description | Parameters |
|--------|-------------|------------|
| `switch_profile_tab` | Switch between profile tabs | `tab: 'info' \| 'settings'` |
| `save_tonality` | Save tonality preferences | - |
| `delete_account` | Delete the user account | `confirmed: true` |

---

## Common Actions

These actions are available across multiple pages:

| Action | Description | Parameters | Pages |
|--------|-------------|------------|-------|
| `select_topic` | Switch to a topic | `topic: string` | All topic-aware pages |
| `select_article` | Focus on an article | `article_id: number` | Home, Analyst, Editor, Admin |
| `download_pdf` | Download article PDF | `article_id: number` | Home, Analyst, Editor |
| `close_modal` | Close current modal | - | All pages with modals |

---

## Confirmation Actions

Some administrative actions require explicit confirmation to prevent accidental execution. These actions must include `confirmed: true` in the params:

- `deactivate_article`
- `reactivate_article`
- `recall_article`
- `purge_article`
- `delete_resource`
- `delete_account`

**Example:** To purge article #123, the action type is `purge_article` with params `article_id: 123` and `confirmed: true`.

---

## Action Results

After an action is executed, the UI returns a result containing:

| Field | Description |
|-------|-------------|
| `success` | Whether the action succeeded |
| `action` | The action type that was executed |
| `message` | Success message (optional) |
| `error` | Error message if failed (optional) |
| `data` | Additional result data (optional) |

**Success Example:** Opening article #42 returns `success: true`, `action: "open_article"`, `message: "Article #42 opened"`.

**Error Example:** Selecting a restricted topic returns `success: false`, `action: "select_topic"`, `error: "No admin access to topic: restricted"`.

---

## Error Handling

Common error scenarios:

| Error | Cause | Resolution |
|-------|-------|------------|
| `No handler available for action: X` | Action dispatched on wrong page | Navigate to correct page first |
| `No article ID specified` | Missing required parameter | Include `article_id` in params |
| `Article not found in current view` | Article not loaded | Ensure topic is selected and articles loaded |
| `Action requires confirmation` | Missing `confirmed: true` | Add confirmation flag for destructive actions |
| `No admin access to topic: X` | Insufficient permissions | User lacks required role |

---

## Backend Integration

The main chat agent can trigger UI actions by including a `ui_action` field in its response. The response contains:
- `content` - The text response to show the user
- `ui_action` - Action to trigger (type and params)

The frontend `ChatPanel` component detects the `ui_action` field and dispatches the action to the store.

---

## Editor Content Store

In addition to UI actions, the chatbot can send content directly to the article editor via the `editorContentStore`. This is used when the AI generates article content.

### Content Payload Fields

| Field | Description |
|-------|-------------|
| `headline` | Article headline (optional) |
| `content` | Markdown content (optional) |
| `keywords` | Comma-separated keywords (optional) |
| `action` | How to apply content: fill, append, or replace |
| `linked_resources` | Resources to link to the article |
| `article_id` | Target article for verification |
| `timestamp` | When the content was generated |

### Content Actions

| Action | Description |
|--------|-------------|
| `fill` | Fill empty fields only |
| `append` | Append to existing content |
| `replace` | Replace existing content |

This allows the chatbot to generate article drafts and insert them directly into the editor.

---

## Related Documentation

- [User Workflows](./14-user-workflows.md) - Complete workflow guides
- [Frontend](./13-frontend.md) - Page structure and navigation
- [Multi-Agent Architecture](./08-multi-agent-architecture.md) - Agent system
- [Authorization](./02-authorization_concept.md) - Permission requirements
