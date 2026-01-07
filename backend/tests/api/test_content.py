"""
Content management endpoint tests.

Tests for:
- Reader endpoints (GET articles, search, rate, PDF)
- Analyst endpoints (create, edit, submit)
- Editor endpoints (review, reject, publish)
- Admin endpoints (manage, recall, purge)
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from models import ContentArticle, ArticleStatus


class TestReaderEndpoints:
    """Test reader-level content endpoints."""

    def test_get_articles_no_auth(self, client: TestClient):
        """Test GET /api/reader/{topic}/articles without auth."""
        response = client.get("/api/reader/macro/articles")
        assert response.status_code == 401  # HTTPBearer returns 401 for missing auth

    def test_get_articles_with_auth(
        self, client: TestClient, auth_headers, test_topic, published_article, mock_redis
    ):
        """Test GET /api/reader/{topic}/articles returns published articles."""
        response = client.get(
            f"/api/reader/{test_topic.slug}/articles",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Published article should be in the list
        if len(data) > 0:
            assert "headline" in data[0]

    def test_get_article_by_id(
        self, client: TestClient, auth_headers, test_topic, published_article, mock_redis
    ):
        """Test GET /api/reader/{topic}/article/{article_id} returns article."""
        response = client.get(
            f"/api/reader/{test_topic.slug}/article/{published_article.id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["headline"] == published_article.headline

    def test_get_article_not_found(
        self, client: TestClient, auth_headers, test_topic, mock_redis
    ):
        """Test GET /api/reader/{topic}/article/{article_id} for non-existent article."""
        response = client.get(f"/api/reader/{test_topic.slug}/article/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_rate_article(
        self, client: TestClient, auth_headers, test_topic, published_article, db_session, mock_redis
    ):
        """Test POST /api/reader/{topic}/article/{article_id}/rate."""
        response = client.post(
            f"/api/reader/{test_topic.slug}/article/{published_article.id}/rate",
            json={"rating": 5},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "rating" in data or "success" in str(data).lower()

    def test_rate_article_invalid_rating(
        self, client: TestClient, auth_headers, test_topic, published_article, mock_redis
    ):
        """Test POST /api/reader/{topic}/article/{article_id}/rate with invalid rating."""
        response = client.post(
            f"/api/reader/{test_topic.slug}/article/{published_article.id}/rate",
            json={"rating": 10},  # Invalid: should be 1-5
            headers=auth_headers
        )
        assert response.status_code in [400, 422]

    def test_search_articles(
        self, client: TestClient, auth_headers, test_topic, published_article, mock_redis
    ):
        """Test GET /api/reader/{topic}/search."""
        response = client.get(
            f"/api/reader/{test_topic.slug}/search",
            params={"query": "test"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_top_rated_articles(
        self, client: TestClient, auth_headers, test_topic, mock_redis
    ):
        """Test GET /api/reader/{topic}/articles/top-rated."""
        response = client.get(
            f"/api/reader/{test_topic.slug}/articles/top-rated",
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_get_most_read_articles(
        self, client: TestClient, auth_headers, test_topic, mock_redis
    ):
        """Test GET /api/reader/{topic}/articles/most-read."""
        response = client.get(
            f"/api/reader/{test_topic.slug}/articles/most-read",
            headers=auth_headers
        )
        assert response.status_code == 200


class TestAnalystEndpoints:
    """Test analyst-level content endpoints."""

    def test_create_article_no_permission(
        self, client: TestClient, auth_headers, test_topic, mock_redis, mock_chromadb
    ):
        """Test creating article without analyst permission."""
        response = client.post(
            f"/api/analyst/{test_topic.slug}/article",
            headers=auth_headers  # Reader token
        )
        # Should be forbidden for readers (403) - they don't have analyst permission
        assert response.status_code == 403

    def test_create_article_with_permission(
        self, client: TestClient, analyst_headers, test_topic, db_session, mock_redis, mock_chromadb
    ):
        """Test POST /api/analyst/{topic}/article with analyst permission."""
        response = client.post(
            f"/api/analyst/{test_topic.slug}/article",
            headers=analyst_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["status"] == "draft"

    def test_edit_article(
        self, client: TestClient, analyst_headers, test_topic, test_article, db_session, mock_redis, mock_chromadb
    ):
        """Test PUT /api/analyst/{topic}/article/{article_id}."""
        response = client.put(
            f"/api/analyst/{test_topic.slug}/article/{test_article.id}",
            json={
                "headline": "Updated Headline",
                "keywords": "updated, test"
            },
            headers=analyst_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["headline"] == "Updated Headline"

    def test_get_analyst_drafts(
        self, client: TestClient, analyst_headers, test_topic, test_article, mock_redis, mock_chromadb
    ):
        """Test GET /api/analyst/{topic}/articles."""
        response = client.get(
            f"/api/analyst/{test_topic.slug}/articles",
            headers=analyst_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_submit_article_for_review(
        self, client: TestClient, analyst_headers, test_topic, test_article, db_session, mock_redis, mock_chromadb
    ):
        """Test POST /api/analyst/{topic}/article/{article_id}/submit (submit for review)."""
        response = client.post(
            f"/api/analyst/{test_topic.slug}/article/{test_article.id}/submit",
            headers=analyst_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Response format: {"message": "...", "article": {...}}
        assert data["article"]["status"] == "editor"


class TestEditorEndpoints:
    """Test editor-level content endpoints."""

    def test_get_editor_queue(
        self, client: TestClient, editor_headers, test_topic, mock_redis, mock_chromadb
    ):
        """Test GET /api/editor/{topic}/articles."""
        response = client.get(
            f"/api/editor/{test_topic.slug}/articles",
            headers=editor_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_reject_article(
        self, client: TestClient, editor_headers, test_topic, test_article, db_session, mock_redis, mock_chromadb
    ):
        """Test POST /api/editor/{topic}/article/{article_id}/reject."""
        # First submit the article for review
        test_article.status = ArticleStatus.EDITOR
        db_session.commit()

        response = client.post(
            f"/api/editor/{test_topic.slug}/article/{test_article.id}/reject",
            json={"reason": "Needs more data"},
            headers=editor_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Response format: {"message": "...", "article": {...}}
        assert data["article"]["status"] == "draft"

    @pytest.mark.integration
    def test_publish_article(
        self, client: TestClient, editor_headers, test_topic, test_article, db_session, mock_redis, mock_chromadb
    ):
        """Test POST /api/editor/{topic}/article/{article_id}/publish."""
        # First submit the article for review
        test_article.status = ArticleStatus.EDITOR
        db_session.commit()

        with patch("services.agent_service.AgentService") as mock_agent:
            mock_instance = MagicMock()
            mock_instance.publish_article.return_value = {
                "status": "published",
                "article_id": test_article.id
            }
            mock_agent.return_value = mock_instance

            response = client.post(
                f"/api/editor/{test_topic.slug}/article/{test_article.id}/publish",
                headers=editor_headers
            )
            assert response.status_code == 200
            data = response.json()
            assert data["article"]["status"] == "published"


class TestAdminContentEndpoints:
    """Test admin content management endpoints."""

    def test_get_all_articles_no_admin(
        self, client: TestClient, auth_headers, test_topic, mock_redis
    ):
        """Test GET /api/admin/{topic}/articles without admin permission."""
        response = client.get(
            f"/api/admin/{test_topic.slug}/articles",
            headers=auth_headers  # Reader token
        )
        assert response.status_code in [403, 401]

    def test_get_all_articles_with_admin(
        self, client: TestClient, admin_headers, test_topic, mock_redis
    ):
        """Test GET /api/admin/{topic}/articles with admin permission."""
        response = client.get(
            f"/api/admin/{test_topic.slug}/articles",
            headers=admin_headers
        )
        assert response.status_code == 200

    def test_recall_published_article(
        self, client: TestClient, admin_headers, test_topic, published_article, db_session, mock_redis
    ):
        """Test POST /api/admin/{topic}/article/{article_id}/recall."""
        response = client.post(
            f"/api/admin/{test_topic.slug}/article/{published_article.id}/recall",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Response format is {"message": ..., "article": {...}}
        assert "article" in data or "message" in data
        if "article" in data:
            assert data["article"]["status"] == "draft"

    def test_deactivate_article(
        self, client: TestClient, admin_headers, test_topic, test_article, db_session, mock_redis
    ):
        """Test DELETE /api/admin/{topic}/article/{article_id} (soft delete)."""
        response = client.delete(
            f"/api/admin/{test_topic.slug}/article/{test_article.id}",
            headers=admin_headers
        )
        assert response.status_code == 200

    def test_reactivate_article(
        self, client: TestClient, admin_headers, test_topic, test_article, db_session, mock_redis
    ):
        """Test POST /api/admin/{topic}/article/{article_id}/reactivate."""
        # First deactivate
        test_article.is_active = False
        db_session.commit()

        response = client.post(
            f"/api/admin/{test_topic.slug}/article/{test_article.id}/reactivate",
            headers=admin_headers
        )
        assert response.status_code == 200

    @pytest.mark.integration
    def test_purge_article(
        self, client: TestClient, admin_headers, test_article, db_session, mock_redis, mock_chromadb
    ):
        """Test DELETE /api/admin/global/article/{article_id}/purge (permanent delete)."""
        article_id = test_article.id

        response = client.delete(
            f"/api/admin/global/article/{article_id}/purge",
            headers=admin_headers
        )
        assert response.status_code == 200

        # Verify article is actually deleted
        article = db_session.query(ContentArticle).filter(
            ContentArticle.id == article_id
        ).first()
        assert article is None

    def test_reorder_articles(
        self, client: TestClient, admin_headers, test_topic, test_article, published_article, db_session, mock_redis
    ):
        """Test POST /api/admin/global/articles/reorder."""
        response = client.post(
            "/api/admin/global/articles/reorder",
            json={
                "articles": [  # API expects "articles" with "id" and "priority"
                    {"id": test_article.id, "priority": 10},
                    {"id": published_article.id, "priority": 5}
                ]
            },
            headers=admin_headers
        )
        assert response.status_code == 200
