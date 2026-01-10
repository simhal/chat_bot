# Frontend Navigation & Components Reference

This document maps all navigation paths, components, and features in the application. Use `{topic}` as a placeholder for dynamic topic slugs (e.g., `macro`, `equity`, `fixed_income`, `esg`).

---

## Navigation Structure Overview

```
/                           # Home - Article browsing & search
├── ?tab={topic}            # Topic-specific article list
├── ?tab=search             # Advanced article search
│
/analyst                    # Analyst Hub (redirects to first accessible topic)
├── /analyst/{topic}        # Analyst Draft Management
│   └── ?view=drafts        # View draft articles
└── /analyst/edit/{id}      # Article Editor
    ├── ?mode=editor        # Editor-only view
    ├── ?mode=preview       # Editor + Preview split
    └── ?mode=resources     # Editor + Resources split
│
/editor                     # Editor Hub (redirects to first accessible topic)
└── /editor/{topic}         # Editor Review Queue
    └── ?view=pending       # Articles pending review
│
/admin                      # Admin Hub
└── /admin/content          # Content Management
    └── ?tab={topic}        # Topic-specific content
│
/profile                    # User Profile & Settings
├── ?tab=info               # Profile information
└── ?tab=settings           # User preferences
│
/auth/callback              # OAuth callback (internal)
```

---

## Route Details

### `/` - Home Page

**Purpose**: Main landing page for browsing and searching published articles.

**Required Permission**: Authenticated user (any role)

| Component | Name | Description |
|-----------|------|-------------|
| Topic Tabs | Topic Navigation | Horizontal tabs to switch between article topics (Macro, Equity, Fixed Income, ESG) |
| Search Tab | Search Navigation | Tab to access advanced article search |
| Article List | Article Cards | Grid of article cards showing headline, date, readership, rating, and keywords |
| Article Modal | Article Viewer | Full article view with content, metadata, PDF download, and rating options |
| Login Panel | Authentication | LinkedIn OAuth login button for unauthenticated users |

**Sub-paths**:
| Path | Name | Description |
|------|------|-------------|
| `/?tab={topic}` | Topic View | Shows published articles for the selected topic |
| `/?tab=search` | Search View | Advanced search form with filters |

---

### `/?tab=search` - Article Search

**Purpose**: Advanced search interface for finding articles across all topics.

**Required Permission**: Authenticated user (any role)

| Component | Name | Description |
|-----------|------|-------------|
| Topic Filter | Topic Dropdown | Filter results by specific topic or search all |
| Search Input | General Search | Full-text search across article content (vector + keyword) |
| Headline Filter | Headline Search | Search within article headlines only |
| Keywords Filter | Keywords Search | Filter by article keywords |
| Author Filter | Author Search | Filter by article author/creator |
| Date Range | Date Filters | Filter by creation date (from/to) |
| Limit Control | Results Limit | Control number of results returned |
| Search Button | Search Action | Execute the search query |
| Results Grid | Search Results | Article cards matching search criteria |

---

### `/analyst` - Analyst Hub

**Purpose**: Redirect to the analyst's first accessible topic dashboard.

**Required Permission**: `{topic}:analyst` or `global:admin`

**Behavior**: Automatically redirects to `/analyst/{topic}` based on user's permissions and saved preference.

---

### `/analyst/{topic}` - Analyst Draft Management

**Purpose**: Create and manage draft articles for a specific topic.

**Required Permission**: `{topic}:analyst` or `global:admin`

| Component | Name | Description |
|-----------|------|-------------|
| Topic Selector | Topic Dropdown | Switch between accessible analyst topics |
| New Article Button | Create Article | Creates a new empty draft article |
| Article Grid | Draft Articles | List of draft articles with status, metadata, and actions |
| Status Badge | Article Status | Shows draft/editor/published status |
| View Button | View Article | Opens article in preview modal |
| Edit Button | Edit Article | Navigates to full article editor |
| Submit Button | Submit for Review | Sends draft to editor queue (changes status to 'editor') |
| Delete Button | Delete Article | Removes article (admin only) |
| Article Modal | Article Preview | Full article view with all metadata |

