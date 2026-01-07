# User Workflows Guide

This document describes all user workflows in the application, organized by user role.

## Table of Contents

1. [User Roles Overview](#1-user-roles-overview)
2. [Authentication Workflows](#2-authentication-workflows)
3. [Reader Workflows](#3-reader-workflows)
4. [Analyst Workflows](#4-analyst-workflows)
5. [Editor Workflows](#5-editor-workflows)
6. [Admin Workflows](#6-admin-workflows)
7. [Profile & Settings Workflows](#7-profile--settings-workflows)
8. [Chat Workflows](#8-chat-workflows)

---

## 1. User Roles Overview

### Scope-Based Permission System

Users are assigned scopes in the format `{topic}:{role}`:

| Role | Scope Format | Capabilities |
|------|--------------|--------------|
| Reader | `{topic}:reader` | Browse, search, read, rate articles |
| Analyst | `{topic}:analyst` | Reader + create, edit, submit articles |
| Editor | `{topic}:editor` | Reader + review, reject, publish articles |
| Topic Admin | `{topic}:admin` | All topic operations + content management |
| Global Admin | `global:admin` | All operations across all topics |

### Role Hierarchy

```
global:admin
    └── {topic}:admin
            └── {topic}:editor
                    └── {topic}:analyst
                            └── {topic}:reader
```

---

## 2. Authentication Workflows

### 2.1 LinkedIn OAuth Login

1. User navigates to application
2. Click "Sign in with LinkedIn"
3. Redirect to LinkedIn OAuth consent page
4. Authorize the application
5. Redirect back to callback URL
6. JWT token issued with user's scopes
7. User lands on main chat interface

### 2.2 Session Management

- JWT tokens expire after configured duration
- Refresh tokens can extend sessions
- Tokens stored in browser localStorage
- Logout clears tokens and redirects to login

### 2.3 First-Time User Setup

1. New users receive default reader access
2. Admins can assign additional roles via admin panel
3. Users see only topics they have access to

---

## 3. Reader Workflows

**Available to:** All authenticated users

### 3.1 Browse Articles

1. Select topic from tabs (Macro, Equity, Fixed Income, etc.)
2. View list of published articles
3. Articles show headline, author, date, rating
4. Click article to view full content

### 3.2 Read Article

1. Open article from list
2. View full article content with markdown rendering
3. See metadata (author, editor, publication date)
4. View associated resources (images, tables, PDFs)
5. Readership count increments automatically

### 3.3 Search Articles

**Basic Search:**
1. Enter search term in search bar
2. Results filter by keyword match
3. Click result to open article

**Advanced Search:**
1. Filter by headline
2. Filter by keywords
3. Filter by author
4. Filter by date range
5. Combine multiple filters

### 3.4 Rate Articles

1. Open a published article
2. Click star rating (1-5 stars)
3. Rating saved and average updated
4. Can change rating later

### 3.5 Download Article PDF

1. Open article
2. Click "Download PDF"
3. PDF generated with article content
4. File downloads to browser

### 3.6 View Article Resources

1. Open article with attached resources
2. Click resource thumbnail/link
3. Images open in modal
4. PDFs open in viewer or download
5. Tables display inline

---

## 4. Analyst Workflows

**Required Scope:** `{topic}:analyst` or higher

### 4.1 Access Analyst Dashboard

1. Navigate to `/analyst/{topic}`
2. View your draft articles
3. See articles returned for revision
4. Access article creation tools

### 4.2 Create New Article

1. Click "Create Article" or ask chat to create
2. Enter headline
3. Write content using markdown editor
4. Add keywords for searchability
5. Save as draft

### 4.3 Edit Draft Article

1. Select draft from analyst dashboard
2. Modify headline, content, keywords
3. Switch between editor/preview modes
4. Save changes (auto-save available)

### 4.4 Manage Article Resources

1. Open article in editor
2. Click "Resources" tab
3. Add resources:
   - Upload images
   - Upload PDFs
   - Create data tables
   - Add text snippets
4. Link resources to article
5. Remove/unlink resources as needed

### 4.5 Submit for Editorial Review

1. Open completed draft
2. Click "Submit for Review"
3. Confirm submission
4. Article status changes to EDITOR
5. Article moves to editor queue

### 4.6 Revise Rejected Article

1. Receive notification of rejection
2. Open article in analyst dashboard
3. View editor feedback/notes
4. Make requested changes
5. Re-submit for review

---

## 5. Editor Workflows

**Required Scope:** `{topic}:editor` or higher

### 5.1 Access Editor Dashboard

1. Navigate to `/editor/{topic}`
2. View articles awaiting review (EDITOR status)
3. See submission queue ordered by date

### 5.2 Review Article

1. Click article in review queue
2. Read full content
3. Review headline and keywords
4. Check attached resources
5. Preview PDF output

### 5.3 Request Changes (Reject)

1. Click "Request Changes" or "Reject"
2. Enter feedback explaining needed changes
3. Submit rejection
4. Article returns to DRAFT status
5. Analyst receives notification

### 5.4 Publish Article

1. Click "Publish" on approved article
2. Confirm publication
3. HITL (Human-in-the-Loop) approval may trigger:
   - Article enters PENDING_APPROVAL status
   - WebSocket notification for approval
   - Click "Approve" to finalize
4. Article status changes to PUBLISHED
5. Article visible to all readers

### 5.5 HITL Approval Flow

1. Receive approval request via WebSocket
2. Review final article state
3. Choose to:
   - **Approve**: Article publishes immediately
   - **Reject**: Article returns to EDITOR queue with notes

---

## 6. Admin Workflows

### 6.1 Topic Admin Workflows

**Required Scope:** `{topic}:admin`

#### View All Articles

1. Navigate to `/admin/content`
2. Select topic
3. View articles in all statuses (DRAFT, EDITOR, PENDING, PUBLISHED)
4. Filter and sort by various criteria

#### Edit Any Article

1. Select article from admin view
2. Edit content regardless of status
3. Modify author/editor assignments
4. Save changes

#### Reorder Articles

1. Access article list
2. Drag articles to reorder
3. Save new priority order
4. Order reflected in reader view

#### Recall Published Article

1. Find published article
2. Click "Recall"
3. Confirm action
4. Article status returns to DRAFT
5. Article removed from public view

#### Deactivate/Reactivate Articles

1. Find article to deactivate
2. Click "Deactivate" (soft delete)
3. Article hidden from readers but preserved
4. Admin can still view/manage
5. Click "Reactivate" to restore

#### Purge Article (Permanent Delete)

1. Find article to purge
2. Click "Purge"
3. Confirm permanent deletion (warning displayed)
4. Article permanently removed
5. ChromaDB embeddings cleaned up

### 6.2 Global Admin Workflows

**Required Scope:** `global:admin`

#### Manage Topics

1. Navigate to `/admin/global`
2. View all topics
3. Create new topic:
   - Enter slug (URL-friendly name)
   - Enter display title
   - Configure visibility
   - Default groups created automatically
4. Edit existing topics
5. Deactivate topics to hide from users

#### Manage Users

1. View all users
2. Search by name or email
3. View user profile and group memberships
4. Assign users to groups (roles)
5. Remove users from groups
6. Deactivate user accounts

#### Manage Groups

1. View all permission groups
2. Create new groups:
   - Format: `{topic}:{role}` or `global:admin`
3. Assign/remove users from groups
4. Delete unused groups

#### Edit Global Prompts

1. Navigate to prompt management
2. Edit system prompts:
   - Base general prompt
   - Chat-specific prompt
   - Chat constraints
   - Article generation constraints
3. Save changes
4. Changes apply to all new conversations

#### Manage Tonality Options

1. View available tonality options
2. Create new tonality:
   - Define name
   - Write prompt modification
3. Edit existing tonalities
4. Deactivate tonalities to hide from users
5. Set default tonality for new users

---

## 7. Profile & Settings Workflows

**Available to:** All authenticated users

### 7.1 View Profile

1. Navigate to `/profile`
2. View personal information (from LinkedIn)
3. See assigned groups and roles
4. View access statistics (last login, total logins)

### 7.2 Update Chat Tonality

1. Go to profile settings
2. Select preferred chat tonality from dropdown
3. Options: Professional, Casual, Technical, etc.
4. Save preference
5. Chat responses adapt to selected tone

### 7.3 Update Content Tonality

1. Go to profile settings
2. Select preferred content style
3. Save preference
4. Generated articles match selected style

### 7.4 Delete Account

1. Go to profile settings
2. Click "Delete Account"
3. Confirm deletion
4. Account and associated data removed
5. Logged out and redirected

---

## 8. Chat Workflows

**Available to:** All authenticated users

### 8.1 Basic Chat Interaction

1. Type message in chat input
2. Send message
3. AI processes and responds
4. Response streams in real-time
5. Conversation history maintained

### 8.2 Article-Aware Chat

1. Ask questions about topics
2. AI searches ChromaDB for relevant articles
3. Response references specific articles
4. Click article citations to view full content

### 8.3 Chat-Triggered UI Actions

The chat can trigger UI actions based on natural language:

| User Request | Action |
|--------------|--------|
| "Show me macro articles" | Switches to Macro topic tab |
| "Search for inflation" | Executes search query |
| "Show the GDP article" | Opens specific article |
| "Download as PDF" | Generates and downloads PDF |

### 8.4 Analyst Chat Actions

**For users with analyst scope:**

| User Request | Action |
|--------------|--------|
| "Create a new article" | Opens article creation |
| "Research latest news on..." | WebSearchAgent runs |
| "Download economic data for..." | DataDownloadAgent runs |

### 8.5 Editor Chat Actions

**For users with editor scope:**

| User Request | Action |
|--------------|--------|
| "Show articles for review" | Opens editor queue |
| "Publish this article" | Initiates HITL publish workflow |

### 8.6 Background Tasks

Complex requests may run as background tasks:

1. Request complex research or analysis
2. Task queued to Celery worker
3. Progress indicator shows in UI
4. Results return when complete
5. Can continue chatting while waiting

### 8.7 Conversation Memory

- Chat maintains context within session
- Can refer to previous topics
- Follow-up questions work naturally
- Starting new session clears context

---

## Related Documentation

- [Multi-Agent Architecture](./08-multi-agent-architecture.md) - System design
- [Frontend](./13-frontend.md) - Navigation and components
- [UI Actions](./15-ui-actions.md) - Chat-triggered actions
- [Authorization](./02-authorization_concept.md) - Permission system
