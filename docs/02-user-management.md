# User Management

## Overview

The user management system handles user accounts, group memberships, and role assignments. Users are authenticated via LinkedIn OAuth and organized into groups that define their access permissions. The system supports a flexible permission model where users can belong to multiple groups across different research topics.

---

## Core Concepts

### Users

A **User** represents an individual who can access the platform. Users are created automatically on first login via LinkedIn OAuth, eliminating the need for manual account creation or password management.

### Groups

A **Group** represents a permission scope combining a topic area (like "macro" or "equity") with a role level (like "admin" or "analyst"). Groups follow the naming convention `{topic}:{role}`.

### Memberships

Users are connected to groups through **memberships**. A user can belong to multiple groups, allowing for flexible permission combinations like:
- `macro:analyst` + `equity:reader` → Can create macro content and view equity content
- `global:admin` → Has full access to everything

---

## User Data Model

### User Information

When a user logs in via LinkedIn, the following information is captured and maintained:

| Field | Source | Description |
|-------|--------|-------------|
| **Email** | LinkedIn | Primary identifier, must be unique |
| **Name** | LinkedIn | First name from profile |
| **Surname** | LinkedIn | Last name from profile |
| **LinkedIn ID** | LinkedIn | Unique identifier from LinkedIn (immutable) |
| **Profile Photo** | LinkedIn | URL to profile picture |
| **Active Status** | Platform | Whether the account is enabled |
| **Created At** | Platform | When the account was first created |
| **Last Access** | Platform | Most recent login timestamp |
| **Access Count** | Platform | Total number of logins |

### User Preferences

Users can customize their experience through preferences:

| Preference | Purpose | Effect |
|------------|---------|--------|
| **Chat Tonality** | Response style for AI chat | Changes how the AI agent communicates |
| **Content Tonality** | Writing style for generated articles | Affects the tone of AI-generated content |

---

## Group Structure

### Group Composition

Each group consists of three components:

```
┌─────────────────────────────────────────────────────────────┐
│                         Group                                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   Name: "macro:analyst"                                      │
│         ├── Groupname: "macro"     (the topic/domain)       │
│         └── Role: "analyst"         (the permission level)   │
│                                                              │
│   Description: "Macroeconomic analysts - can create         │
│                 and edit draft content"                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Standard Groups

The platform maintains a standard set of groups covering all topic-role combinations:

| Topic | Admin | Analyst | Editor | Reader |
|-------|-------|---------|--------|--------|
| **Global** | `global:admin` | - | - | - |
| **Macro** | `macro:admin` | `macro:analyst` | `macro:editor` | `macro:reader` |
| **Equity** | `equity:admin` | `equity:analyst` | `equity:editor` | `equity:reader` |
| **Fixed Income** | `fixed_income:admin` | `fixed_income:analyst` | `fixed_income:editor` | `fixed_income:reader` |
| **ESG** | `esg:admin` | `esg:analyst` | `esg:editor` | `esg:reader` |

### Role Definitions

| Role | Purpose | Typical Responsibilities |
|------|---------|-------------------------|
| **admin** | Full topic control | Manage users, resources, all content operations |
| **analyst** | Content creation | Write and edit draft articles, manage resources |
| **editor** | Content review | Review submissions, approve/reject, publish |
| **reader** | Content consumption | View published articles only |

---

## User Lifecycle

### First Login (Account Creation)

When a user logs in for the first time, the system automatically creates their account:

```
User clicks "Login with LinkedIn"
              │
              ▼
┌─────────────────────────────────────┐
│ LinkedIn authenticates user         │
│ Returns: email, name, LinkedIn ID   │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ Backend checks: Does user exist?    │
│ (Lookup by LinkedIn ID)             │
└─────────────────────────────────────┘
              │
        User not found
              │
              ▼
