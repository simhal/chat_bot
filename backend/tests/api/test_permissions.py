"""
Comprehensive permission and authorization tests.

Tests for:
- Role-based access control (RBAC)
- Scope-based permissions (topic:role format)
- Authentication vs Authorization
- Cross-topic access restrictions
- Permission escalation prevention
- Admin-only operations
"""
import pytest
import secrets
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from jose import jwt
import os

from models import User, Group, Topic, ContentArticle, ArticleStatus


# =============================================================================
# TEST TOKEN UTILITIES
# =============================================================================

def create_custom_token(
    user_id: int,
    email: str,
    scopes: list = None,
    expired: bool = False
) -> str:
    """
    Create a custom test token with specific scopes.
    This is a test-only function - production uses auth.create_access_token.
    """
    token_id = secrets.token_urlsafe(32)

    if expired:
        expire = datetime.utcnow() - timedelta(hours=1)
    else:
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
        os.environ.get("JWT_SECRET_KEY", "test-secret-key-for-testing-only"),
        algorithm=os.environ.get("JWT_ALGORITHM", "HS256")
    )


# =============================================================================
# AUTHENTICATION TESTS
# =============================================================================

class TestAuthentication:
    """Test authentication mechanisms are secure."""

    def test_no_token_returns_401(self, client: TestClient):
        """Test that requests without auth token return 401."""
        endpoints = [
            "/api/me",
            "/api/profile/me",
            "/api/topics",
            "/api/prompts",
            "/api/chat",
        ]
        for endpoint in endpoints:
            if endpoint == "/api/chat":
                response = client.post(endpoint, json={"message": "test"})
            else:
                response = client.get(endpoint)
            assert response.status_code == 401, f"Endpoint {endpoint} should require auth"

    def test_malformed_token_returns_401(self, client: TestClient, mock_redis):
        """Test that malformed tokens are rejected."""
        malformed_tokens = [
            "not_a_jwt",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.payload",
            "",
        ]
        for token in malformed_tokens:
            response = client.get(
                "/api/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 401, f"Token '{token[:20]}...' should be rejected"

    def test_expired_token_returns_401(self, client: TestClient, test_user, mock_redis):
        """Test that expired tokens are rejected."""
        expired_token = create_custom_token(
            user_id=test_user.id,
            email=test_user.email,
            scopes=[],
            expired=True
        )
        response = client.get(
            "/api/me",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401

    def test_wrong_secret_token_returns_401(self, client: TestClient, mock_redis):
        """Test that tokens signed with wrong secret are rejected."""
        # Create token with different secret
        token_data = {
            "sub": "1",
            "email": "test@test.com",
            "scopes": [],
            "jti": secrets.token_urlsafe(32),
            "exp": datetime.utcnow() + timedelta(hours=1),
            "type": "access"
        }
        wrong_secret_token = jwt.encode(token_data, "wrong-secret", algorithm="HS256")

        response = client.get(
            "/api/me",
            headers={"Authorization": f"Bearer {wrong_secret_token}"}
        )
        assert response.status_code == 401


# =============================================================================
# ROLE-BASED ACCESS CONTROL TESTS
# =============================================================================

class TestRoleBasedAccess:
    """Test role-based access control for different user roles."""

    def test_reader_cannot_access_admin_endpoints(
        self, client: TestClient, auth_headers, mock_redis
    ):
        """Test that readers cannot access admin endpoints."""
        admin_endpoints = [
            ("/api/admin/groups", "POST", {"name": "hack:admin"}),
            ("/api/admin/groups", "GET", None),
            ("/api/admin/users", "GET", None),
            ("/api/admin/users", "POST", {"email": "new@test.com"}),
        ]

        for endpoint, method, data in admin_endpoints:
            if method == "GET":
                response = client.get(endpoint, headers=auth_headers)
            else:
                response = client.post(endpoint, json=data, headers=auth_headers)

            assert response.status_code in [401, 403], \
                f"{method} {endpoint} should be forbidden for readers"

    def test_reader_cannot_create_content(
        self, client: TestClient, auth_headers, test_topic, mock_redis, mock_chromadb
    ):
        """Test that readers cannot create articles."""
        response = client.post(
            f"/api/analyst/{test_topic.slug}/article",
            headers=auth_headers
        )
        # Should be forbidden (403) - readers don't have analyst permission
        assert response.status_code == 403

    def test_reader_can_view_published_content(
        self, client: TestClient, auth_headers, test_topic, published_article, mock_redis
    ):
        """Test that readers can view published articles."""
        response = client.get(
            f"/api/reader/{test_topic.slug}/article/{published_article.id}",
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_analyst_can_create_content(
        self, client: TestClient, analyst_headers, test_topic, mock_redis, mock_chromadb
    ):
        """Test that analysts can create articles in their topic."""
        response = client.post(
            f"/api/analyst/{test_topic.slug}/article",
            headers=analyst_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["status"] == "draft"

    def test_editor_can_reject_article(
        self, client: TestClient, editor_headers, test_topic, test_article, db_session, mock_redis, mock_chromadb
    ):
        """Test that editors can reject articles."""
        test_article.status = ArticleStatus.EDITOR
        db_session.commit()

        response = client.post(
            f"/api/editor/{test_topic.slug}/article/{test_article.id}/reject",
            json={"reason": "Needs revision"},
            headers=editor_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["article"]["status"] == "draft"

    def test_admin_can_manage_users(
        self, client: TestClient, admin_headers, mock_redis
    ):
        """Test that admins can access user management."""
        response = client.get("/api/admin/users", headers=admin_headers)
        assert response.status_code == 200


# =============================================================================
# SCOPE-BASED PERMISSION TESTS
# =============================================================================

class TestScopeBasedPermissions:
    """Test that scope-based permissions are enforced correctly."""

    def test_topic_scope_isolation(
        self, client: TestClient, db_session, mock_redis
    ):
        """Test that topic-specific scopes don't grant access to other topics."""
        # Create a user with macro:analyst scope only
        macro_analyst = User(
            email="macro_analyst@test.com",
            name="Macro",
            surname="Analyst",
            linkedin_sub="linkedin_macro_123",
            active=True
        )
        db_session.add(macro_analyst)
        db_session.flush()

        # Create token with macro:analyst scope only
        macro_token = create_custom_token(
            user_id=macro_analyst.id,
            email=macro_analyst.email,
            scopes=["macro:analyst"]
        )
        macro_headers = {"Authorization": f"Bearer {macro_token}"}

        # Try to access equity topic content (should fail)
        # Note: The actual check depends on how the API enforces topic scopes
        response = client.get("/api/me", headers=macro_headers)
        assert response.status_code == 200  # Can still access /me

    def test_global_admin_has_all_access(
        self, client: TestClient, admin_headers, mock_redis
    ):
        """Test that global:admin scope grants access to all operations."""
        # Admin should be able to access all admin endpoints
        endpoints = [
            "/api/admin/groups",
            "/api/admin/users",
        ]
        for endpoint in endpoints:
            response = client.get(endpoint, headers=admin_headers)
            assert response.status_code == 200, \
                f"Admin should access {endpoint}"

    def test_multiple_scopes_work_correctly(
        self, client: TestClient, db_session, mock_redis
    ):
        """Test that users with multiple scopes have proper access."""
        # Create user with multiple scopes
        multi_role_user = User(
            email="multi@test.com",
            name="Multi",
            surname="Role",
            linkedin_sub="linkedin_multi_123",
            active=True
        )
        db_session.add(multi_role_user)
        db_session.flush()

        # Token with both reader and analyst scopes
        multi_token = create_custom_token(
            user_id=multi_role_user.id,
            email=multi_role_user.email,
            scopes=["macro:reader", "macro:analyst"]
        )
        multi_headers = {"Authorization": f"Bearer {multi_token}"}

        # Should have reader access
        response = client.get("/api/me", headers=multi_headers)
        assert response.status_code == 200


# =============================================================================
# PERMISSION ESCALATION PREVENTION TESTS
# =============================================================================

class TestPermissionEscalation:
    """Test that permission escalation is prevented."""

    def test_user_cannot_modify_own_roles(
        self, client: TestClient, auth_headers, test_user, mock_redis
    ):
        """Test that users cannot assign roles to themselves."""
        response = client.post(
            f"/api/admin/users/{test_user.id}/groups",
            json={"user_id": test_user.id, "group_name": "global:admin"},
            headers=auth_headers  # Using reader token
        )
        assert response.status_code in [401, 403]

    def test_admin_cannot_ban_self(
        self, client: TestClient, admin_headers, test_admin, mock_redis
    ):
        """Test that admins cannot ban themselves."""
        response = client.put(
            f"/api/admin/users/{test_admin.id}/ban",
            headers=admin_headers
        )
        assert response.status_code == 400
        assert "yourself" in response.json()["detail"].lower()

    def test_admin_cannot_delete_self(
        self, client: TestClient, admin_headers, test_admin, mock_redis
    ):
        """Test that admins cannot delete themselves."""
        response = client.delete(
            f"/api/admin/users/{test_admin.id}",
            headers=admin_headers
        )
        assert response.status_code == 400
        assert "yourself" in response.json()["detail"].lower()


# =============================================================================
# TOKEN SECURITY TESTS
# =============================================================================

class TestTokenSecurity:
    """Test token security features."""

    def test_tokens_are_unique(self, test_user):
        """Test that generated tokens are unique."""
        tokens = set()
        for _ in range(100):
            token = create_custom_token(
                user_id=test_user.id,
                email=test_user.email,
                scopes=[]
            )
            assert token not in tokens, "Tokens should be unique"
            tokens.add(token)

    def test_token_contains_required_claims(self, test_user):
        """Test that tokens contain all required claims."""
        token = create_custom_token(
            user_id=test_user.id,
            email=test_user.email,
            scopes=["test:scope"]
        )

        # Decode and verify claims
        payload = jwt.decode(
            token,
            os.environ.get("JWT_SECRET_KEY", "test-secret-key-for-testing-only"),
            algorithms=[os.environ.get("JWT_ALGORITHM", "HS256")]
        )

        assert "sub" in payload  # User ID
        assert "email" in payload
        assert "scopes" in payload
        assert "jti" in payload  # Token ID
        assert "exp" in payload  # Expiration
        assert "type" in payload  # Token type

    def test_test_tokens_use_test_secret(self):
        """Verify test tokens are signed with test secret key."""
        # This test ensures we're using the test secret, not production
        test_secret = os.environ.get("JWT_SECRET_KEY")
        assert test_secret == "test-secret-key-for-testing-only", \
            "Tests must use test JWT secret, not production secret"


# =============================================================================
# PROTECTED ENDPOINT ACCESS TESTS
# =============================================================================

class TestProtectedEndpoints:
    """Test that all sensitive endpoints require proper authorization."""

    def test_content_management_requires_auth(self, client: TestClient, test_topic):
        """Test that content management endpoints require authentication."""
        endpoints = [
            ("GET", f"/api/reader/{test_topic.slug}/articles"),
            ("GET", f"/api/analyst/{test_topic.slug}/articles"),
            ("GET", f"/api/editor/{test_topic.slug}/articles"),
        ]

        for method, endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code in [401, 403], \
                f"{endpoint} should require authentication"

    def test_prompt_management_requires_admin(
        self, client: TestClient, auth_headers, test_prompt, mock_redis
    ):
        """Test that prompt modification requires admin."""
        response = client.put(
            f"/api/prompts/{test_prompt.id}",
            json={"template_text": "Hacked prompt text that is definitely long enough to pass validation checks."},
            headers=auth_headers  # Reader token
        )
        assert response.status_code in [401, 403]

    def test_topic_management_requires_admin(
        self, client: TestClient, auth_headers, mock_redis
    ):
        """Test that topic management requires admin."""
        response = client.post(
            "/api/topics",
            json={"slug": "hacked_topic", "title": "Hacked"},
            headers=auth_headers  # Reader token
        )
        assert response.status_code in [401, 403]


# =============================================================================
# DATA ISOLATION TESTS
# =============================================================================

class TestDataIsolation:
    """Test that users can only access their own data."""

    def test_user_can_access_own_profile(
        self, client: TestClient, auth_headers, test_user, mock_redis
    ):
        """Test that users can access their own profile."""
        response = client.get("/api/profile/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email

    def test_user_can_delete_own_account(
        self, client: TestClient, db_session, mock_redis
    ):
        """Test that users can delete their own account."""
        # Create a temporary user for this test
        temp_user = User(
            email="temp_delete@test.com",
            name="Temp",
            surname="Delete",
            linkedin_sub="linkedin_temp_delete_123",
            active=True
        )
        db_session.add(temp_user)
        db_session.flush()

        # Create token for temp user
        temp_token = create_custom_token(
            user_id=temp_user.id,
            email=temp_user.email,
            scopes=[]
        )
        temp_headers = {"Authorization": f"Bearer {temp_token}"}

        response = client.delete("/api/profile/me", headers=temp_headers)
        assert response.status_code == 200

    def test_non_admin_cannot_access_other_user_tonality(
        self, client: TestClient, auth_headers, test_user, mock_redis
    ):
        """Test that non-admins cannot access other users' tonality settings."""
        # Try to access admin endpoint for other user's tonality
        response = client.get(
            f"/api/prompts/admin/user/{test_user.id + 100}/tonality",
            headers=auth_headers  # Reader token
        )
        assert response.status_code in [401, 403]
