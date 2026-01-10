"""
Article Query Agent for searching and managing articles.

This agent handles article-related operations:
- Searching articles by topic and query
- Reading article content
- Creating draft articles (analyst+)
- Writing article content (analyst+)
- Submitting articles for review (analyst+)
"""

from typing import Dict, Any, Optional, List
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session

from agents.state import AgentState, UserContext, update_workflow_step
from services.permission_service import PermissionService


class ArticleQueryAgent:
    """
    Agent for article search and management operations.

    This agent provides read operations for all users and write operations
    for users with analyst+ permissions on the topic.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        db: Session,
        topic: Optional[str] = None,
    ):
        """
        Initialize the ArticleQueryAgent.

        Args:
            llm: Language model for generating responses
            db: Database session
            topic: Optional topic slug for topic-scoped operations
        """
        self.llm = llm
        self.db = db
        self.topic = topic

    def search_articles(
        self,
        query: str,
        user_context: UserContext,
        topic: Optional[str] = None,
        limit: int = 10,
        include_drafts: bool = False,
        ai_accessible_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Search for articles matching the query.

        Args:
            query: Search query string
            user_context: User context for permission checking
            topic: Topic slug to search within (uses self.topic if not provided)
            limit: Maximum number of results
            include_drafts: Whether to include draft articles (requires analyst+)
            ai_accessible_only: If True, only search topics with access_mainchat=True

        Returns:
            Dict with articles list and metadata
        """
        from services.content_service import ContentService

        search_topic = topic or self.topic
        user_scopes = user_context.get("scopes", [])

        # Filter by AI-accessible topics if requested
        allowed_topics = None
        if ai_accessible_only and not search_topic:
            from agents.topic_manager import get_ai_accessible_topic_slugs
            allowed_topics = get_ai_accessible_topic_slugs()
            if not allowed_topics:
                return {
                    "success": True,
                    "articles": [],
                    "total_count": 0,
                    "query": query,
                    "topic": None,
                }

        # Check if user can see drafts
        can_see_drafts = include_drafts and PermissionService.check_permission(
            user_scopes, "analyst", topic=search_topic
        )

        try:
            # Determine which statuses to include
            if can_see_drafts:
                # Analysts can see draft, editor, and published
                statuses = ["draft", "editor", "published"]
            else:
                # Regular users only see published articles
                statuses = ["published"]

            articles = ContentService.search_articles(
                db=self.db,
                topic=search_topic,
                query=query,
                limit=limit,
                statuses=statuses,
            )

            return {
                "success": True,
                "articles": [
                    {
                        "id": a.get("id"),
                        "headline": a.get("headline"),
                        "topic": a.get("topic"),
                        "status": a.get("status"),
                        "author": a.get("author"),
                        "created_at": a.get("created_at"),
                    }
                    for a in articles
                ],
                "total_count": len(articles),
                "query": query,
                "topic": search_topic,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "articles": [],
                "total_count": 0,
            }

    def get_article(
        self,
        article_id: int,
        user_context: UserContext,
    ) -> Dict[str, Any]:
        """
        Get a specific article by ID.

        Args:
            article_id: ID of the article to retrieve
            user_context: User context for permission checking

        Returns:
            Dict with article data
        """
        from services.content_service import ContentService
        from models import ArticleStatus

        try:
            article = ContentService.get_article(self.db, article_id)

            if not article:
                return {
                    "success": False,
                    "error": f"Article {article_id} not found",
                }

            # Check if user can view this article
            user_scopes = user_context.get("scopes", [])
            topic = article.get("topic")

            # Published articles are visible to all readers
            # Draft/Editor articles require analyst+ on the topic
            article_status = article.get("status", "draft")
            if article_status != "published":
                if not PermissionService.check_permission(user_scopes, "analyst", topic=topic):
                    return {
                        "success": False,
                        "error": "Permission denied: cannot view unpublished article",
                    }

            return {
                "success": True,
                "article": {
                    "id": article.get("id"),
                    "headline": article.get("headline"),
                    "topic": topic,
                    "status": article_status,
                    "author": article.get("author"),
                    "editor": article.get("editor"),
                    "content": article.get("content", ""),
                    "keywords": article.get("keywords"),
                    "created_at": article.get("created_at"),
                    "updated_at": article.get("updated_at"),
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def create_draft_article(
        self,
        headline: str,
        user_context: UserContext,
        topic: Optional[str] = None,
        keywords: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new draft article.

        Requires analyst+ permission on the topic.

        Args:
            headline: Article headline
            user_context: User context for permission and author tracking
            topic: Topic slug (uses self.topic if not provided)
            keywords: Optional keywords for the article

        Returns:
            Dict with created article data
        """
        from services.content_service import ContentService
        from models import ArticleStatus

        create_topic = topic or self.topic

        # Validate topic is provided
        if not create_topic:
            return {
                "success": False,
                "error": "Topic is required to create an article. Please specify a topic.",
            }

        user_scopes = user_context.get("scopes", [])

        # Check permission
        if not PermissionService.check_permission(user_scopes, "analyst", topic=create_topic):
            return {
                "success": False,
                "error": f"Permission denied: analyst+ required for topic '{create_topic}'",
            }

        try:
            # Get user info for author field
            user_name = user_context.get("name", "")
            user_surname = user_context.get("surname", "")
            author = f"{user_name} {user_surname}".strip() or "Unknown"

            article = ContentService.create_article(
                db=self.db,
                topic=create_topic,
                headline=headline,
                content="",  # Empty content initially
                keywords=keywords,
                agent_name="AnalystAgent",
                author=author,
                status="draft",
            )

            return {
                "success": True,
                "article_id": article.get("id"),
                "headline": article.get("headline"),
                "topic": create_topic,
                "status": "draft",
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def write_article_content(
        self,
        article_id: int,
        content: str,
        user_context: UserContext,
        resource_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Write or update article content.

        Requires analyst+ permission on the article's topic.

        Args:
            article_id: ID of the article to update
            content: Markdown content to write
            user_context: User context for permission checking
            resource_ids: Optional list of resource IDs to attach

        Returns:
            Dict with update result
        """
        from services.content_service import ContentService
        from models import ContentArticle, ArticleStatus

        user_scopes = user_context.get("scopes", [])

        try:
            # Get article to check topic and status
            article = self.db.query(ContentArticle).filter(
                ContentArticle.id == article_id
            ).first()

            if not article:
                return {
                    "success": False,
                    "error": f"Article {article_id} not found",
                }

            topic = article.topic_slug

            # Check permission
            if not PermissionService.check_permission(user_scopes, "analyst", topic=topic):
                return {
                    "success": False,
                    "error": f"Permission denied: analyst+ required for topic '{topic}'",
                }

            # Can only write to DRAFT articles
            if article.status not in [ArticleStatus.DRAFT, ArticleStatus.EDITOR]:
                return {
                    "success": False,
                    "error": f"Cannot modify article in status '{article.status.value}'",
                }

            # Update content
            ContentService.update_article(
                db=self.db,
                article_id=article_id,
                content=content,
            )

            # Attach resources if provided
            attached = []
            if resource_ids:
                from services.article_resource_service import ArticleResourceService
                resource_service = ArticleResourceService(self.db)
                for res_id in resource_ids:
                    try:
                        resource_service.attach_resource(article_id, res_id)
                        attached.append(res_id)
                    except Exception:
                        pass  # Skip resources that can't be attached

            return {
                "success": True,
                "article_id": article_id,
                "content_length": len(content),
                "attached_resources": attached,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def submit_for_review(
        self,
        article_id: int,
        user_context: UserContext,
    ) -> Dict[str, Any]:
        """
        Submit a draft article for editorial review.

        Changes article status from DRAFT to EDITOR.
        Requires analyst+ permission on the topic.

        Args:
            article_id: ID of the article to submit
            user_context: User context for permission checking

        Returns:
            Dict with submission result
        """
        from models import ContentArticle, ArticleStatus

        user_scopes = user_context.get("scopes", [])

        try:
            article = self.db.query(ContentArticle).filter(
                ContentArticle.id == article_id
            ).first()

            if not article:
                return {
                    "success": False,
                    "error": f"Article {article_id} not found",
                }

            topic = article.topic_slug

            # Check permission
            if not PermissionService.check_permission(user_scopes, "analyst", topic=topic):
                return {
                    "success": False,
                    "error": f"Permission denied: analyst+ required for topic '{topic}'",
                }

            # Must be in DRAFT status
            if article.status != ArticleStatus.DRAFT:
                return {
                    "success": False,
                    "error": f"Article must be in DRAFT status, currently '{article.status.value}'",
                }

            # Update status
            article.status = ArticleStatus.EDITOR
            self.db.commit()

            return {
                "success": True,
                "article_id": article_id,
                "new_status": "editor",
                "message": "Article submitted for editorial review",
            }

        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "error": str(e),
            }

    def process(self, state: AgentState) -> AgentState:
        """
        Process agent state for LangGraph integration.

        This method is called when the agent is used as a node in a LangGraph.

        Args:
            state: Current agent state

        Returns:
            Updated agent state with response
        """
        messages = state.get("messages", [])
        user_context = state.get("user_context")

        if not messages:
            return {
                **state,
                "error": "No messages to process",
            }

        # Get the last user message
        last_message = messages[-1]
        query = last_message.content if hasattr(last_message, 'content') else str(last_message)

        # Search for relevant articles
        result = self.search_articles(
            query=query,
            user_context=user_context,
            topic=self.topic,
        )

        if result.get("success") and result.get("articles"):
            articles = result["articles"]
            response = f"Found {len(articles)} relevant articles:\n\n"
            for article in articles[:5]:  # Limit to top 5
                response += f"- **{article['headline']}** (ID: {article['id']}, Status: {article['status']})\n"
        else:
            response = "No relevant articles found for your query."

        return {
            **state,
            "messages": [AIMessage(content=response)],
            "tool_results": {"article_search": result},
            "last_tool_call": "search_articles",
        }
