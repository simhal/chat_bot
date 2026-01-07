# Regression Testing Guide

This document describes the automated test suite for the Chatbot Application, including how to run tests, understand the test architecture, and add new tests.

## Table of Contents

1. [Overview](#1-overview)
2. [Test Architecture](#2-test-architecture)
3. [Running Tests](#3-running-tests)
4. [Backend Tests](#4-backend-tests)
5. [Frontend Tests](#5-frontend-tests)
6. [E2E Tests](#6-e2e-tests)
7. [Test Containers](#7-test-containers)
8. [Writing New Tests](#8-writing-new-tests)
9. [CI/CD Integration](#9-cicd-integration)

---

## 1. Overview

The test suite provides comprehensive coverage across:

- **Backend API Tests**: 100+ tests covering all REST endpoints
- **Frontend Unit Tests**: Component and store testing with Vitest
- **E2E Workflow Tests**: Full user journey testing with Playwright

### Test Categories

| Category | Tool | Location | Purpose |
|----------|------|----------|---------|
| Backend Unit | pytest | `backend/tests/` | Test individual functions and classes |
| Backend Integration | pytest | `backend/tests/` | Test API endpoints with database |
| Frontend Unit | Vitest | `frontend/src/**/*.test.ts` | Test Svelte components and stores |
| E2E Workflow | Playwright | `frontend/e2e/` | Test complete user workflows |

---

## 2. Test Architecture

### Backend Test Structure

```
backend/tests/
├── __init__.py
├── conftest.py              # Shared fixtures and configuration
├── fixtures/
│   ├── __init__.py
│   ├── factories.py         # Factory Boy factories for test data
│   └── seed_test_data.py    # E2E test data seeding
└── api/
    ├── __init__.py
    ├── test_health.py       # Health endpoint tests
    ├── test_auth.py         # Authentication tests
    ├── test_user_profile.py # Profile endpoint tests
    ├── test_chat.py         # Chat endpoint tests
    ├── test_content.py      # Content management tests
    ├── test_admin.py        # Admin endpoint tests
    ├── test_topics.py       # Topic management tests
    └── test_prompts.py      # Prompt management tests
```

### Frontend Test Structure

```
frontend/
├── src/
│   ├── lib/stores/
│   │   └── actions.test.ts  # Store unit tests
│   └── test-setup.ts        # Test configuration
├── e2e/
│   ├── ui-actions.spec.ts   # UI action handler tests
│   └── workflows/
│       ├── reader.spec.ts   # Reader workflow tests
│       ├── analyst.spec.ts  # Analyst workflow tests
│       ├── editor.spec.ts   # Editor workflow tests
│       ├── admin.spec.ts    # Admin workflow tests
│       └── profile-chat.spec.ts  # Profile and chat tests
├── vitest.config.ts         # Vitest configuration
└── playwright.config.ts     # Playwright configuration
```

---

## 3. Running Tests

### Quick Start

```bash
# Run all tests (backend + frontend unit)
./scripts/run-tests.sh

# Windows PowerShell
.\scripts\run-tests.ps1
```

### Test Runner Options

| Command | Description |
|---------|-------------|
| `./scripts/run-tests.sh` | Run all tests |
| `./scripts/run-tests.sh backend` | Backend tests only |
| `./scripts/run-tests.sh frontend` | Frontend unit tests only |
| `./scripts/run-tests.sh e2e` | E2E tests with full stack |
| `./scripts/run-tests.sh unit` | Unit tests only (fast) |
| `./scripts/run-tests.sh integration` | Integration tests only |

### Options

| Flag | Description |
|------|-------------|
| `--coverage` | Generate coverage reports |
| `--verbose` | Verbose output |
| `--keep` | Keep containers running after tests |
| `--no-build` | Skip rebuilding containers |

### Manual Test Commands

```bash
# Backend tests (from backend directory)
cd backend
uv pip install -e ".[test]"
uv run pytest tests/ -v

# Frontend unit tests (from frontend directory)
cd frontend
npm run test:run

# Frontend E2E tests (from frontend directory)
cd frontend
npx playwright test
```

---

## 4. Backend Tests

### Test Markers

Tests are organized using pytest markers:

```python
@pytest.mark.unit        # No external dependencies
@pytest.mark.integration # Requires database
@pytest.mark.e2e        # Requires all services
@pytest.mark.slow       # Long-running tests
```

### Running Specific Markers

```bash
# Run only unit tests
uv run pytest -m unit

# Run only integration tests
uv run pytest -m integration

# Skip slow tests
uv run pytest -m "not slow"
```

### Available Fixtures

| Fixture | Description |
|---------|-------------|
| `db_session` | Clean database session per test |
| `client` | FastAPI TestClient |
| `test_user` | User with reader access |
| `test_analyst` | User with analyst role |
| `test_editor` | User with editor role |
| `test_admin` | User with global admin |
| `auth_headers` | Authorization headers for reader |
| `analyst_headers` | Authorization headers for analyst |
| `editor_headers` | Authorization headers for editor |
| `admin_headers` | Authorization headers for admin |
| `test_topic` | Test topic |
| `test_article` | Draft article |
| `published_article` | Published article |
| `mock_redis` | Mocked Redis client |
| `mock_chromadb` | Mocked ChromaDB client |
| `mock_openai` | Mocked OpenAI client |

### Test Coverage by Endpoint

| Endpoint Group | Test File | Coverage |
|----------------|-----------|----------|
| Health (`/health`, `/`) | `test_health.py` | 100% |
| Auth (`/api/auth/*`) | `test_auth.py` | 100% |
| Profile (`/api/profile/*`) | `test_user_profile.py` | 100% |
| Chat (`/api/chat/*`) | `test_chat.py` | 100% |
| Content (`/api/content/*`) | `test_content.py` | 100% |
| Admin (`/api/admin/*`) | `test_admin.py` | 100% |
| Topics (`/api/topics/*`) | `test_topics.py` | 100% |
| Prompts (`/api/prompts/*`) | `test_prompts.py` | 100% |
| Permissions & Security | `test_permissions.py` | 100% |

### Security & Permission Tests

The `test_permissions.py` file provides comprehensive security testing:

| Test Category | Tests Covered |
|---------------|---------------|
| Authentication | Token validation, expired tokens, malformed tokens, wrong secret |
| Role-Based Access | Reader, analyst, editor, admin role restrictions |
| Scope-Based Permissions | Topic-specific scopes, global admin access, multiple scopes |
| Permission Escalation | Self-role modification, admin self-ban/delete prevention |
| Token Security | Token uniqueness, required claims, test secret isolation |
| Protected Endpoints | Admin-only operations, content management auth |
| Data Isolation | User profile access, account deletion, tonality settings |

---

## 5. Frontend Tests

### Unit Tests (Vitest)

```bash
# Run all unit tests
npm run test:run

# Watch mode
npm run test

# With coverage
npm run test:run -- --coverage
```

### Test Setup

The `src/test-setup.ts` file mocks SvelteKit modules:

- `$app/environment` - Browser/dev flags
- `$app/navigation` - goto, invalidate functions
- `$app/stores` - page, navigating, updated stores

---

## 6. E2E Tests

### Playwright Configuration

E2E tests run against a full application stack:

- Backend API at `http://localhost:8000`
- Frontend at `http://localhost:3000`
- PostgreSQL, Redis, ChromaDB test containers

### Running E2E Tests

```bash
# Start test infrastructure
docker-compose -f docker-compose.test.yml --profile e2e up -d

# Run tests
cd frontend
npx playwright test

# With UI mode
npx playwright test --ui

# View report
npx playwright show-report
```

### E2E Test Organization

Tests are organized by user role/workflow matching `docs/12-testing-workflows.md`:

| File | Workflows Covered |
|------|-------------------|
| `reader.spec.ts` | Browse, search, read, rate articles |
| `analyst.spec.ts` | Create, edit, submit articles |
| `editor.spec.ts` | Review, reject, publish articles |
| `admin.spec.ts` | Content management, user management |
| `profile-chat.spec.ts` | Profile settings, chat interactions |
| `ui-actions.spec.ts` | Chat-triggered UI actions |

---

## 7. Test Containers

### Docker Compose Test Configuration

The `docker-compose.test.yml` provides isolated test infrastructure:

| Service | Port | Purpose |
|---------|------|---------|
| `postgres-test` | 5433 | Test database (fresh each run) |
| `redis-test` | 6380 | Test cache (no persistence) |
| `chroma-test` | 8002 | Test vector DB (in-memory) |
| `backend-test` | 8001 | Backend for API tests |
| `backend-e2e` | 8000 | Backend for E2E tests |
| `frontend-test` | 3000 | Frontend for E2E tests |
| `celery-worker-test` | - | Background worker for E2E |

### Starting Containers Manually

```bash
# Start just the databases
docker-compose -f docker-compose.test.yml up -d postgres-test redis-test chroma-test

# Start full E2E stack
docker-compose -f docker-compose.test.yml --profile e2e up -d

# Stop and clean up
docker-compose -f docker-compose.test.yml down -v
```

### Environment Variables for Tests

```bash
# Database
DATABASE_URL=postgresql://chatbot_test_user:chatbot_test_password@localhost:5433/chatbot_test

# Redis
REDIS_URL=redis://localhost:6380/0
REDIS_HOST=localhost
REDIS_PORT=6380

# ChromaDB
CHROMA_HOST=localhost
CHROMA_PORT=8002

# Testing mode
TESTING=true
JWT_SECRET_KEY=test-secret-key-for-testing-only
```

---

## 8. Writing New Tests

### Backend Test Example

```python
# tests/api/test_example.py
import pytest
from fastapi.testclient import TestClient

class TestNewEndpoint:
    """Test new endpoint functionality."""

    def test_endpoint_no_auth(self, client: TestClient):
        """Test endpoint without authentication."""
        response = client.get("/api/new-endpoint")
        assert response.status_code == 403

    def test_endpoint_with_auth(
        self, client: TestClient, auth_headers, mock_redis
    ):
        """Test endpoint with valid authentication."""
        response = client.get("/api/new-endpoint", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "expected_field" in data

    @pytest.mark.integration
    def test_endpoint_with_database(
        self, client: TestClient, auth_headers, test_topic, db_session
    ):
        """Test endpoint that requires database."""
        response = client.get(
            f"/api/new-endpoint/{test_topic.slug}",
            headers=auth_headers
        )
        assert response.status_code == 200
```

### E2E Test Example

```typescript
// e2e/workflows/example.spec.ts
import { test, expect, type Page } from '@playwright/test';

async function mockAuth(page: Page) {
    await page.addInitScript(() => {
        localStorage.setItem('auth', JSON.stringify({
            access_token: 'test-token',
            user: { id: 1, email: 'test@test.com', scopes: ['macro:reader'] }
        }));
    });
}

test.describe('New Feature Workflow', () => {
    test.beforeEach(async ({ page }) => {
        await mockAuth(page);
    });

    test('should perform action', async ({ page }) => {
        await page.goto('/');

        await page.click('[data-testid="action-button"]');

        await expect(page.locator('[data-testid="result"]')).toBeVisible();
    });
});
```

### Factory Example

```python
# tests/fixtures/factories.py
class NewModelFactory(BaseFactory):
    """Factory for creating NewModel instances."""

    class Meta:
        model = NewModel

    name = Faker("word")
    status = "active"
    created_at = Faker("date_time")
```

---

## 9. CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: chatbot_test
          POSTGRES_USER: chatbot_test_user
          POSTGRES_PASSWORD: chatbot_test_password
        ports:
          - 5433:5432
      redis:
        image: redis:7-alpine
        ports:
          - 6380:6379

    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install uv
        run: pip install uv
      - name: Install dependencies
        run: cd backend && uv pip install -e ".[test]"
      - name: Run tests
        run: cd backend && uv run pytest tests/ -v --cov=.
        env:
          DATABASE_URL: postgresql://chatbot_test_user:chatbot_test_password@localhost:5433/chatbot_test
          REDIS_URL: redis://localhost:6380/0
          TESTING: true

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install dependencies
        run: cd frontend && npm ci
      - name: Run unit tests
        run: cd frontend && npm run test:run

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start test containers
        run: docker-compose -f docker-compose.test.yml --profile e2e up -d --build
      - name: Wait for services
        run: sleep 30
      - name: Run E2E tests
        run: |
          cd frontend
          npm ci
          npx playwright install chromium
          npx playwright test
        env:
          BASE_URL: http://localhost:3000
```

---

## Troubleshooting

### Common Issues

**Tests fail to connect to database:**
```bash
# Ensure test containers are running
docker-compose -f docker-compose.test.yml up -d postgres-test redis-test chroma-test

# Check container health
docker-compose -f docker-compose.test.yml ps
```

**E2E tests timeout:**
```bash
# Increase timeout in playwright.config.ts
timeout: 60000,

# Or wait longer for services
await page.waitForTimeout(5000);
```

**Mock fixtures not working:**
```python
# Ensure mock_redis fixture is included in test function
def test_example(self, client, auth_headers, mock_redis):
    ...
```

**Frontend tests can't find modules:**
```bash
# Reinstall dependencies
cd frontend && rm -rf node_modules && npm ci
```

---

## Related Documentation

- [Testing Workflows](./12-testing-workflows.md) - Manual testing checklist
- [Multi-Agent Architecture](./08-multi-agent-architecture.md) - System architecture
- [Frontend Documentation](./09-frontend.md) - Frontend structure