┌─────────────────────────────────────┐
│ Create new user record:             │
│ • Store email, name, surname        │
│ • Store LinkedIn ID (immutable)     │
│ • Set active = true                 │
│ • Set created_at = now              │
│ • No groups assigned yet            │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│ User can now log in but has         │
│ no permissions until admin          │
│ assigns them to groups              │
└─────────────────────────────────────┘
```

### Subsequent Logins

For returning users, the system updates tracking information:

```
User logs in
      │
      ▼
┌───────────────────────────────────┐
│ Find user by LinkedIn ID          │
│ (User exists in database)         │
└───────────────────────────────────┘
      │
      ▼
┌───────────────────────────────────┐
│ Update access tracking:           │
│ • last_access_at = now            │
│ • access_count += 1               │
│                                   │
│ Optionally update from LinkedIn:  │
│ • Profile photo (if changed)      │
│ • Name (if changed)               │
└───────────────────────────────────┘
      │
      ▼
┌───────────────────────────────────┐
│ Load group memberships            │
│ Generate JWT with scopes          │
└───────────────────────────────────┘
```

### Profile Updates

Users can update certain profile information, while other data comes exclusively from LinkedIn:

| Field | User Editable | Admin Editable | Source of Truth |
|-------|---------------|----------------|-----------------|
| Email | No | No | LinkedIn |
| Name | No | Yes | LinkedIn (admin can override) |
| Surname | No | Yes | LinkedIn (admin can override) |
| Photo | No | No | LinkedIn |
| Active Status | No | Yes | Platform |
| Groups | No | Yes | Platform |
| Preferences | Yes | Yes | Platform |

### Account Deactivation

Deactivated users cannot log in but their data is preserved for audit purposes:

```
Admin deactivates user
         │
         ▼
┌─────────────────────────────────┐
│ Set user.active = false         │
│                                 │
│ Revoke all active tokens        │
│ (Remove from Redis)             │
│                                 │
│ User data remains in database   │
│ (For audit trail)               │
└─────────────────────────────────┘
         │
         ▼
Next login attempt:
         │
         ▼
┌─────────────────────────────────┐
│ User found but active = false   │
│                                 │
│ Return: "Account deactivated"   │
│ (401 Unauthorized)              │
└─────────────────────────────────┘
```

---

## Group Management

### Assigning Users to Groups

Administrators can assign users to groups, granting them permissions:

```
┌─────────────────────────────────────────────────────────────┐
│                    Admin Panel                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  User: john.doe@company.com                                  │
│                                                              │
│  Current Groups:                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ [x] macro:analyst    - Assigned 2024-01-15              ││
│  │ [x] equity:reader    - Assigned 2024-01-20              ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  Available Groups:                                           │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ [ ] macro:admin                                         ││
│  │ [ ] macro:editor                                        ││
│  │ [ ] equity:admin                                        ││
│  │ [ ] equity:analyst                                      ││
│  │ ... (more groups)                                       ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  [Save Changes]                                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Assignment Records

Each group assignment is tracked with metadata:

| Field | Description |
|-------|-------------|
| **User ID** | The user being assigned |
| **Group ID** | The group being assigned to |
| **Assigned At** | Timestamp of assignment |

### Permission Inheritance

When a user is assigned to multiple groups, their effective permissions are the **union** of all group permissions:

```
User belongs to:
  • macro:analyst
  • equity:reader

Effective permissions:
  ┌────────────────────────────────────────────────────────┐
  │ Macro Topic:                                           │
  │   • View all articles (including drafts)               │
  │   • Create new articles                                │
  │   • Edit own drafts                                    │
  │   • Manage macro resources                             │
  │                                                        │
  │ Equity Topic:                                          │
  │   • View published articles only                       │
  │   • No create/edit permissions                         │
  │   • No resource access                                 │
  │                                                        │
  │ Other Topics:                                          │
  │   • No access                                          │
  └────────────────────────────────────────────────────────┘
```

---

## User Preferences

### Tonality Settings

Users can personalize how the AI interacts with them:

| Setting | Description | Example Options |
|---------|-------------|-----------------|
| **Chat Tonality** | How the AI responds in chat | Professional, Casual, Technical, Educational |
| **Content Tonality** | Style of generated articles | Formal Research, Executive Summary, Detailed Analysis |

