# Testing Workflows Guide

This document describes application workflows and their automated test coverage. For details on running tests, see [Regression Testing Guide](./13-regression-testing.md).

## Table of Contents

1. [Workflow Overview](#1-workflow-overview)
2. [Authentication Workflows](#2-authentication-workflows)
3. [Reader Workflows](#3-reader-workflows)
4. [Analyst Workflows](#4-analyst-workflows)
5. [Editor Workflows](#5-editor-workflows)
6. [Admin Workflows](#6-admin-workflows)
7. [Profile & Chat Workflows](#7-profile--chat-workflows)
8. [Test Coverage Matrix](#8-test-coverage-matrix)

---

## 1. Workflow Overview

### User Roles and Scopes

| Role | Scope Format | Capabilities |
|------|--------------|--------------|
| Reader | `{topic}:reader` | Browse, search, read, rate articles |
| Analyst | `{topic}:analyst` | Reader + create, edit, submit articles |
| Editor | `{topic}:editor` | Reader + review, reject, publish articles |
| Topic Admin | `{topic}:admin` | All topic operations + content management |
| Global Admin | `global:admin` | All operations across all topics |

### Test Coverage by Component

| Component | Backend Tests | Frontend Tests | E2E Tests |
|-----------|---------------|----------------|-----------|
| Authentication | `test_auth.py`, `test_permissions.py` | - | `profile-chat.spec.ts` |
| Content/Articles | `test_content.py` | - | `reader.spec.ts`, `analyst.spec.ts`, `editor.spec.ts` |
| User Management | `test_admin.py`, `test_user_profile.py` | - | `admin.spec.ts` |
| Topics/Prompts | `test_topics.py`, `test_prompts.py` | - | `admin.spec.ts` |
| Chat & Actions | `test_chat.py` | `actions.test.ts` | `ui-actions.spec.ts` |

---

## 2. Authentication Workflows

### 2.1 OAuth Login Flow

**Workflow:** User authenticates via LinkedIn OAuth, receives JWT token with scopes.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_auth.py` | `TestAuthCallback` | OAuth callback handling, token exchange |
| `test_auth.py` | `TestTokenRefresh` | Token refresh flow |
| `test_auth.py` | `TestLogout` | Session termination |
| `test_permissions.py` | `TestAuthentication` | Token validation, expiry, malformed tokens |

**Key Security Tests (`test_permissions.py`):**
- `test_no_token_returns_401` - Unauthenticated requests blocked
- `test_malformed_token_returns_401` - Invalid JWT rejected
- `test_expired_token_returns_401` - Expired tokens rejected
- `test_wrong_secret_token_returns_401` - Wrong signing key rejected

### 2.2 Session Management

**Workflow:** Token-based sessions with Redis storage, automatic expiry.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_auth.py` | `TestTokenValidation` | JWT claims, expiration |
| `test_permissions.py` | `TestTokenSecurity` | Token uniqueness, required claims |

---

## 3. Reader Workflows

**Required Scope:** Any authenticated user

### 3.1 Browse Articles

**Workflow:** List published articles by topic, view article details.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_content.py` | `TestReaderEndpoints.test_get_articles_with_auth` | List articles by topic |
| `test_content.py` | `TestReaderEndpoints.test_get_article_by_id` | View single article |
| `test_content.py` | `TestReaderEndpoints.test_get_article_not_found` | 404 handling |

**E2E Coverage:** `frontend/e2e/workflows/reader.spec.ts`

### 3.2 Search Articles

**Workflow:** Search articles by keyword, filter by metadata.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_content.py` | `TestReaderEndpoints.test_search_articles` | Keyword search |
| `test_content.py` | `TestReaderEndpoints.test_get_top_rated_articles` | Filtered lists |
| `test_content.py` | `TestReaderEndpoints.test_get_most_read_articles` | Sorted lists |

### 3.3 Rate Articles

**Workflow:** Submit 1-5 star rating for published articles.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_content.py` | `TestReaderEndpoints.test_rate_article` | Valid rating submission |
| `test_content.py` | `TestReaderEndpoints.test_rate_article_invalid_rating` | Validation (1-5 range) |

---

## 4. Analyst Workflows

**Required Scope:** `{topic}:analyst` or `global:admin`

### 4.1 Create Article

**Workflow:** Create new draft article in a topic.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_content.py` | `TestAnalystEndpoints.test_create_article_with_permission` | Authorized creation |
| `test_content.py` | `TestAnalystEndpoints.test_create_article_no_permission` | Permission denied |
| `test_permissions.py` | `TestRoleBasedAccess.test_reader_cannot_create_content` | RBAC enforcement |

**E2E Coverage:** `frontend/e2e/workflows/analyst.spec.ts`

### 4.2 Edit Draft

**Workflow:** Modify article headline, content, keywords.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_content.py` | `TestAnalystEndpoints.test_edit_article` | Update fields |
| `test_content.py` | `TestAnalystEndpoints.test_get_analyst_drafts` | List own drafts |

### 4.3 Submit for Review

**Workflow:** Change article status from DRAFT to EDITOR queue.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_content.py` | `TestAnalystEndpoints.test_submit_article_for_review` | Status transition |

---

## 5. Editor Workflows

**Required Scope:** `{topic}:editor` or `global:admin`

### 5.1 Review Queue

**Workflow:** View articles awaiting editorial review.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_content.py` | `TestEditorEndpoints.test_get_editor_queue` | List pending articles |

**E2E Coverage:** `frontend/e2e/workflows/editor.spec.ts`

### 5.2 Reject Article

**Workflow:** Return article to analyst with feedback.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_content.py` | `TestEditorEndpoints.test_reject_article` | Status transition, feedback |
| `test_permissions.py` | `TestRoleBasedAccess.test_editor_can_reject_article` | Editor authorization |

### 5.3 Publish Article

**Workflow:** Move article from EDITOR to PUBLISHED status.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_content.py` | `TestEditorEndpoints.test_publish_article` | Publication flow |

---

## 6. Admin Workflows

### 6.1 Topic Admin (`{topic}:admin`)

**Workflow:** Manage content within a specific topic.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_content.py` | `TestAdminContentEndpoints.test_get_all_articles_with_admin` | View all statuses |
| `test_content.py` | `TestAdminContentEndpoints.test_get_all_articles_no_admin` | Permission denied |
| `test_content.py` | `TestAdminContentEndpoints.test_recall_published_article` | Unpublish article |
| `test_content.py` | `TestAdminContentEndpoints.test_deactivate_article` | Soft delete |
| `test_content.py` | `TestAdminContentEndpoints.test_reactivate_article` | Restore article |
| `test_content.py` | `TestAdminContentEndpoints.test_purge_article` | Permanent delete |
| `test_content.py` | `TestAdminContentEndpoints.test_reorder_articles` | Change priority |

**E2E Coverage:** `frontend/e2e/workflows/admin.spec.ts`

### 6.2 Global Admin (`global:admin`)

**Workflow:** System-wide administration.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_admin.py` | `TestUserManagement` | CRUD users, group assignment |
| `test_admin.py` | `TestGroupManagement` | Create/manage groups |
| `test_topics.py` | `TestTopicManagement` | CRUD topics |
| `test_prompts.py` | `TestPromptManagement` | Edit system prompts |
| `test_permissions.py` | `TestRoleBasedAccess.test_admin_can_manage_users` | Admin authorization |

### 6.3 Permission Escalation Prevention

**Workflow:** Prevent users from granting themselves elevated privileges.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_permissions.py` | `TestPermissionEscalation.test_user_cannot_modify_own_roles` | Self-elevation blocked |
| `test_permissions.py` | `TestPermissionEscalation.test_admin_cannot_ban_self` | Self-ban prevention |
| `test_permissions.py` | `TestPermissionEscalation.test_admin_cannot_delete_self` | Self-delete prevention |

---

## 7. Profile & Chat Workflows

### 7.1 Profile Management

**Workflow:** View/update user profile and preferences.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_user_profile.py` | `TestProfileEndpoints.test_get_my_profile` | View own profile |
| `test_user_profile.py` | `TestProfileEndpoints.test_get_my_profile_unauthorized` | Auth required |
| `test_user_profile.py` | `TestProfileEndpoints.test_update_tonality` | Preferences |
| `test_user_profile.py` | `TestProfileEndpoints.test_delete_my_account` | Account deletion |
| `test_permissions.py` | `TestDataIsolation.test_user_can_access_own_profile` | Data isolation |
| `test_permissions.py` | `TestDataIsolation.test_user_can_delete_own_account` | Self-service |

**E2E Coverage:** `frontend/e2e/workflows/profile-chat.spec.ts`

### 7.2 Chat Interface

**Workflow:** AI-powered chat with context awareness.

**Automated Test Coverage:**

| Test File | Test Class/Function | Coverage |
|-----------|---------------------|----------|
| `test_chat.py` | `TestChatEndpoints.test_chat_requires_auth` | Auth required |
| `test_chat.py` | `TestChatEndpoints.test_chat_basic_message` | Message handling |
| `test_chat.py` | `TestChatEndpoints.test_chat_with_context` | Context passing |

### 7.3 UI Actions (Chat-Triggered)

**Workflow:** Chat agent triggers frontend navigation and actions.

**Automated Test Coverage:**

| Test File | Type | Coverage |
|-----------|------|----------|
| `frontend/src/lib/stores/actions.test.ts` | Unit | Action store behavior |
| `frontend/e2e/ui-actions.spec.ts` | E2E | Full action flow |

**Supported Actions:**
- `navigate_topic` - Switch topic tabs
- `search_articles` - Execute search
- `open_article` - Display article
- `download_pdf` - Generate PDF

---

## 8. Test Coverage Matrix

### Backend API Endpoints

| Endpoint Group | Test File | Tests | Coverage |
|----------------|-----------|-------|----------|
| Health (`/health`) | `test_health.py` | 3 | 100% |
| Auth (`/api/auth/*`) | `test_auth.py` | 10 | 100% |
| Profile (`/api/profile/*`) | `test_user_profile.py` | 8 | 100% |
| Chat (`/api/chat/*`) | `test_chat.py` | 6 | 100% |
| Content (`/api/content/*`) | `test_content.py` | 25 | 100% |
| Admin (`/api/admin/*`) | `test_admin.py` | 15 | 100% |
| Topics (`/api/topics/*`) | `test_topics.py` | 10 | 100% |
| Prompts (`/api/prompts/*`) | `test_prompts.py` | 12 | 100% |
| Permissions | `test_permissions.py` | 25 | 100% |

### Security Test Coverage

| Security Category | Tests in `test_permissions.py` |
|-------------------|--------------------------------|
| Authentication | 4 tests (token validation, expiry, format, signing) |
| Role-Based Access | 5 tests (reader, analyst, editor, admin restrictions) |
| Scope-Based Permissions | 3 tests (topic isolation, global admin, multi-scope) |
| Permission Escalation | 3 tests (self-role modify, self-ban, self-delete) |
| Token Security | 3 tests (uniqueness, claims, test secret) |
| Protected Endpoints | 3 tests (content, prompts, topics auth) |
| Data Isolation | 4 tests (profile access, account deletion, tonality) |

### Frontend Test Coverage

| Test Type | Location | Coverage |
|-----------|----------|----------|
| Unit Tests | `src/lib/stores/actions.test.ts` | Action store logic |
| E2E Tests | `e2e/workflows/*.spec.ts` | Full user journeys |
| E2E Tests | `e2e/ui-actions.spec.ts` | Chat-triggered actions |

---

## Running Tests

### Quick Commands

```bash
# Run all tests (backend + frontend unit + E2E)
./scripts/run-tests.sh

# Backend tests only
./scripts/run-tests.sh backend

# Frontend unit tests only
./scripts/run-tests.sh frontend

# E2E tests only (requires full stack)
./scripts/run-tests.sh e2e

# Quick tests (no E2E)
./scripts/run-tests.sh quick

# Windows PowerShell
.\scripts\run-tests.ps1 -TestType backend
```

### Test Markers (Backend)

```bash
# Run only unit tests (fast, no external dependencies)
uv run pytest -m unit

# Run only integration tests (requires database)
uv run pytest -m integration

# Run security/permission tests
uv run pytest tests/api/test_permissions.py -v
```

---

## Manual Testing Checklist

For workflows that require manual verification (UI interactions, visual elements):

### Critical Path (Must Pass)

- [ ] LinkedIn OAuth login completes successfully
- [ ] User can browse and read published articles
- [ ] Search returns relevant results
- [ ] Chat responds appropriately
- [ ] Analyst can create and submit articles
- [ ] Editor can review and publish articles
- [ ] HITL approval flow works via WebSocket

### Visual/UX Elements

- [ ] Markdown renders correctly in articles
- [ ] PDF generation produces valid documents
- [ ] Mobile responsive layout works
- [ ] Error messages are user-friendly
- [ ] Loading states display appropriately

---

## Related Documentation

- [Regression Testing Guide](./13-regression-testing.md) - Test infrastructure and CI/CD
- [Multi-Agent Architecture](./08-multi-agent-architecture.md) - System design
- [Frontend Documentation](./09-frontend.md) - UI components
