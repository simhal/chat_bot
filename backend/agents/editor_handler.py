"""Editor action handling for the main chat agent."""

from typing import Dict, Optional, Any
import logging
import re
import uuid

logger = logging.getLogger("uvicorn")


class EditorHandler:
    """Handles editor intents and actions for the main chat agent."""

    def __init__(self, llm, db, user_context: Optional[Dict[str, Any]] = None):
        """
        Initialize editor handler.

        Args:
            llm: ChatOpenAI LLM instance
            db: Database session
            user_context: User context for permissions
        """
        self.llm = llm
        self.db = db
        self.user_context = user_context
        self.navigation_context = None
        self._editor_agent = None

    def set_navigation_context(self, context: Optional[Dict[str, Any]]):
        """Set the current navigation context."""
        self.navigation_context = context

    def _get_editor_agent(self):
        """Get or create the EditorSubAgent."""
        if self._editor_agent is None:
            from agents.editor_sub_agent import EditorSubAgent
            self._editor_agent = EditorSubAgent(llm=self.llm, db=self.db)
            logger.info("✓ EditorSubAgent initialized")
        return self._editor_agent

    def detect_publish_confirmation(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect if user is confirming or cancelling a publish action.

        Matches messages like:
        - "Yes, publish article #54"
        - "Cancel publishing article #54"
        - "confirm publish"
        - "cancel publish"

        Returns:
            Dict with 'action' (confirm/cancel), 'article_id', or None
        """
        message_lower = message.lower()

        # Check for publish confirmation
        confirm_patterns = [
            r"yes,?\s*publish\s*(?:article\s*)?#?(\d+)",
            r"confirm\s*publish\s*(?:article\s*)?#?(\d+)",
            r"publish\s*(?:article\s*)?#?(\d+)\s*now",
            r"go\s*ahead\s*(?:and\s*)?publish\s*(?:article\s*)?#?(\d+)",
        ]

        for pattern in confirm_patterns:
            match = re.search(pattern, message_lower)
            if match:
                return {
                    "action": "confirm",
                    "article_id": int(match.group(1)),
                }

        # Also check for general confirmation without article ID (use context)
        if any(phrase in message_lower for phrase in [
            "yes, publish", "confirm publish", "yes publish", "go ahead and publish",
            "publish it now", "yes, do it", "proceed with publish"
        ]):
            nav_context = self.navigation_context or {}
            article_id = nav_context.get('article_id')
            if article_id:
                return {
                    "action": "confirm",
                    "article_id": article_id,
                }

        # Check for cancellation
        cancel_patterns = [
            r"cancel\s*(?:publishing\s*)?(?:article\s*)?#?(\d+)",
            r"don'?t\s*publish\s*(?:article\s*)?#?(\d+)",
            r"no,?\s*(?:don'?t\s*)?publish",
        ]

        for pattern in cancel_patterns:
            match = re.search(pattern, message_lower)
            if match:
                article_id = int(match.group(1)) if match.lastindex else None
                return {
                    "action": "cancel",
                    "article_id": article_id,
                }

        # General cancel phrases
        if any(phrase in message_lower for phrase in [
            "cancel publish", "cancel the publish", "don't publish", "no, cancel",
            "nevermind", "never mind", "abort publish"
        ]):
            return {
                "action": "cancel",
                "article_id": None,
            }

        return None

    def execute_publish_article(self, article_id: int) -> Dict[str, Any]:
        """
        Execute the actual publish action for an article.

        Calls the same logic as the /api/content/article/{id}/publish endpoint.

        Returns:
            Dict with success status and message
        """
        from models import ContentArticle, ArticleStatus
        from services.vector_service import VectorService
        from services.article_resource_service import ArticleResourceService

        try:
            # Get the article
            article = self.db.query(ContentArticle).filter(ContentArticle.id == article_id).first()

            if not article:
                return {
                    "success": False,
                    "message": f"Article #{article_id} not found.",
                }

            # Check article status
            if article.status != ArticleStatus.EDITOR:
                return {
                    "success": False,
                    "message": f"Article #{article_id} cannot be published. Current status is '{article.status.value}'. Only articles in 'editor' review can be published.",
                }

            # Check user has editor permission for this topic
            user_scopes = self.user_context.get("scopes", [])
            topic = article.topic_slug
            is_admin = "global:admin" in user_scopes
            has_editor_perm = f"{topic}:editor" in user_scopes or any(":editor" in s for s in user_scopes)

            if not is_admin and not has_editor_perm:
                return {
                    "success": False,
                    "message": f"You don't have editor permission to publish articles in the '{topic}' topic.",
                }

            # Publish the article
            editor_email = self.user_context.get("email", "")
            editor_name = f"{self.user_context.get('name', '')} {self.user_context.get('surname', '')}".strip()

            article.status = ArticleStatus.PUBLISHED
            if editor_name:
                article.editor = editor_name

            self.db.commit()

            # Create publication resources (HTML, PDF)
            user_id = self.user_context.get("user_id")
            resources_created = False

            try:
                content = VectorService.get_article_content(article_id)
                if content:
                    parent, html_res, pdf_res = ArticleResourceService.create_article_resources(
                        db=self.db,
                        article=article,
                        content=content,
                        editor_user_id=user_id
                    )
                    if parent:
                        resources_created = True
                        logger.info(f"Created publication resources for article {article_id}")
            except Exception as e:
                logger.warning(f"Could not create publication resources: {e}")

            return {
                "success": True,
                "message": f"Article #{article_id} has been published successfully!" + (" Publication resources (HTML/PDF) have been created." if resources_created else ""),
                "article_id": article_id,
                "headline": article.headline,
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error publishing article {article_id}: {e}")
            return {
                "success": False,
                "message": f"An error occurred while publishing: {str(e)}",
            }

    def detect_editor_intent(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect if the user wants to perform editor tasks (when role=editor).

        Args:
            message: User message

        Returns:
            Editor intent dict or None if no editor intent detected
        """
        nav_context = self.navigation_context or {}
        current_role = nav_context.get('role', 'reader')
        current_topic = nav_context.get('topic')
        article_id = nav_context.get('article_id')

        # Only trigger editor actions when role is editor
        if current_role != 'editor':
            return None

        message_lower = message.lower()

        # Review article
        if any(kw in message_lower for kw in [
            "review this article", "review article", "analyze this article",
            "check this article", "evaluate", "assess quality"
        ]):
            return {
                "action": "review",
                "article_id": article_id,
                "topic": current_topic,
            }

        # Request changes
        if any(kw in message_lower for kw in [
            "request changes", "send back", "needs revision", "needs work",
            "reject", "return to author", "revise"
        ]):
            return {
                "action": "request_changes",
                "article_id": article_id,
                "topic": current_topic,
                "notes": message,  # Use the message as notes
            }

        # Approve/Publish
        if any(kw in message_lower for kw in [
            "approve", "publish", "looks good", "approve and publish",
            "ready to publish", "publish article"
        ]):
            return {
                "action": "approve",
                "article_id": article_id,
                "topic": current_topic,
            }

        # List pending approvals
        if any(kw in message_lower for kw in [
            "pending approvals", "what needs approval", "articles to review",
            "show pending", "list pending", "what's waiting"
        ]):
            return {
                "action": "list_pending",
                "topic": current_topic,
            }

        return None

    def handle_editor_request(self, editor_intent: Dict[str, Any], user_message: str) -> Dict[str, Any]:
        """
        Handle editor-specific requests like reviewing and approving articles.

        Args:
            editor_intent: The detected editor intent
            user_message: Original user message

        Returns:
            Response dict with editor action results
        """
        action = editor_intent.get("action")
        article_id = editor_intent.get("article_id")
        topic = editor_intent.get("topic")

        # Check permissions
        if not self.user_context:
            return {
                "response": "I can't verify your permissions. Please ensure you're logged in.",
                "agent_type": "editor",
                "routing_reason": "No user context",
                "articles": [],
            }

        scopes = self.user_context.get("scopes", [])
        has_editor_permission = (
            "global:admin" in scopes or
            any(":editor" in s for s in scopes)
        )

        if not has_editor_permission:
            return {
                "response": "You need editor permissions to perform this action. Contact your administrator for access.",
                "agent_type": "editor",
                "routing_reason": "Missing editor permission",
                "articles": [],
            }

        editor_agent = self._get_editor_agent()

        try:
            if action == "review":
                if not article_id:
                    return {
                        "response": "Please navigate to a specific article to review it, or tell me which article ID you'd like to review.",
                        "agent_type": "editor",
                        "routing_reason": "No article specified for review",
                        "articles": [],
                    }

                result = editor_agent.review_article(article_id, self.user_context)

                if result.get("success"):
                    article_info = result.get("article", {})
                    ai_review = result.get("ai_review", {})
                    content_preview = result.get("content_preview", "")[:500]

                    response = f"""## Article Review: #{article_id}

**Headline:** {article_info.get('headline', 'N/A')}
**Topic:** {article_info.get('topic', 'N/A')}
**Status:** {article_info.get('status', 'N/A')}
**Author:** {article_info.get('author', 'N/A')}

### Content Preview
{content_preview}...

### AI Review
{ai_review.get('review', 'Review not available')}

Would you like to approve this article, request changes, or need more details?"""
                else:
                    response = f"Could not review article: {result.get('error', 'Unknown error')}"

            elif action == "request_changes":
                if not article_id:
                    return {
                        "response": "Please specify which article needs changes.",
                        "agent_type": "editor",
                        "routing_reason": "No article specified",
                        "articles": [],
                    }

                notes = editor_intent.get("notes", user_message)
                result = editor_agent.request_changes(article_id, self.user_context, notes)

                if result.get("success"):
                    response = f"Article #{article_id} has been returned to draft status with your feedback. The analyst will be notified to make revisions."
                else:
                    response = f"Could not request changes: {result.get('error', 'Unknown error')}"

            elif action == "approve":
                if not article_id:
                    return {
                        "response": "Please specify which article to approve.",
                        "agent_type": "editor",
                        "routing_reason": "No article specified",
                        "articles": [],
                    }

                # Return HITL button-based confirmation for publishing
                return {
                    "response": f"You're about to publish article #{article_id}. This will make it visible to all readers.",
                    "agent_type": "editor",
                    "routing_reason": "HITL confirmation for publish",
                    "articles": [],
                    "confirmation": {
                        "id": str(uuid.uuid4()),
                        "type": "publish_approval",
                        "title": "Confirm Publication",
                        "message": f"Article #{article_id} will be published and visible to all readers. This action can be reversed by recalling the article.",
                        "article_id": article_id,
                        "confirm_label": "Publish Now",
                        "cancel_label": "Cancel",
                        "confirm_endpoint": f"/api/content/article/{article_id}/publish",
                        "confirm_method": "POST",
                        "confirm_body": {},
                    },
                }

            elif action == "list_pending":
                result = editor_agent.get_pending_approvals(self.user_context, topic)

                if result.get("success"):
                    approvals = result.get("pending_approvals", [])
                    if approvals:
                        response = "## Pending Approvals\n\n"
                        for a in approvals:
                            response += f"- **Article #{a.get('article_id')}**: {a.get('article_headline', 'N/A')} ({a.get('topic', 'N/A')})\n"
                            if a.get('requested_by'):
                                response += f"  Requested by: {a.get('requested_by')}\n"
                        response += f"\nTotal: {len(approvals)} article(s) pending review."
                    else:
                        response = "No articles pending approval at this time."
                else:
                    response = f"Could not retrieve pending approvals: {result.get('error', 'Unknown error')}"

            else:
                response = f"I'm not sure how to handle that editor action. Try asking me to review an article, approve it, or request changes."

            return {
                "response": response,
                "agent_type": "editor",
                "routing_reason": f"Editor action: {action}",
                "articles": [],
            }

        except Exception as e:
            logger.error(f"✗ EDITOR REQUEST: Exception - {str(e)}")
            return {
                "response": f"An error occurred while processing your request: {str(e)}",
                "agent_type": "editor",
                "routing_reason": f"Editor error: {str(e)}",
                "articles": [],
            }