**Article Card Information**:
- Headline with status indicator
- Article ID and creation date
- Readership count and rating
- Keywords (comma-separated)
- Content preview (truncated)

---

### `/analyst/edit/{id}` - Article Editor

**Purpose**: Full-featured article editing interface with AI assistance.

**Required Permission**: `{topic}:analyst` or `global:admin` for the article's topic

| Component | Name | Description |
|-----------|------|-------------|
| Back Button | Return to Hub | Navigate back to analyst topic dashboard |
| Article Info | Article Metadata | Shows article ID and current status |
| View Mode Toggle | Layout Selector | Switch between Editor Only, Editor+Preview, Editor+Resources |
| Save Button | Save Changes | Persist all edits to the article |
| Submit Button | Submit for Review | Send to editor queue (only visible for drafts) |
| Headline Input | Headline Editor | Edit the article headline (max 500 chars) |
| Keywords Input | Keywords Editor | Edit comma-separated keywords |
| Content Textarea | Content Editor | Markdown editor for article body with word count |
| Preview Panel | Live Preview | Real-time rendered preview of markdown content |
| Resources Panel | Resource Manager | Link/unlink resources, drag into content |
| Chat Panel | Content Agent | AI assistant for article modifications |

**View Modes**:
| Mode | Name | Description |
|------|------|-------------|
| `?mode=editor` | Editor Only | Full-width editor panel |
| `?mode=preview` | Editor + Preview | Split view with live preview |
| `?mode=resources` | Editor + Resources | Split view with resource manager |

**Chat Panel Features**:
- Chat history with user and agent messages
- Input field for instructions
- Agent can modify headline, content, and keywords
- Receives generated content from main chat agent

---

### `/editor` - Editor Hub

**Purpose**: Redirect to the editor's first accessible topic review queue.

**Required Permission**: `{topic}:editor` or `global:admin`

**Behavior**: Automatically redirects to `/editor/{topic}` based on user's permissions and saved preference.

---

### `/editor/{topic}` - Editor Review Queue

**Purpose**: Review and publish articles submitted by analysts.

**Required Permission**: `{topic}:editor` or `global:admin`

| Component | Name | Description |
|-----------|------|-------------|
| Topic Selector | Topic Dropdown | Switch between accessible editor topics |
| Article Grid | Pending Articles | List of articles with status='editor' awaiting review |
| Status Badge | Article Status | Shows current workflow status |
| View Button | Review Article | Opens article in review modal |
| Reject Button | Reject Article | Returns article to draft status |
| Publish Button | Publish Article | Changes status to 'published', makes visible to readers |
| Review Modal | Article Review | Full article view with review actions |

**Review Modal Actions**:
- Download PDF - Export article as PDF
- Reject - Return to analyst for revisions
- Publish - Make article publicly visible

---

### `/admin` - Admin Hub

**Purpose**: Administration dashboard landing page.

**Required Permission**: `global:admin`

| Component | Name | Description |
|-----------|------|-------------|
| Navigation Cards | Admin Sections | Links to different admin areas |
| Content Management | Content Link | Navigate to `/admin/content` |
| User Management | Users Link | Navigate to user administration |
| System Settings | Settings Link | Navigate to system configuration |

---

### `/admin/content` - Content Management

**Purpose**: Administrative interface for managing all content across topics.

**Required Permission**: `global:admin`, `{topic}:admin`, `{topic}:analyst`, or `{topic}:editor`

| Component | Name | Description |
|-----------|------|-------------|
| Topic Tabs | Topic Navigation | Switch between topic content views |
| Generate Button | Generate Content | Open AI content generation dialog (if authorized) |
| Search Toggle | Advanced Search | Expand/collapse search filters |
| Search Form | Content Search | Filter articles by various criteria |
| Article Grid | Content List | All articles for the topic (all statuses) |
| Status Badge | Article Status | Visual status indicator (draft/editor/published) |
| Inactive Badge | Inactive Flag | Shows if article is deactivated |
| Edit Button | Edit Article | Navigate to article editor |
| Delete Button | Delete Article | Soft-delete article (admin only) |
| Reactivate Button | Restore Article | Reactivate deleted article (admin only) |

