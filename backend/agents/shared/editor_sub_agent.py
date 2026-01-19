"""
Editor Sub-Agent for human-in-the-loop publishing workflow.

This agent handles the editorial review and publishing workflow:
- Review articles in EDITOR status
- Request changes (return to DRAFT)
- Submit for human approval (HITL)
- Process approval callbacks
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from sqlalchemy.orm import Session

from agents.builds.v1.state import AgentState, UserContext
from services.permission_service import PermissionService


class EditorSubAgent:
    """
    Agent for editorial review and HITL publishing workflow.

    This agent manages the final stages of article publishing:
    1. Review article content and quality
    2. Request changes if needed
    3. Submit for human approval
    4. Process approval decisions
    """

    def __init__(
        self,
        llm: BaseChatModel,
        db: Session,
    ):
        """
        Initialize the EditorSubAgent.

        Args:
            llm: Language model for review assistance
            db: Database session
        """
        self.llm = llm
        self.db = db

    def review_article(
        self,
        article_id: int,
        user_context: UserContext,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Review an article and provide feedback.

        Args:
            article_id: ID of the article to review
            user_context: User context for permission checking
            conversation_history: Optional previous messages for context

        Returns:
            Dict with article details and AI-generated review
        """
        from models import ContentArticle, ArticleStatus
        from services.content_service import ContentService

        user_scopes = user_context.get("scopes", [])

        # Get article
        article = self.db.query(ContentArticle).filter(
            ContentArticle.id == article_id
        ).first()

        if not article:
            return {
                "success": False,
                "error": f"Article {article_id} not found",
            }

        topic = article.topic_slug

        # Check editor permission
        if not PermissionService.check_permission(user_scopes, "editor", topic=topic):
            return {
                "success": False,
                "error": f"Editor permission required for topic '{topic}'",
            }

        # Must be in EDITOR status
        if article.status != ArticleStatus.EDITOR:
            return {
                "success": False,
                "error": f"Article must be in EDITOR status, currently '{article.status.value}'",
            }

        # Get content
        from services.vector_service import VectorService
        content = VectorService.get_article_content(article_id)

        # Generate AI review
        review = self._generate_review(article.headline, content, conversation_history)

        return {
            "success": True,
            "article": {
                "id": article.id,
                "headline": article.headline,
                "topic": topic,
                "status": article.status.value,
                "author": article.author,
                "content_length": len(content) if content else 0,
            },
            "content_preview": content[:1000] if content else "",
            "ai_review": review,
        }

    def _generate_review(
        self,
        headline: str,
        content: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate an AI-powered review of the article.

        Args:
            headline: Article headline
            content: Article content
            conversation_history: Previous messages for context

        Returns:
            Dict with review findings
        """
        try:
            from langchain_core.messages import SystemMessage, HumanMessage

            # Build context from conversation history
            context_section = ""
            if conversation_history:
                context_parts = ["## Editor's Conversation Context\n"]
                for msg in conversation_history[-5:]:
                    role = msg.get("role", "user")
                    msg_content = msg.get("content", "")[:200]
                    context_parts.append(f"- **{role}**: {msg_content}")
                context_section = "\n".join(context_parts) + "\n\n"

            prompt = f"""{context_section}Review this financial research article for quality and accuracy.

Headline: {headline}

Content:
{content[:3000]}

Provide a structured review with:
1. Quality score (1-10)
2. Key strengths (2-3 points)
3. Areas for improvement (2-3 points)
4. Factual concerns (if any)
5. Recommendation (approve, request changes, or reject)

Be concise and professional."""

            response = self.llm.invoke([
                SystemMessage(content="You are a senior editor reviewing financial research articles."),
                HumanMessage(content=prompt),
            ])

            return {
                "generated": True,
                "review": response.content,
            }

        except Exception as e:
            return {
                "generated": False,
                "error": str(e),
            }

    def request_changes(
        self,
        article_id: int,
        user_context: UserContext,
        notes: str,
    ) -> Dict[str, Any]:
        """
        Request changes to an article (return to DRAFT).

        Args:
            article_id: ID of the article
            user_context: User context for permission checking
            notes: Editor notes explaining requested changes

        Returns:
            Dict with result
        """
        from models import ContentArticle, ArticleStatus

        user_scopes = user_context.get("scopes", [])

        article = self.db.query(ContentArticle).filter(
            ContentArticle.id == article_id
        ).first()

        if not article:
            return {
                "success": False,
                "error": f"Article {article_id} not found",
            }

        topic = article.topic_slug

        # Check editor permission
        if not PermissionService.check_permission(user_scopes, "editor", topic=topic):
            return {
                "success": False,
                "error": f"Editor permission required for topic '{topic}'",
            }

        # Must be in EDITOR or PENDING_APPROVAL status
        if article.status not in [ArticleStatus.EDITOR, ArticleStatus.PENDING_APPROVAL]:
            return {
                "success": False,
                "error": f"Cannot request changes for article in status '{article.status.value}'",
            }

        # Update status back to DRAFT
        article.status = ArticleStatus.DRAFT
        # Store editor notes (could be in a separate table for full audit trail)
        # For now, we'll update the article's editor field with notes
        user_name = f"{user_context.get('name', '')} {user_context.get('surname', '')}".strip()
        article.editor = f"{user_name}: {notes[:200]}"

        try:
            self.db.commit()
            return {
                "success": True,
                "article_id": article_id,
                "new_status": "draft",
                "message": "Article returned to draft for revisions",
                "notes": notes,
            }
        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "error": str(e),
            }

    def submit_for_approval(
        self,
        article_id: int,
        user_context: UserContext,
        editor_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Submit an article for human approval (HITL).

        This creates an ApprovalRequest and transitions the article to
        PENDING_APPROVAL status. The workflow pauses here until a human
        reviews and approves/rejects the request.

        Args:
            article_id: ID of the article to submit
            user_context: User context for permission checking
            editor_notes: Optional notes from the submitting editor

        Returns:
            Dict with approval request details and thread_id for resumption
        """
        from models import ContentArticle, ArticleStatus, ApprovalRequest, ApprovalStatus
        import uuid

        user_scopes = user_context.get("scopes", [])
        user_id = user_context.get("user_id")

        article = self.db.query(ContentArticle).filter(
            ContentArticle.id == article_id
        ).first()

        if not article:
            return {
                "success": False,
                "error": f"Article {article_id} not found",
            }

        topic = article.topic_slug

        # Check editor permission
        if not PermissionService.check_permission(user_scopes, "editor", topic=topic):
            return {
                "success": False,
                "error": f"Editor permission required for topic '{topic}'",
            }

        # Must be in EDITOR status
        if article.status != ArticleStatus.EDITOR:
            return {
                "success": False,
                "error": f"Article must be in EDITOR status, currently '{article.status.value}'",
            }

        try:
            # Create approval request
            thread_id = str(uuid.uuid4())
            expires_at = datetime.utcnow() + timedelta(hours=24)

            approval_request = ApprovalRequest(
                article_id=article_id,
                requested_by=user_id,
                editor_notes=editor_notes,
                status=ApprovalStatus.PENDING,
                expires_at=expires_at,
                thread_id=thread_id,
            )

            self.db.add(approval_request)

            # Update article status
            article.status = ArticleStatus.PENDING_APPROVAL

            self.db.commit()

            return {
                "success": True,
                "status": "awaiting_approval",
                "article_id": article_id,
                "approval_request_id": approval_request.id,
                "thread_id": thread_id,
                "expires_at": expires_at.isoformat(),
                "message": "Article submitted for approval. Awaiting human review.",
            }

        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "error": str(e),
            }

    def process_approval(
        self,
        article_id: int,
        approved: bool,
        user_context: UserContext,
        review_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process an approval decision.

        This is called when a human reviewer approves or rejects a
        publishing request.

        Args:
            article_id: ID of the article
            approved: Whether the article is approved
            user_context: User context of the reviewer
            review_notes: Optional notes from the reviewer

        Returns:
            Dict with result and new article status
        """
        from models import ContentArticle, ArticleStatus, ApprovalRequest, ApprovalStatus

        user_scopes = user_context.get("scopes", [])
        user_id = user_context.get("user_id")

        article = self.db.query(ContentArticle).filter(
            ContentArticle.id == article_id
        ).first()

        if not article:
            return {
                "success": False,
                "error": f"Article {article_id} not found",
            }

        topic = article.topic_slug

        # Check editor permission
        if not PermissionService.check_permission(user_scopes, "editor", topic=topic):
            return {
                "success": False,
                "error": f"Editor permission required for topic '{topic}'",
            }

        # Must be in PENDING_APPROVAL status
        if article.status != ArticleStatus.PENDING_APPROVAL:
            return {
                "success": False,
                "error": f"Article is not pending approval, status: '{article.status.value}'",
            }

        # Find the pending approval request
        approval_request = self.db.query(ApprovalRequest).filter(
            ApprovalRequest.article_id == article_id,
            ApprovalRequest.status == ApprovalStatus.PENDING,
        ).first()

        if not approval_request:
            return {
                "success": False,
                "error": "No pending approval request found",
            }

        try:
            # Update approval request
            approval_request.reviewed_by = user_id
            approval_request.reviewed_at = datetime.utcnow()
            approval_request.review_notes = review_notes
            approval_request.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED

            # Update article status
            if approved:
                article.status = ArticleStatus.PUBLISHED
                user_name = f"{user_context.get('name', '')} {user_context.get('surname', '')}".strip()
                article.editor = user_name or article.editor
                new_status = "published"
                message = "Article has been published."
            else:
                article.status = ArticleStatus.EDITOR
                new_status = "editor"
                message = "Article rejected. Returned to editor status."

            self.db.commit()

            return {
                "success": True,
                "article_id": article_id,
                "new_status": new_status,
                "approved": approved,
                "message": message,
                "review_notes": review_notes,
            }

        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "error": str(e),
            }

    def get_pending_approvals(
        self,
        user_context: UserContext,
        topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get list of pending approval requests.

        Args:
            user_context: User context for permission filtering
            topic: Optional topic filter

        Returns:
            Dict with list of pending approvals
        """
        from models import ApprovalRequest, ApprovalStatus, ContentArticle

        user_scopes = user_context.get("scopes", [])

        # Get accessible topics for this user (editor+)
        accessible_topics = PermissionService.get_accessible_topics(user_scopes, "editor")

        if not accessible_topics:
            return {
                "success": True,
                "pending_approvals": [],
                "message": "No topics accessible with editor permissions",
            }

        try:
            query = self.db.query(ApprovalRequest).join(ContentArticle).filter(
                ApprovalRequest.status == ApprovalStatus.PENDING,
            )

            # Filter by topic if specified
            if topic:
                if topic not in accessible_topics and "*" not in accessible_topics:
                    return {
                        "success": False,
                        "error": f"No editor permission for topic '{topic}'",
                    }
                query = query.filter(ContentArticle.topic == topic)
            elif "*" not in accessible_topics:
                # Filter to accessible topics
                query = query.filter(ContentArticle.topic.in_(accessible_topics))

            approvals = query.order_by(ApprovalRequest.requested_at.desc()).all()

            return {
                "success": True,
                "pending_approvals": [
                    {
                        "id": a.id,
                        "article_id": a.article_id,
                        "article_headline": a.article.headline if a.article else "Unknown",
                        "topic": a.article.topic_slug if a.article else None,
                        "requested_by": a.requester.name if a.requester else "Unknown",
                        "requested_at": a.requested_at.isoformat() if a.requested_at else None,
                        "expires_at": a.expires_at.isoformat() if a.expires_at else None,
                        "editor_notes": a.editor_notes,
                    }
                    for a in approvals
                ],
                "count": len(approvals),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def process(self, state: AgentState) -> AgentState:
        """
        Process agent state for LangGraph integration.

        Args:
            state: Current agent state

        Returns:
            Updated agent state
        """
        user_context = state.get("user_context")
        workflow_context = state.get("workflow_context")

        if not user_context:
            return {
                **state,
                "error": "User context required",
                "is_final": True,
            }

        # Get article_id from workflow context
        article_id = None
        if workflow_context:
            article_id = workflow_context.get("article_id")

        if not article_id:
            return {
                **state,
                "error": "Article ID required in workflow context",
                "is_final": True,
            }

        # Submit for approval
        result = self.submit_for_approval(
            article_id=article_id,
            user_context=user_context,
        )

        if result.get("success"):
            if result.get("status") == "awaiting_approval":
                response = f"""Article {article_id} submitted for approval.

**Approval Request ID:** {result.get('approval_request_id')}
**Thread ID:** {result.get('thread_id')}
**Expires:** {result.get('expires_at')}

The workflow is now paused awaiting human approval.
Use the /api/approvals endpoint to approve or reject."""

                return {
                    **state,
                    "messages": [AIMessage(content=response)],
                    "tool_results": {"editor_submit": result},
                    "last_tool_call": "submit_for_approval",
                    # Note: is_final is False because we're awaiting approval
                    # The LangGraph interrupt_before mechanism handles the pause
                }
            else:
                return {
                    **state,
                    "messages": [AIMessage(content=f"Article published: {result}")],
                    "is_final": True,
                }
        else:
            return {
                **state,
                "messages": [AIMessage(content=f"Submission failed: {result.get('error')}")],
                "error": result.get("error"),
                "is_final": True,
            }
