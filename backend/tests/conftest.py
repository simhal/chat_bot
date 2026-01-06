"""
Pytest configuration and fixtures for backend tests.

This module provides:
- Database fixtures (clean database per test)
- Authentication fixtures (test users with various roles)
- HTTP client fixtures (async test client)
- Mock fixtures for external services
"""
import os
import pytest
from typing import Generator, AsyncGenerator
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import secrets

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from fastapi.testclient import TestClient
from jose import jwt

# Set testing environment before importing app modules
os.environ["TESTING"] = "true"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["JWT_ALGORITHM"] = "HS256"

from models import Base, User, Group, Topic, ContentArticle, ArticleStatus, PromptModule, PromptType
from database import get_db


# =============================================================================
# TEST TOKEN CREATION (bypasses Redis)
# =============================================================================

def create_test_token(user_id: int, email: str, scopes: list = None) -> str:
    """
    Create a test JWT token without Redis dependency.
    This is for testing only - doesn't store in Redis cache.
    """
    token_id = secrets.token_urlsafe(32)
    expire = datetime.utcnow() + timedelta(hours=1)

    token_data = {
        "sub": str(user_id),
        "email": email,
        "name": "Test",
        "surname": "User",
        "picture": None,
        "scopes": scopes or [],
        "jti": token_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    }

    return jwt.encode(
        token_data,
        os.environ["JWT_SECRET_KEY"],
        algorithm=os.environ["JWT_ALGORITHM"]
    )


# =============================================================================
# DATABASE FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def test_engine():
    """Create a test database engine.

    Uses SQLite in-memory for fast tests, or PostgreSQL for integration tests.
    """
    database_url = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

    if "sqlite" in database_url:
        # SQLite configuration for in-memory testing
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        # PostgreSQL configuration
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10
        )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # Cleanup - skip drop_all for PostgreSQL to avoid constraint name issues
    # (PostgreSQL test container uses tmpfs and will be destroyed anyway)
    if "sqlite" in database_url:
        Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session, None, None]:
    """Create a fresh database session for each test.

    Uses nested transactions with savepoints to rollback after each test.
    """
    connection = test_engine.connect()
    transaction = connection.begin()

    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = TestSessionLocal()

    # Begin a nested transaction (savepoint)
    nested = connection.begin_nested()

    # If the application code calls session.commit(), restart the nested transaction
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        nonlocal nested
        if transaction.nested and not transaction._parent.nested:
            nested = connection.begin_nested()

    yield session

    # Rollback everything
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def override_get_db(db_session):
    """Override the get_db dependency to use test session."""
    def _get_test_db():
        try:
            yield db_session
        finally:
            pass
    return _get_test_db


# =============================================================================
# TEST CLIENT FIXTURES
# =============================================================================

@pytest.fixture(scope="function")
def client(override_get_db, mock_redis) -> Generator[TestClient, None, None]:
    """Create a synchronous test client with mocked Redis."""
    # Import app here to avoid circular imports
    from main import app

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# =============================================================================
# USER AND AUTH FIXTURES
# =============================================================================