---

### `/profile` - User Profile

**Purpose**: View profile information and manage user preferences.

**Required Permission**: Authenticated user (any role)

| Component | Name | Description |
|-----------|------|-------------|
| Profile Tabs | Section Navigation | Switch between Info and Settings tabs |
| Avatar | Profile Picture | User photo from OAuth or initial placeholder |
| User Info | Profile Details | Name, email, member since date |
| Groups List | Group Memberships | Badges showing assigned groups |
| Tonality Settings | Response Preferences | Configure AI response style |
| Delete Account | Account Removal | Permanently delete user account |

**Tabs**:
| Tab | Name | Description |
|-----|------|-------------|
| `?tab=info` | Profile Info | View profile details and group memberships |
| `?tab=settings` | Settings | Manage preferences and account |

**Settings Components**:
| Component | Name | Description |
|-----------|------|-------------|
| Chat Tonality | Chat Style | Dropdown to select AI chat response style |
| Content Tonality | Content Style | Dropdown to select AI content generation style |
| Save Button | Save Preferences | Persist tonality preferences |
| Danger Zone | Account Actions | Section containing destructive actions |
| Delete Button | Delete Account | Remove account with double confirmation |

---

## Permission Reference

| Permission Scope | Access Level | Description |
|-----------------|--------------|-------------|
| `global:admin` | Full Access | All features across all topics |
| `{topic}:admin` | Topic Admin | Full access to specific topic |
| `{topic}:analyst` | Analyst | Create/edit drafts for specific topic |
| `{topic}:editor` | Editor | Review/publish articles for specific topic |
| (authenticated) | Reader | Browse published articles, use search |

---

## Common UI Components

### Header
- **Logo/Home Link**: Navigate to home page
- **Topic Links**: Quick access to topic views
- **Search Link**: Navigate to search
- **Analyst Link**: Navigate to analyst hub (if authorized)
- **Editor Link**: Navigate to editor hub (if authorized)
- **Admin Link**: Navigate to admin hub (if authorized)
- **Profile Menu**: User avatar with profile/logout options

### Chat Panel (Global)
- **Agent Label**: Shows current context-aware agent name
- **Message History**: Scrollable chat messages
- **Input Field**: Type messages to the AI assistant
- **Send Button**: Submit message
- **Clear Button**: Clear chat history

### Article Card
- **Headline**: Article title (clickable)
- **Status Badge**: Draft/Editor/Published indicator
- **Metadata**: Date, readership, rating
- **Keywords**: Tag-style keyword display
- **Preview**: Truncated content preview
- **Actions**: Context-specific action buttons

### Modal Dialog
- **Header**: Title and close button
- **Content Area**: Scrollable content
- **Footer**: Action buttons
- **Overlay**: Click-to-close background

---

## Navigation Context

The application tracks the user's current location for context-aware AI assistance:

| Context Field | Values | Description |
|--------------|--------|-------------|
| `section` | home, search, analyst, editor, admin, profile | Current major section |
| `topic` | macro, equity, fixed_income, esg, null | Selected topic if applicable |
| `subNav` | drafts, editing, pending, content, info, settings, null | Sub-section within major section |
| `articleId` | number or null | Current article being viewed/edited |
| `articleHeadline` | string or null | Current article's headline |
| `role` | reader, analyst, editor, admin | User's role in current context |

---

## Related Documentation

- [User Workflows](./13-user-workflows.md) - Step-by-step workflow guides
- [UI Actions](./14-ui-actions.md) - Chat-triggered UI commands
- [Authorization](./02-authorization_concept.md) - Permission system
- [Architecture Diagrams](./diagrams/frontend-architecture.mmd) - Frontend component diagram