### How Tonality Works

```
User sets preference: "Chat Tonality = Professional"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ Preference stored in User record                             │
│ (References a PromptModule of type "tonality")               │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
When user starts chat:
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│ AI Agent loads user's tonality preference                    │
│ Includes tonality instructions in system prompt              │
│                                                              │
│ "Respond in a professional tone. Use formal language.        │
│  Avoid colloquialisms. Be direct and precise."               │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
AI responses reflect the chosen tonality
```

---

## Administrative Functions

### User Listing

Administrators can view all users with filtering options:

| Filter | Purpose |
|--------|---------|
| **By Status** | Active, Inactive, All |
| **By Group** | Show only members of a specific group |
| **By Topic** | Show users with any role in a topic |
| **Search** | Find by name or email |

### Bulk Operations

For efficiency, administrators can perform bulk operations:

| Operation | Description |
|-----------|-------------|
| **Bulk Group Assignment** | Add multiple users to a group |
| **Bulk Deactivation** | Deactivate multiple accounts |
| **Export User List** | Download user data for reporting |

### Audit Trail

The system maintains records of administrative actions:

| Action | Recorded Data |
|--------|---------------|
| Group Assignment | Who assigned, when, which group |
| Group Removal | Who removed, when, which group |
| Account Deactivation | Who deactivated, when, reason |
| Account Reactivation | Who reactivated, when |

---

## API Capabilities

### User Endpoints

| Operation | Who Can Do It | Description |
|-----------|---------------|-------------|
| View own profile | Any authenticated user | Get current user's information |
| Update preferences | Any authenticated user | Change tonality settings |
| List all users | Administrators only | View all user accounts |
| View any user | Administrators only | Get specific user details |
| Update any user | Administrators only | Modify user information |
| Assign to group | Administrators only | Grant permissions |
| Remove from group | Administrators only | Revoke permissions |
| Deactivate account | Administrators only | Disable user access |

### Group Endpoints

| Operation | Who Can Do It | Description |
|-----------|---------------|-------------|
| List all groups | Administrators only | View all available groups |
| View group details | Administrators only | See group description and members |
| List group members | Administrators only | See all users in a group |

---

## Frontend Integration

### User Context

The frontend maintains user information in a store accessible throughout the application:

| Data Available | Usage |
|----------------|-------|
| User ID | API calls, logging |
| Email | Display, contact |
| Name/Surname | Display, personalization |
| Profile Photo | UI display |
| Scopes (Permissions) | UI rendering decisions |

### Permission-Based UI

The frontend adapts based on user permissions:

```
┌────────────────────────────────────────────────────────────┐
│                    Navigation Bar                           │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  [Chat]  [Articles]  [Resources]  [Admin]*                 │
│                                                             │
│  * Only visible if user has admin scope                    │
│                                                             │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                    Article List                             │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  "Inflation Analysis"                                       │
│  [View]  [Edit]*  [Delete]*                                │
│                                                             │
│  * Only visible if user has analyst/admin scope for topic  │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### Route Protection

Certain pages are only accessible to users with appropriate permissions:

| Route | Required Permission |
|-------|---------------------|
| `/chat` | Any authenticated user |
| `/analyst/{topic}` | `{topic}:analyst` or higher |
| `/editor/{topic}` | `{topic}:editor` or higher |
| `/admin` | `global:admin` |

---

## Security Considerations

### Data Protection

| Data Type | Protection Measure |
|-----------|-------------------|
| LinkedIn ID | Never exposed in API responses |
| Email | Only visible to user themselves and admins |
| Access Logs | Retained for audit purposes |

### Permission Boundaries

- Users cannot elevate their own permissions
- Only `global:admin` can create other `global:admin` users
- Topic admins can only manage users within their topic
- Changes to permissions take effect on next token refresh

### Account Recovery

Since authentication is via LinkedIn:
- No password reset functionality needed
- Account issues are resolved by LinkedIn
- Platform admins can only activate/deactivate accounts