@pytest.fixture(scope="function")
def test_user(db_session) -> User:
    """Get or create a basic test user with reader access."""
    # Try to get existing seeded user first
    user = db_session.query(User).filter(User.email == "reader@test.com").first()
    if user:
        return user

    # Fallback: create user (for SQLite in-memory tests without seeding)
    user = User(
        email="reader@test.com",
        name="Test",
        surname="Reader",
        linkedin_sub="linkedin_reader_123",
        active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture(scope="function")
def test_analyst(db_session, test_topic) -> User:
    """Get or create a test user with analyst role."""
    # Try to get existing seeded user first
    user = db_session.query(User).filter(User.email == "analyst@test.com").first()
    if user:
        return user

    # Fallback: create user (for SQLite in-memory tests without seeding)
    user = User(
        email="analyst@test.com",
        name="Test",
        surname="Analyst",
        linkedin_sub="linkedin_analyst_123",
        active=True,
    )
    db_session.add(user)
    db_session.flush()

    # Get or create analyst group for topic
    group_name = f"{test_topic.slug}:analyst"
    group = db_session.query(Group).filter(Group.name == group_name).first()
    if not group:
        group = Group(
            name=group_name,
            groupname=test_topic.slug,
            role="analyst",
            topic_id=test_topic.id,
        )
        db_session.add(group)
        db_session.flush()

    if group not in user.groups:
        user.groups.append(group)
        db_session.flush()
    return user


@pytest.fixture(scope="function")
def test_editor(db_session, test_topic) -> User:
    """Get or create a test user with editor role."""
    # Try to get existing seeded user first
    user = db_session.query(User).filter(User.email == "editor@test.com").first()
    if user:
        return user

    # Fallback: create user (for SQLite in-memory tests without seeding)
    user = User(
        email="editor@test.com",
        name="Test",
        surname="Editor",
        linkedin_sub="linkedin_editor_123",
        active=True,
    )
    db_session.add(user)
    db_session.flush()

    # Get or create editor group for topic
    group_name = f"{test_topic.slug}:editor"
    group = db_session.query(Group).filter(Group.name == group_name).first()
    if not group:
        group = Group(
            name=group_name,
            groupname=test_topic.slug,
            role="editor",
            topic_id=test_topic.id,
        )
        db_session.add(group)
        db_session.flush()

    if group not in user.groups:
        user.groups.append(group)
        db_session.flush()
    return user


@pytest.fixture(scope="function")
def test_admin(db_session) -> User:
    """Get or create a test user with global admin role."""
    # Try to get existing seeded user first
    user = db_session.query(User).filter(User.email == "admin@test.com").first()
    if user:
        return user

    # Fallback: create user (for SQLite in-memory tests without seeding)
    user = User(
        email="admin@test.com",
        name="Test",
        surname="Admin",
        linkedin_sub="linkedin_admin_123",
        active=True,
    )
    db_session.add(user)
    db_session.flush()

    # Get or create global admin group
    group = db_session.query(Group).filter(Group.name == "global:admin").first()
    if not group:
        group = Group(
            name="global:admin",
            groupname="global",
            role="admin",
        )
        db_session.add(group)
        db_session.flush()

    if group not in user.groups:
        user.groups.append(group)
        db_session.flush()
    return user


@pytest.fixture(scope="function")
def reader_token(test_user) -> str:
    """Create an access token for the reader user."""
    return create_test_token(
        user_id=test_user.id,
        email=test_user.email,
        scopes=[]
    )


@pytest.fixture(scope="function")
def analyst_token(test_analyst, test_topic) -> str:
    """Create an access token for the analyst user."""
    return create_test_token(
        user_id=test_analyst.id,
        email=test_analyst.email,
        scopes=[f"{test_topic.slug}:analyst"]
    )


@pytest.fixture(scope="function")
def editor_token(test_editor, test_topic) -> str:
    """Create an access token for the editor user."""
    return create_test_token(
        user_id=test_editor.id,
        email=test_editor.email,
        scopes=[f"{test_topic.slug}:editor"]
    )


@pytest.fixture(scope="function")
def admin_token(test_admin) -> str:
    """Create an access token for the admin user."""
    return create_test_token(
        user_id=test_admin.id,
        email=test_admin.email,
        scopes=["global:admin"]
    )


@pytest.fixture(scope="function")
def auth_headers(reader_token) -> dict:
    """Create authorization headers for reader user."""
    return {"Authorization": f"Bearer {reader_token}"}


@pytest.fixture(scope="function")
def analyst_headers(analyst_token) -> dict:
    """Create authorization headers for analyst user."""
    return {"Authorization": f"Bearer {analyst_token}"}


@pytest.fixture(scope="function")
def editor_headers(editor_token) -> dict:
    """Create authorization headers for editor user."""
    return {"Authorization": f"Bearer {editor_token}"}


@pytest.fixture(scope="function")
def admin_headers(admin_token) -> dict:
    """Create authorization headers for admin user."""
    return {"Authorization": f"Bearer {admin_token}"}


# =============================================================================
# TOPIC AND CONTENT FIXTURES
# =============================================================================

@pytest.fixture(scope="function")
def test_topic(db_session) -> Topic:
    """Get or create the 'macro' topic for testing.

    Uses 'macro' to match seeded test data for PostgreSQL tests.
    Falls back to creating topic for SQLite in-memory tests.
    """
    # Try to get existing seeded topic first
    topic = db_session.query(Topic).filter(Topic.slug == "macro").first()
    if topic:
        return topic

    # Fallback: create topic (for SQLite in-memory tests without seeding)
    topic = Topic(
        slug="macro",
        title="Macroeconomic Research",
        description="A topic for testing",
        visible=True,
        searchable=True,
        active=True,
        article_order="date",
    )
    db_session.add(topic)
    db_session.flush()
    return topic


@pytest.fixture(scope="function")
def test_article(db_session, test_topic, test_analyst) -> ContentArticle:
    """Create a test article in draft status."""
    article = ContentArticle(
        topic_id=test_topic.id,
        topic=test_topic.slug,
        headline="Test Article Headline",
        author=f"{test_analyst.name} {test_analyst.surname}",
        status=ArticleStatus.DRAFT,
        keywords="test, article, sample",
        created_by_agent="test",
    )
    db_session.add(article)
    db_session.flush()
    return article


@pytest.fixture(scope="function")
def published_article(db_session, test_topic, test_analyst, test_editor) -> ContentArticle:
    """Create a published test article."""
    article = ContentArticle(
        topic_id=test_topic.id,
        topic=test_topic.slug,
        headline="Published Test Article",
        author=f"{test_analyst.name} {test_analyst.surname}",
        editor=f"{test_editor.name} {test_editor.surname}",
        status=ArticleStatus.PUBLISHED,
        keywords="published, test, article",
        created_by_agent="test",
        readership_count=10,
        rating=4,
        rating_count=5,
    )
    db_session.add(article)
    db_session.flush()
    return article


# =============================================================================
# PROMPT FIXTURES
# =============================================================================

@pytest.fixture(scope="function")
def test_prompt(db_session) -> PromptModule:
    """Create a test prompt module."""
    prompt = PromptModule(
        name="Test General Prompt",
        prompt_type=PromptType.GENERAL,
        template_text="You are a helpful assistant for testing.",
        description="Test prompt for unit tests",
        is_active=True,
    )
    db_session.add(prompt)
    db_session.flush()
    return prompt


@pytest.fixture(scope="function")
def test_tonality(db_session) -> PromptModule:
    """Create a test tonality option."""
    tonality = PromptModule(
        name="Professional Tone",
        prompt_type=PromptType.TONALITY,
        template_text="Respond in a professional, formal manner.",
        description="Professional writing style",
        is_default=True,
        is_active=True,
    )
    db_session.add(tonality)
    db_session.flush()
    return tonality


# =============================================================================
# MOCK FIXTURES
# =============================================================================

@pytest.fixture(scope="function")
def mock_redis():
    """Mock Redis client and TokenCache for tests."""
    with patch("redis_client.get_redis_client") as mock_client, \
         patch("redis_client.TokenCache") as mock_cache, \
         patch("auth.TokenCache") as mock_auth_cache:

        # Mock Redis client
        redis_mock = MagicMock()
        redis_mock.get.return_value = None
        redis_mock.set.return_value = True
        redis_mock.delete.return_value = True
        redis_mock.exists.return_value = False
        mock_client.return_value = redis_mock

        # Mock TokenCache methods to return valid data for test tokens
        def mock_get_access_token(token_id):
            # Always return valid cache data for test tokens
            return {"user_id": 1, "email": "test@test.com", "scopes": []}

        mock_cache.get_access_token.side_effect = mock_get_access_token
        mock_cache.store_access_token.return_value = None
        mock_cache.delete_access_token.return_value = None
        mock_cache.get_refresh_token.return_value = 1
        mock_cache.store_refresh_token.return_value = None
        mock_cache.delete_refresh_token.return_value = None

        mock_auth_cache.get_access_token.side_effect = mock_get_access_token
        mock_auth_cache.store_access_token.return_value = None
        mock_auth_cache.delete_access_token.return_value = None
        mock_auth_cache.get_refresh_token.return_value = 1
        mock_auth_cache.store_refresh_token.return_value = None
        mock_auth_cache.delete_refresh_token.return_value = None

        yield redis_mock


@pytest.fixture(scope="function")
def mock_chromadb():
    """Mock ChromaDB client and VectorService for tests that don't need real vector DB."""
    with patch("services.vector_service._get_chroma_client") as mock_client, \
         patch("services.vector_service.VectorService.get_article_data") as mock_get_data, \
         patch("services.vector_service.VectorService.add_article") as mock_add, \
         patch("services.vector_service.VectorService.delete_article") as mock_delete:

        chroma_mock = MagicMock()
        collection_mock = MagicMock()
        collection_mock.query.return_value = {"documents": [], "ids": [], "metadatas": []}
        collection_mock.add.return_value = None
        collection_mock.delete.return_value = None
        collection_mock.get.return_value = {"documents": [], "ids": [], "metadatas": []}
        collection_mock.count.return_value = 0
        chroma_mock.get_or_create_collection.return_value = collection_mock
        chroma_mock.heartbeat.return_value = True
        mock_client.return_value = (chroma_mock, collection_mock)

        # Mock VectorService static methods
        mock_get_data.return_value = None  # Return None to use PostgreSQL fallback
        mock_add.return_value = True
        mock_delete.return_value = True

        yield chroma_mock


@pytest.fixture(scope="function")
def mock_openai():
    """Mock OpenAI client for tests that don't need real API calls."""
    with patch("langchain_openai.ChatOpenAI") as mock:
        openai_mock = MagicMock()
        openai_mock.invoke.return_value = MagicMock(content="Test response from AI")
        mock.return_value = openai_mock
        yield openai_mock


# =============================================================================
# INTEGRATION TEST MARKERS
# =============================================================================

def pytest_configure(config):
    """Add custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (no external dependencies)")
    config.addinivalue_line("markers", "integration: Integration tests (requires database)")
    config.addinivalue_line("markers", "e2e: End-to-end tests (requires all services)")
    config.addinivalue_line("markers", "slow: Slow tests that can be skipped")
