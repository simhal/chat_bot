"""
Main chat agent that uses existing articles and resources for responses.

This module is the main orchestrator for the chat agent. It delegates to specialized
handlers for different types of requests:

- NavigationHandler: Navigation intents and UI actions (agents/navigation_handler.py)
- EditorHandler: Editor actions like review, approve, publish (agents/editor_handler.py)
- ContentHandler: Content generation and routing (agents/content_handler.py)

The MainChatAgent class ties these together and handles:
- System prompt building
- User context and permissions
- Interface help queries
- General chat responses
"""

import os
import json
import logging
import re
import time
from typing import Dict, Optional, List, Any, TYPE_CHECKING

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from services.prompt_service import PromptService
from services.google_search_service import GoogleSearchService
from services.content_service import ContentService
from services.resource_service import ResourceService
from agents.state import (
    UserContext,
    NavigationContext,
    create_initial_state,
    create_navigation_context,
    create_user_context,
)

# Feature flag for using new LangGraph-based chat
USE_LANGGRAPH_CHAT = os.getenv("USE_LANGGRAPH_CHAT", "false").lower() == "true"

# Import from modular handlers
from agents.navigation_handler import (
    NavigationHandler,
    UI_ACTION_TYPES,
    ACTIONS_REQUIRING_CONFIRMATION,
)
from agents.editor_handler import EditorHandler
from agents.content_handler import ContentHandler

from pathlib import Path

if TYPE_CHECKING:
    from agents.resource_query_agent import ResourceQueryAgent

logger = logging.getLogger("uvicorn")

# Load frontend documentation for interface questions
_FRONTEND_DOCS_CACHE: Optional[str] = None

def _load_frontend_docs() -> str:
    """Load frontend documentation from docs/09-frontend.md."""
    global _FRONTEND_DOCS_CACHE
    if _FRONTEND_DOCS_CACHE is not None:
        return _FRONTEND_DOCS_CACHE

    # Try multiple paths to find the docs
    possible_paths = [
        Path("/app/docs/09-frontend.md"),  # Docker mount location
        Path(__file__).parent.parent.parent / "docs" / "09-frontend.md",  # Relative to backend/agents/
        Path("docs/09-frontend.md"),  # Current working directory
    ]

    docs_path = None
    for path in possible_paths:
        if path.exists():
            docs_path = path
            break

    if docs_path:
        _FRONTEND_DOCS_CACHE = docs_path.read_text(encoding="utf-8")
        logger.info(f"✓ Loaded frontend documentation from {docs_path} ({len(_FRONTEND_DOCS_CACHE)} chars)")
    else:
        _FRONTEND_DOCS_CACHE = ""
        logger.warning(f"⚠️ Frontend documentation not found. Tried: {[str(p) for p in possible_paths]}")

    return _FRONTEND_DOCS_CACHE


class MainChatAgent:
    """
    Main chat agent that:
    1. Has customizable prompt template (global + user-specific)
    2. Searches existing articles and resources to answer queries
    3. Includes article references with links in responses
    4. Uses ResourceQueryAgents for semantic search of resources
    5. Delegates to content agents (WebSearch, DataDownload) when appropriate
    6. Is user context aware (personalization, entitlements)
    """

    def __init__(
        self,
        user_id: int,
        llm: ChatOpenAI,
        google_search_service: GoogleSearchService,
        db: Session,
        resource_query_agents: Optional[List["ResourceQueryAgent"]] = None,
        user_context: Optional[UserContext] = None,
    ):
        """
        Initialize main chat agent.

        Args:
            user_id: User ID for personalized prompts
            llm: ChatOpenAI LLM instance
            google_search_service: Google Search service
            db: Database session
            resource_query_agents: Optional list of ResourceQueryAgents for querying resources
            user_context: Optional UserContext for personalization and entitlements
        """
        self.user_id = user_id
        self.llm = llm
        self.google_search = google_search_service
        self.db = db
        self.resource_query_agents = resource_query_agents or []
        self.user_context = user_context

        # Initialize content agents for delegation
        self._init_content_agents()

        # Log user context
        if user_context:
            logger.info(f"🧑 MainChatAgent initialized for user: {user_context.get('name', 'N/A')} ({user_context.get('email', 'N/A')})")
            logger.info(f"   Highest role: {user_context.get('highest_role', 'N/A')}")
            logger.info(f"   Topic roles: {user_context.get('topic_roles', {})}")
            logger.info(f"   Scopes: {user_context.get('scopes', [])}")
        else:
            logger.warning("⚠️ MainChatAgent initialized WITHOUT user_context")

        # Get personalized system prompt (enhanced with user context)
        self.system_prompt = self._build_system_prompt()

    def _init_content_agents(self):
        """Initialize content agents for delegation."""
        from agents.web_search_agent import WebSearchAgent
        from agents.data_download_agent import DataDownloadAgent

        self.web_search_agent = WebSearchAgent(llm=self.llm)
        self.data_download_agent = DataDownloadAgent(llm=self.llm, db=self.db)
        self.analyst_agents = {}  # Lazy-initialized per topic

        logger.info("✓ Content agents initialized (WebSearch, DataDownload)")

    def _get_analyst_agent(self, topic: str):
        """Get or create an AnalystAgent for a specific topic."""
        if topic not in self.analyst_agents:
            from agents.analyst_agent import AnalystAgent
            self.analyst_agents[topic] = AnalystAgent(
                topic=topic,
                llm=self.llm,
                db=self.db
            )
            logger.info(f"✓ AnalystAgent initialized for topic: {topic}")
        return self.analyst_agents[topic]

    def _get_editor_agent(self):
        """Get or create the EditorSubAgent."""
        if not hasattr(self, '_editor_agent') or self._editor_agent is None:
            from agents.editor_sub_agent import EditorSubAgent
            self._editor_agent = EditorSubAgent(llm=self.llm, db=self.db)
            logger.info("✓ EditorSubAgent initialized")
        return self._editor_agent

    def _detect_publish_confirmation(self, message: str) -> Optional[Dict[str, Any]]:
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
        import re

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
            nav_context = getattr(self, 'navigation_context', None) or {}
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

    def _execute_publish_article(self, article_id: int) -> Dict[str, Any]:
        """
        Execute the actual publish action for an article.

        Calls the same logic as the /api/content/article/{id}/publish endpoint.

        Returns:
            Dict with success status and message
        """
        from models import ContentArticle, ArticleStatus
        from services.content import ContentService
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

    def _extract_article_id_from_message(self, message: str) -> Optional[int]:
        """Extract article ID from message like 'article #54' or 'article 54'."""
        import re
        patterns = [
            r"article\s*#?(\d+)",
            r"#(\d+)",
            r"id\s*:?\s*(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                return int(match.group(1))
        return None

    def _detect_editor_intent(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect if the user wants to perform editor tasks.
        Works from ANY page - will navigate to editor hub if needed.

        Args:
            message: User message

        Returns:
            Editor intent dict or None if no editor intent detected
        """
        nav_context = getattr(self, 'navigation_context', None) or {}
        current_section = nav_context.get('section', 'home')
        current_role = nav_context.get('role', 'reader')
        current_topic = nav_context.get('topic')
        article_id = nav_context.get('article_id')

        message_lower = message.lower()

        # Try to extract article ID from message if not in context
        message_article_id = self._extract_article_id_from_message(message)
        if message_article_id:
            article_id = message_article_id

        # Determine if navigation is needed
        needs_navigation = current_section != 'editor'

        # Publish / approve article (works from any page)
        if any(kw in message_lower for kw in [
            "publish article", "approve article", "publish #", "approve #",
            "publish this article", "approve this article"
        ]):
            if article_id:
                return {
                    "action": "approve",
                    "article_id": article_id,
                    "topic": current_topic,
                    "needs_navigation": needs_navigation,
                    "current_section": current_section,
                }

        # Review article (works from any page)
        if any(kw in message_lower for kw in [
            "review article", "review #", "check article",
            "evaluate article", "assess article"
        ]):
            if article_id:
                return {
                    "action": "review",
                    "article_id": article_id,
                    "topic": current_topic,
                    "needs_navigation": needs_navigation,
                    "current_section": current_section,
                }

        # Reject / request changes (works from any page)
        if any(kw in message_lower for kw in [
            "reject article", "reject #", "send back article",
            "request changes for article", "return article"
        ]):
            if article_id:
                return {
                    "action": "request_changes",
                    "article_id": article_id,
                    "topic": current_topic,
                    "notes": message,
                    "needs_navigation": needs_navigation,
                    "current_section": current_section,
                }

        # List pending approvals (works from any page)
        if any(kw in message_lower for kw in [
            "pending articles", "pending approvals", "what's pending",
            "show pending", "articles to review", "review queue",
            "what needs review", "articles waiting"
        ]):
            return {
                "action": "list_pending",
                "topic": current_topic,
                "needs_navigation": needs_navigation,
                "current_section": current_section,
            }

        # Context-specific actions only when already in editor section
        if current_role == 'editor' and current_section == 'editor':
            # Review current article
            if any(kw in message_lower for kw in [
                "review this", "check this", "evaluate this", "assess this"
            ]):
                return {
                    "action": "review",
                    "article_id": article_id,
                    "topic": current_topic,
                    "needs_navigation": False,
                    "current_section": current_section,
                }

            # Approve/publish current article
            if any(kw in message_lower for kw in [
                "approve", "publish", "looks good", "accept"
            ]):
                return {
                    "action": "approve",
                    "article_id": article_id,
                    "topic": current_topic,
                    "needs_navigation": False,
                    "current_section": current_section,
                }

            # Reject current article
            if any(kw in message_lower for kw in [
                "reject", "send back", "needs changes", "request changes"
            ]):
                return {
                    "action": "request_changes",
                    "article_id": article_id,
                    "topic": current_topic,
                    "notes": message,
                    "needs_navigation": False,
                    "current_section": current_section,
                }

        return None

    def _handle_editor_request(self, editor_intent: Dict[str, Any], user_message: str) -> Dict[str, Any]:
        """
        Handle editor requests by delegating to EditorSubAgent.
        Will navigate to editor hub first if not already there.

        Args:
            editor_intent: Editor intent from _detect_editor_intent
            user_message: Original user message

        Returns:
            Response dict with editor action result
        """
        action = editor_intent.get("action")
        article_id = editor_intent.get("article_id")
        topic = editor_intent.get("topic")
        needs_navigation = editor_intent.get("needs_navigation", False)
        current_section = editor_intent.get("current_section", "home")

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
                        "response": "Please specify which article to approve (e.g., 'publish article #54').",
                        "agent_type": "editor",
                        "routing_reason": "No article specified",
                        "articles": [],
                    }

                # Get article info to determine topic for navigation
                from models import ContentArticle
                article = self.db.query(ContentArticle).filter(ContentArticle.id == article_id).first()
                article_topic = article.topic_slug if article else topic

                # Build navigation if needed
                navigation = None
                nav_msg = ""
                if needs_navigation and article_topic:
                    navigation = {
                        "action": "navigate",
                        "target": f"/editor/{article_topic}",
                        "params": {"topic": article_topic, "article_id": article_id},
                    }
                    nav_msg = f"\n\n**Navigating to the Editor Hub...**"
                    logger.info(f"📍 Including navigation to /editor/{article_topic}")

                # Return HITL button-based confirmation for publishing
                import uuid
                result = {
                    "response": f"You're about to publish article #{article_id}. This will make it visible to all readers.{nav_msg}",
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
                if navigation:
                    result["navigation"] = navigation
                return result

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

            # Build navigation for non-approve actions if needed
            navigation = None
            if needs_navigation and action in ["review", "list_pending", "request_changes"]:
                # Navigate to editor hub
                nav_topic = topic or "macro"  # Default topic if none specified
                navigation = {
                    "action": "navigate",
                    "target": f"/editor/{nav_topic}",
                    "params": {"topic": nav_topic},
                }
                response += f"\n\n**Navigating to the Editor Hub...**"
                logger.info(f"📍 Including navigation to /editor/{nav_topic}")

            result_dict = {
                "response": response,
                "agent_type": "editor",
                "routing_reason": f"Editor action: {action}",
                "articles": [],
            }
            if navigation:
                result_dict["navigation"] = navigation
            return result_dict

        except Exception as e:
            logger.error(f"✗ EDITOR REQUEST: Exception - {str(e)}")
            return {
                "response": f"An error occurred while processing your request: {str(e)}",
                "agent_type": "editor",
                "routing_reason": f"Editor error: {str(e)}",
                "articles": [],
            }

    def _detect_content_generation_intent(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect if the user wants to generate article content.
        Works from ANY page - will navigate to analyst editor if needed.

        Args:
            message: User message

        Returns:
            Content generation intent dict or None if no generation intent detected
        """
        nav_context = getattr(self, 'navigation_context', None) or {}
        current_section = nav_context.get('section', 'home')
        current_role = nav_context.get('role', 'reader')
        article_id = nav_context.get('article_id')
        topic = nav_context.get('topic')

        logger.info(f"📝 Content generation check: section={current_section}, role={current_role}, article_id={article_id}, topic={topic}")

        message_lower = message.lower()

        # Content generation keywords - detect from ANY page
        generation_keywords = [
            "write an article", "generate article", "create article content",
            "write content", "generate content", "draft an article",
            "write about", "generate analysis", "create analysis",
            "research and write", "write research", "produce article",
            "fill in the article", "fill the article", "fill the editor", "write this article",
            "fill article", "please fill", "generate for me", "write for me",
            "rewrite", "rewrite this", "rewrite the article", "rewrite article",
            "regenerate", "redo this", "redo the article",
            # Additional patterns for requests from main chat
            "write a market", "write an analysis", "write a report",
            "create a market", "create an analysis", "create a report",
            "draft a market", "draft an analysis", "draft a report",
            "write me an article", "write me a report", "write me an analysis",
            "please write an", "please create an", "please draft an",
            "can you write", "could you write", "would you write",
            # More flexible patterns
            "write an overview", "create an overview", "draft an overview",
            "write a overview", "create a overview", "draft a overview",
            "write an economic", "write a economic", "write economic",
            "write an equity", "write a equity", "write equity",
            "write a macro", "write macro", "write an macro",
            "write a bond", "write bond", "write an bond",
            "create an economic", "create economic", "create macro",
            "produce an article", "produce article", "produce a article",
            # Article creation patterns
            "make an article", "make a article", "make article",
            "prepare an article", "prepare a article", "prepare article",
            "compose an article", "compose a article", "compose article",
        ]

        # Check for keyword match
        matched_keyword = next((kw for kw in generation_keywords if kw in message_lower), None)

        # Also check for pattern: "write/create/generate" + any topic-related content word
        if not matched_keyword:
            content_pattern = re.compile(
                r'(write|create|generate|draft|produce|compose|prepare)\s+'
                r'(me\s+)?(an?\s+)?'
                r'(article|report|analysis|overview|market\s+overview|research|piece|content|write-up)'
                r'(\s+about|\s+on|\s+for|\s+regarding)?',
                re.IGNORECASE
            )
            if content_pattern.search(message_lower):
                matched_keyword = "pattern: content creation request"
                logger.info(f"✅ Content generation pattern matched via regex")

        if matched_keyword:
            logger.info(f"✅ Content generation keyword matched: '{matched_keyword}'")

            # Determine if we need to navigate to analyst editor
            needs_navigation = current_section != 'analyst'

            return {
                "topic": topic,
                "article_id": article_id,
                "query": message,
                "needs_navigation": needs_navigation,
                "current_section": current_section,
            }

        # Also check for more specific requests when editing an article
        if article_id and current_section == 'analyst':
            # User might ask to generate content for their current article
            article_specific_keywords = [
                "generate this", "write this", "fill this", "draft this",
                "complete this article", "help me write"
            ]
            if any(kw in message_lower for kw in article_specific_keywords):
                return {
                    "topic": topic,
                    "article_id": article_id,
                    "query": message,
                    "needs_navigation": False,
                    "current_section": current_section,
                }

        return None

    def _infer_topic_from_message(self, message: str) -> Optional[str]:
        """
        Infer topic from the user message.

        Args:
            message: User message

        Returns:
            Topic slug or None if no topic detected
        """
        message_lower = message.lower()

        # Get available topics from database
        topics = self._get_available_topics()

        # Direct topic mention patterns
        for topic in topics:
            topic_display = topic.replace("_", " ")
            # Check for patterns like "for the equity topic", "about equity", "on macro", etc.
            patterns = [
                f"for {topic_display}",
                f"for the {topic_display}",
                f"about {topic_display}",
                f"on {topic_display}",
                f"{topic_display} topic",
                f"{topic_display} article",
                f"{topic_display} analysis",
                f"{topic_display} report",
                f"in {topic_display}",
            ]
            if any(p in message_lower for p in patterns):
                logger.info(f"📝 Inferred topic from message: {topic}")
                return topic

        # Content-based topic inference
        topic_keywords = {
            "macro": ["economy", "economic", "gdp", "inflation", "unemployment", "central bank",
                     "fed", "ecb", "monetary policy", "interest rate", "fiscal", "recession",
                     "czech republic", "poland", "hungary", "europe", "eurozone", "country", "countries",
                     "employment", "jobs", "trade", "exports", "imports", "currency", "exchange rate"],
            "equity": ["stock", "stocks", "shares", "equity", "equities", "company", "companies",
                      "earnings", "pe ratio", "market cap", "ipo", "nasdaq", "s&p", "dow",
                      "sector", "industry", "healthcare", "technology", "tech", "financial",
                      "energy", "consumer", "industrial", "materials", "utilities", "telecom"],
            "fixed_income": ["bond", "bonds", "yield", "yields", "treasury", "treasuries",
                            "credit", "debt", "fixed income", "spread", "spreads",
                            "coupon", "maturity", "duration", "sovereign", "corporate bond"],
            "esg": ["esg", "sustainability", "sustainable", "climate", "environmental",
                   "governance", "social", "green", "carbon", "renewable",
                   "emission", "emissions", "net zero", "diversity", "inclusion"],
            "technical": ["technical", "chart", "charts", "pattern", "momentum", "rsi",
                         "moving average", "support", "resistance", "trend",
                         "fibonacci", "bollinger", "macd", "volume"],
        }

        for topic, keywords in topic_keywords.items():
            if topic in topics and any(kw in message_lower for kw in keywords):
                logger.info(f"📝 Inferred topic from content keywords: {topic}")
                return topic

        return None

    def _handle_content_generation(self, gen_intent: Dict[str, Any], user_message: str) -> Dict[str, Any]:
        """
        Handle content generation request by delegating to AnalystAgent.
        Returns editor_content to fill the editor UI (not chat).

        Can work from ANY page:
        - If not in analyst editor, will navigate there first
        - If no article exists, will create one
        - If no topic specified, will infer from message or ask user

        Args:
            gen_intent: Content generation intent from _detect_content_generation_intent
            user_message: Original user message

        Returns:
            Response dict with editor_content for the frontend to fill editor fields
        """
        topic = gen_intent.get("topic")
        article_id = gen_intent.get("article_id")
        needs_navigation = gen_intent.get("needs_navigation", False)
        current_section = gen_intent.get("current_section", "home")

        # Try to infer topic from message if not set
        if not topic:
            topic = self._infer_topic_from_message(user_message)
            logger.info(f"📝 Topic inference result: {topic}")

        if not topic:
            return {
                "response": "I need to know which topic you want to write about. Please navigate to a specific topic's analyst hub first.",
                "agent_type": "content_generation",
                "routing_reason": "No topic specified for content generation",
                "articles": [],
                "editor_content": None,
            }

        # Check permissions
        if not self.user_context:
            return {
                "response": "I can't verify your permissions. Please ensure you're logged in.",
                "agent_type": "content_generation",
                "routing_reason": "No user context",
                "articles": [],
                "editor_content": None,
            }

        scopes = self.user_context.get("scopes", [])
        required_scope = f"{topic}:analyst"

        # Check if user has analyst permission for this topic
        has_permission = (
            "global:admin" in scopes or
            required_scope in scopes or
            any(scope.endswith(":analyst") for scope in scopes)
        )

        if not has_permission:
            topic_display = topic.replace("_", " ").title()
            return {
                "response": f"You need analyst access for {topic_display} to generate article content. Contact your administrator for access.",
                "agent_type": "content_generation",
                "routing_reason": f"Missing permission: {required_scope}",
                "articles": [],
                "editor_content": None,
            }

        topic_display = topic.replace("_", " ").title()

        # If no article exists and we're not already in the analyst editor, create one
        if not article_id and needs_navigation:
            logger.info(f"📝 CONTENT GENERATION: Creating new article for topic '{topic}'")
            try:
                from models import ContentArticle, ArticleStatus
                from datetime import datetime

                # Get author info from user context
                author_name = f"{self.user_context.get('name', '')} {self.user_context.get('surname', '')}".strip()
                if not author_name:
                    author_name = self.user_context.get('email', 'Unknown')

                # Create empty article that will be filled with generated content
                new_article = ContentArticle(
                    topic_slug=topic,
                    headline="",  # Will be filled by generated content
                    status=ArticleStatus.DRAFT,
                    author=author_name,
                    analyst=self.user_context.get('user_id'),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                self.db.add(new_article)
                self.db.commit()
                article_id = new_article.id
                logger.info(f"✓ Created new article #{article_id} for topic '{topic}'")
            except Exception as e:
                logger.error(f"✗ Failed to create article: {e}")
                self.db.rollback()
                return {
                    "response": f"I couldn't create a new article for {topic_display}: {str(e)}",
                    "agent_type": "content_generation",
                    "routing_reason": f"Article creation failed: {str(e)}",
                    "articles": [],
                    "editor_content": None,
                }

        # Delegate to AnalystAgent
        logger.info(f"📝 CONTENT GENERATION: Delegating to AnalystAgent for topic '{topic}', article_id={article_id}")

        try:
            analyst_agent = self._get_analyst_agent(topic)

            # Call the research_and_write method
            result = analyst_agent.research_and_write(
                query=user_message,
                user_context=self.user_context,
                article_id=article_id,
            )

            if result.get("success"):
                # Get linked resources from the result
                linked_resources = result.get("linked_resources", [])

                # Get content for headline/keywords generation
                content = result.get("content", "")

                # Generate headline if not provided (e.g., when rewriting existing article)
                headline = result.get("headline")
                if not headline and content:
                    logger.info("   Generating headline from content...")
                    headline = self._generate_headline_from_content(content, topic)

                # Generate keywords from content
                logger.info("   Generating keywords from content...")
                keywords = self._generate_keywords_from_content(content, topic) if content else topic

                # Return editor_content to fill the editor UI
                editor_content = {
                    "headline": headline,
                    "content": content,
                    "keywords": keywords,
                    "action": "fill" if not article_id else "replace",
                    "linked_resources": linked_resources,
                    "article_id": article_id or result.get("article_id"),
                }

                # Friendly response for chat (content goes to editor, not chat)
                sources = result.get("sources", {})
                linked_count = len([r for r in linked_resources if not r.get("already_linked")])
                already_linked_count = len([r for r in linked_resources if r.get("already_linked")])

                resources_msg = ""
                if linked_count > 0:
                    resources_msg = f"\n\n**Resources linked:** {linked_count} new resource(s) attached to article"
                    if already_linked_count > 0:
                        resources_msg += f" ({already_linked_count} already linked)"

                # Build navigation command if we need to go to the editor
                navigation = None
                if needs_navigation and article_id:
                    navigation = {
                        "action": "navigate",
                        "target": f"/analyst/edit/{article_id}",
                        "params": {"topic": topic, "article_id": article_id},
                    }
                    logger.info(f"📍 Including navigation to /analyst/edit/{article_id}")

                # Build response message
                nav_msg = ""
                if needs_navigation:
                    nav_msg = f"\n\n**Navigating to the {topic_display} article editor...**"

                response = f"""I've generated the article content for you based on your request.

**Topic:** {topic_display}
**Sources used:**
- Existing research: {sources.get('existing_articles', 0)} articles
- Resources: {sources.get('resources', 0)} documents
- Web search: {sources.get('web_results', 0)} news items
- Market data: {sources.get('data_sources', 0)} data points{resources_msg}{nav_msg}

The content has been filled into the editor fields. Please review and make any adjustments before saving."""

                logger.info(f"✓ CONTENT GENERATION: Successfully generated content for topic '{topic}', {linked_count} resources linked")
                logger.info(f"   Editor content: headline={editor_content.get('headline', '')[:50] if editor_content.get('headline') else 'None'}, content_len={len(editor_content.get('content', '') or '')}")

                result_dict = {
                    "response": response,
                    "agent_type": "content_generation",
                    "routing_reason": f"Content generated for {topic}",
                    "articles": [],
                    "editor_content": editor_content,
                }

                # Add navigation if needed
                if navigation:
                    result_dict["navigation"] = navigation

                return result_dict
            else:
                error = result.get("error", "Unknown error")
                logger.error(f"✗ CONTENT GENERATION: Failed - {error}")

                return {
                    "response": f"I encountered an issue generating the content: {error}\n\nPlease try again or provide more specific instructions.",
                    "agent_type": "content_generation",
                    "routing_reason": f"Content generation failed: {error}",
                    "articles": [],
                    "editor_content": None,
                }

        except Exception as e:
            logger.error(f"✗ CONTENT GENERATION: Exception - {str(e)}")
            return {
                "response": f"An error occurred while generating content: {str(e)}\n\nPlease try again.",
                "agent_type": "content_generation",
                "routing_reason": f"Content generation error: {str(e)}",
                "articles": [],
                "editor_content": None,
            }

    def _build_system_prompt(self) -> str:
        """
        Build personalized system prompt with user context.

        Returns:
            System prompt string with user personalization and entitlements info
        """
        # Get base prompt from PromptService
        base_prompt = PromptService.get_main_chat_template(self.user_id)

        # If no user context, return base prompt
        if not self.user_context:
            return base_prompt

        # Build user personalization section
        user_name = self.user_context.get("name", "")
        user_surname = self.user_context.get("surname", "")
        full_name = f"{user_name} {user_surname}".strip() if user_surname else user_name

        # Build entitlements description
        entitlements_desc = self._format_entitlements()

        # Add user context to prompt
        user_context_section = f"""
## Current User Context
- **User**: {full_name or 'Anonymous'}
- **Email**: {self.user_context.get('email', 'N/A')}
- **Highest Role**: {self.user_context.get('highest_role', 'reader')}

## User Entitlements
{entitlements_desc}

When greeting the user or in personalized responses, address them by their first name: {user_name or 'there'}.

If the user asks about their permissions, roles, or what they can do, provide them with their entitlements information from above.
"""

        # Add custom tonality if available
        tonality = self.user_context.get("chat_tonality_text", "")
        if tonality:
            user_context_section += f"\n## Response Tonality\n{tonality}\n"

        # Add navigation context if available
        nav_context = getattr(self, 'navigation_context', None)
        if nav_context:
            section = nav_context.get('section', 'home')
            topic = nav_context.get('topic')
            article_id = nav_context.get('article_id')
            article_headline = nav_context.get('article_headline')
            article_keywords = nav_context.get('article_keywords')
            sub_nav = nav_context.get('sub_nav')
            current_role = nav_context.get('role', 'reader')

            # Build navigation description
            nav_desc_parts = []
            section_labels = {
                'home': 'Home/Articles',
                'search': 'Article Search',
                'analyst': 'Analyst Hub',
                'editor': 'Editor Hub',
                'admin': 'Admin Panel',
                'profile': 'User Profile'
            }
            role_labels = {
                'reader': 'Reader (browsing content)',
                'analyst': 'Analyst (creating/editing articles)',
                'editor': 'Editor (reviewing/publishing articles)',
                'admin': 'Administrator (system management)'
            }
            nav_desc_parts.append(f"**Current Role**: {role_labels.get(current_role, current_role.title())}")
            nav_desc_parts.append(f"**Section**: {section_labels.get(section, section.title())}")

            if topic:
                topic_formatted = topic.replace('_', ' ').title()
                nav_desc_parts.append(f"**Topic**: {topic_formatted}")

            if article_id:
                nav_desc_parts.append(f"**Article ID**: #{article_id}")
                if article_headline:
                    nav_desc_parts.append(f"**Article Headline**: {article_headline}")
                if article_keywords:
                    nav_desc_parts.append(f"**Article Keywords**: {article_keywords}")

            if sub_nav:
                nav_desc_parts.append(f"**View**: {sub_nav.replace('_', ' ').title()}")

            # Build section-specific guidance based on role
            section_guidance = self._get_section_guidance(section, topic, article_id, sub_nav, current_role, article_headline, article_keywords)

            user_context_section += f"""
## Current Navigation Context
The user is currently viewing:
{chr(10).join('- ' + p for p in nav_desc_parts)}

{section_guidance}

## Navigation Commands
You can help the user navigate to different parts of the application by recognizing their intent.
When the user wants to go somewhere, acknowledge their request and the system will navigate them.
Examples of navigation requests you should recognize:
- "logout" / "sign out" - Log the user out
- "go to admin" / "admin panel" - Navigate to admin (requires admin access)
- "write a macro article" / "create equity article" - Navigate to analyst hub (requires analyst access)
- "review articles" / "editor hub" - Navigate to editor hub (requires editor access)
- "show fixed income articles" - Navigate to topic view
- "my profile" / "settings" - Navigate to profile
- "search articles" - Navigate to search

Always check the user's entitlements before suggesting they navigate to protected areas.
If they don't have access, explain what permissions they would need.
"""

        return base_prompt + "\n" + user_context_section

    def _get_section_guidance(self, section: str, topic: Optional[str], article_id: Optional[int], sub_nav: Optional[str], current_role: str = 'reader', article_headline: Optional[str] = None, article_keywords: Optional[str] = None) -> str:
        """
        Get section-specific guidance for the chatbot based on current navigation and role.

        Args:
            section: Current section (home, analyst, editor, admin, profile, search)
            topic: Current topic if any
            article_id: Current article ID if viewing/editing an article
            sub_nav: Sub-navigation state
            current_role: Current user role based on navigation (reader, analyst, editor, admin)
            article_headline: Current article headline if editing
            article_keywords: Current article keywords if editing

        Returns:
            Section-specific guidance string
        """
        topic_display = topic.replace('_', ' ').title() if topic else "selected topic"

        if section == 'analyst':
            if article_id:
                article_info = ""
                if article_headline:
                    article_info += f"\n**Current Headline:** {article_headline}"
                if article_keywords:
                    article_info += f"\n**Current Keywords:** {article_keywords}"

                return f"""### Analyst Context: Editing Article #{article_id}
You are helping an analyst edit article #{article_id} on {topic_display}.{article_info}

- You have full context of the article being edited (ID, headline, keywords shown above)
- Offer help with improving the content, headline, or keywords
- Suggest research sources or data points to add
- Help with formatting and structure
- Explain how to save changes or submit for review
- You can help them navigate to other articles or the analyst hub
- **IMPORTANT**: When asked to generate, rewrite, or write article content, use the content generation tools.
  The generated content will automatically populate the editor fields (headline, content, keywords).
  Do NOT output the full article in the chat - just acknowledge that you're generating it."""
            else:
                return f"""### Analyst Context: {topic_display} Hub
You are helping an analyst in the {topic_display} analyst hub.
- Help them understand their draft articles
- Offer to help create new articles - when they want to create one, navigate them to the article editor
- Explain the workflow: Draft → Submit for Review → Editor Review → Publish
- Help them navigate to specific articles for editing"""

        elif section == 'editor':
            if article_id:
                article_info = ""
                if article_headline:
                    article_info += f"\n**Current Headline:** {article_headline}"
                if article_keywords:
                    article_info += f"\n**Current Keywords:** {article_keywords}"

                return f"""### Editor Context: Reviewing Article #{article_id}
You are helping an editor review article #{article_id} on {topic_display}.{article_info}

- You have full context of the article being reviewed (ID, headline, keywords shown above)
- Help evaluate the article quality and accuracy
- Suggest improvements before publishing
- Explain how to approve/reject or publish the article
- Discuss editorial standards and guidelines"""
            else:
                return f"""### Editor Context: {topic_display} Review Queue
You are helping an editor in the {topic_display} editor hub.
- Help them understand articles pending review
- Explain the review and publishing workflow
- Offer guidance on editorial standards
- Help them navigate to specific articles for review"""

        elif section == 'admin':
            return """### Admin Context: Administration Panel
You are helping an administrator manage the system.
- Help with user management (creating users, assigning groups/roles)
- Explain topic and content management
- Assist with prompt customization and tonality settings
- Guide through resource management
- Help understand system statistics and health"""

        elif section == 'profile':
            return """### Profile Context: User Settings
You are helping the user manage their profile and preferences.
- Explain available settings and preferences
- Help with tonality preferences for AI responses
- Discuss their current permissions and groups
- Guide through account-related options"""

        elif section == 'search':
            return """### Search Context: Article Search
You are helping the user search for articles.
- Help formulate effective search queries
- Explain search filters and options
- Suggest related topics or articles based on their interests
- Offer to navigate to specific articles from search results"""

        else:  # home or default
            # Provide different guidance based on role even on home page
            role_specific_tips = ""
            if current_role == 'analyst':
                role_specific_tips = "\n- As an analyst, you can navigate to the Analyst Hub to create new articles"
            elif current_role == 'editor':
                role_specific_tips = "\n- As an editor, you can navigate to the Editor Hub to review pending articles"
            elif current_role == 'admin':
                role_specific_tips = "\n- As an admin, you have access to all features including the Admin Panel"

            if topic:
                return f"""### Home Context: Viewing {topic_display} Articles
You are helping the user browse {topic_display} articles.
- Help them find relevant articles on {topic_display}
- Summarize or explain article content if asked
- Suggest related articles or topics
- Offer to navigate to article details or other sections{role_specific_tips}"""
            else:
                return f"""### Home Context: Main Dashboard
You are on the main dashboard with the user.
- Help them explore available topics and articles
- Explain what content is available
- Guide them to relevant sections based on their interests
- Offer navigation assistance to any part of the application{role_specific_tips}"""

    def _format_entitlements(self) -> str:
        """
        Format user entitlements as readable text.

        Returns:
            Formatted entitlements string
        """
        if not self.user_context:
            return "No entitlements available."

        topic_roles = self.user_context.get("topic_roles", {})
        scopes = self.user_context.get("scopes", [])
        highest_role = self.user_context.get("highest_role", "reader")

        # Role descriptions
        role_descriptions = {
            "admin": "Full administrative access - can manage users, content, and system settings",
            "analyst": "Can create and edit research articles, access data tools, and use AI agents",
            "editor": "Can review, approve, and publish content created by analysts",
            "reader": "Can view published content and chat with the assistant",
        }

        lines = []

        # Overall highest role
        lines.append(f"**Overall Access Level**: {highest_role.title()}")
        lines.append(f"  - {role_descriptions.get(highest_role, 'Standard access')}")
        lines.append("")

        # Topic-specific roles
        if topic_roles:
            lines.append("**Topic-Specific Access**:")
            for topic, role in topic_roles.items():
                topic_display = topic.replace("_", " ").title()
                lines.append(f"  - {topic_display}: {role.title()}")
        else:
            lines.append("**Topic-Specific Access**: Global access based on overall role")

        lines.append("")

        # Capabilities based on role
        lines.append("**What You Can Do**:")
        if highest_role in ["admin", "analyst"]:
            lines.append("  - Chat with the AI assistant about financial topics")
            lines.append("  - Search and access existing research articles")
            lines.append("  - Request real-time market data and stock information")
            lines.append("  - Search web for latest financial news")
            lines.append("  - Create and edit research articles (analyst features)")
            if highest_role == "admin":
                lines.append("  - Manage users and system settings (admin features)")
        elif highest_role == "editor":
            lines.append("  - Chat with the AI assistant about financial topics")
            lines.append("  - Search and access existing research articles")
            lines.append("  - Review and approve content for publication")
        else:  # reader
            lines.append("  - Chat with the AI assistant about financial topics")
            lines.append("  - Search and access published research articles")

        # Show raw scopes for transparency
        if scopes:
            lines.append("")
            lines.append("**Your Permission Scopes**:")
            for scope in scopes:
                lines.append(f"  - `{scope}`")

        return "\n".join(lines)

    def _is_entitlement_query(self, message: str) -> bool:
        """
        Check if the user is asking about their entitlements/permissions.

        Args:
            message: User message

        Returns:
            True if asking about entitlements
        """
        entitlement_keywords = [
            "permission", "entitlement", "access", "role", "what can i do",
            "my role", "my access", "my permission", "what am i allowed",
            "can i access", "what features", "my capabilities", "what's available",
            "am i allowed", "do i have access", "what topics", "my entitlements"
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in entitlement_keywords)

    def _handle_entitlement_query(self, user_message: str) -> str:
        """
        Handle a query about user entitlements.

        Args:
            user_message: User's message

        Returns:
            Response about user's entitlements
        """
        if not self.user_context:
            return "I don't have information about your permissions. Please ensure you're logged in."

        user_name = self.user_context.get("name", "there")
        entitlements = self._format_entitlements()

        response = f"""Hi {user_name}! Here's a summary of your access and permissions:

{entitlements}

Is there anything specific you'd like to know about what you can do, or would you like help getting started with any of these features?"""

        return response

    def _is_interface_query(self, message: str) -> bool:
        """
        Check if the user is asking about the interface/navigation/how to use the app.

        Args:
            message: User message

        Returns:
            True if asking about the interface
        """
        interface_keywords = [
            "how do i", "how can i", "where is", "where can i find",
            "how to", "what is the", "what does", "explain the",
            "show me how", "help me find",
            "interface", "menu", "button", "tab",
            "screen", "feature",
            "article editor", "content management",
            "what can i do here", "what's available", "how does this work",
            "where do i", "can you show me"
        ]
        # Note: Removed navigation-related keywords (navigate to, get to, navigation, page,
        # panel, section, analyst hub, editor hub, admin panel, profile page, search)
        # These are now handled by _detect_navigation_intent instead
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in interface_keywords)

    def _handle_interface_query(self, user_message: str) -> str:
        """
        Handle a query about the interface/navigation using frontend documentation.
        Only mentions features the user is entitled to access.

        Args:
            user_message: User's message

        Returns:
            Response about the interface, filtered by user permissions
        """
        # Load frontend documentation
        frontend_docs = _load_frontend_docs()

        if not frontend_docs:
            return "I apologize, but I don't have detailed interface documentation available. However, I can help you navigate - just tell me what you're trying to do!"

        # Get user permissions
        scopes = self.user_context.get("scopes", []) if self.user_context else []
        user_name = self.user_context.get("name", "there") if self.user_context else "there"

        # Determine what features the user can access
        has_admin = "global:admin" in scopes
        has_any_analyst = has_admin or any(":analyst" in s for s in scopes)
        has_any_editor = has_admin or any(":editor" in s for s in scopes)

        # Get specific topic permissions
        analyst_topics = []
        editor_topics = []
        for scope in scopes:
            if ":analyst" in scope:
                topic = scope.split(":")[0]
                if topic and topic != "global":
                    analyst_topics.append(topic.replace("_", " ").title())
            if ":editor" in scope:
                topic = scope.split(":")[0]
                if topic and topic != "global":
                    editor_topics.append(topic.replace("_", " ").title())

        # Build permission context for the LLM
        permission_context = f"""
## User's Access Level
- **User**: {user_name}
- **Admin Access**: {'Yes - full access to all features' if has_admin else 'No'}
- **Analyst Access**: {'Yes' if has_any_analyst else 'No'}{f' - Topics: {", ".join(analyst_topics)}' if analyst_topics and not has_admin else ''}
- **Editor Access**: {'Yes' if has_any_editor else 'No'}{f' - Topics: {", ".join(editor_topics)}' if editor_topics and not has_admin else ''}
- **Reader Access**: Yes (all authenticated users can browse published articles)

**IMPORTANT**: Only describe features and navigation paths the user has access to.
If they ask about a feature they cannot access, politely explain they would need additional permissions.
"""

        # Build the prompt
        prompt = f"""You are a helpful assistant explaining the application interface.
Use the following documentation to answer the user's question about the interface.

{permission_context}

## Frontend Documentation
{frontend_docs}

## User's Question
{user_message}

## Instructions
1. Answer the user's question about the interface clearly and concisely
2. Only mention features and paths the user has access to based on their permissions above
3. If they ask about something they can't access, explain what permission would be needed
4. Use the path notation from the documentation (e.g., `/analyst/{{topic}}`)
5. Be helpful and guide them to where they need to go
6. If relevant, offer to navigate them there using the navigation command

Provide a helpful response:"""

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt)
        ]

        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"Error handling interface query: {e}")
            return "I apologize, but I had trouble looking up that information. Could you rephrase your question?"

    def _detect_navigation_intent(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect if the user wants to navigate somewhere in the app.
        Uses current navigation context for context-aware navigation (e.g., "go back").

        Args:
            message: User message

        Returns:
            Navigation intent dict or None if no navigation intent detected
        """
        message_lower = message.lower()
        nav_context = getattr(self, 'navigation_context', None) or {}
        current_section = nav_context.get('section', 'home')
        current_topic = nav_context.get('topic')
        current_article_id = nav_context.get('article_id')

        logger.info(f"🔍 NAVIGATION DETECTION: message='{message_lower[:50]}...'")
        logger.info(f"   Context: section={current_section}, topic={current_topic}")

        # Context-aware "go back" navigation
        if any(kw in message_lower for kw in ["go back", "back to", "return to", "exit this"]):
            if current_section == 'analyst' and current_article_id:
                # In analyst editing article -> go back to analyst hub
                return {
                    "action": "navigate",
                    "target": f"/analyst/{current_topic}" if current_topic else "/analyst",
                    "params": {"topic": current_topic},
                    "requires_scope": f"{current_topic}:analyst" if current_topic else ":analyst",
                }
            elif current_section == 'editor' and current_article_id:
                # In editor reviewing article -> go back to editor hub
                return {
                    "action": "navigate",
                    "target": f"/editor/{current_topic}" if current_topic else "/editor",
                    "params": {"topic": current_topic},
                    "requires_scope": f"{current_topic}:editor" if current_topic else ":editor",
                }
            elif current_section in ['analyst', 'editor', 'admin', 'profile']:
                # In any section -> go back to home
                return {
                    "action": "navigate",
                    "target": "/",
                    "params": None,
                    "requires_scope": None,
                }

        # Define navigation patterns with required scopes
        navigation_patterns = [
            # Logout
            {
                "keywords": ["logout", "log out", "sign out", "signout", "exit app"],
                "action": "logout",
                "target": None,
                "params": None,
                "requires_scope": None,  # Anyone can logout
            },
            # Home/Articles
            {
                "keywords": ["go home", "go to home", "show articles", "main page", "home page",
                            "navigate to home", "take me home", "back to home", "open home"],
                "action": "navigate",
                "target": "/",
                "params": None,
                "requires_scope": None,
            },
            # Search
            {
                "keywords": ["search articles", "find articles", "search for", "go to search",
                            "navigate to search", "open search", "take me to search"],
                "action": "navigate",
                "target": "/?tab=search",
                "params": None,
                "requires_scope": None,
            },
            # Global Admin - must come before Topic Admin to match first
            {
                "keywords": ["global admin", "global administration", "system admin", "system administration",
                            "go to global admin", "navigate to global admin", "open global admin",
                            "take me to global admin", "global admin page", "global admin panel",
                            "manage users", "user management", "group management", "prompt management"],
                "action": "navigate",
                "target": "/admin/global",
                "params": None,
                "requires_scope": "global:admin",
            },
            # Topic Admin
            {
                "keywords": ["topic admin", "admin", "administration", "admin panel", "go to admin",
                            "navigate to admin", "open admin", "take me to admin", "admin page",
                            "admin section", "show admin", "bring me to admin", "content admin",
                            "article admin", "manage articles", "manage content"],
                "action": "navigate",
                "target": "/admin",
                "params": None,
                "requires_scope": None,  # Topic admin requires topic-specific admin scope, checked later
            },
            # Profile
            {
                "keywords": ["my profile", "go to profile", "profile settings", "my settings", "user profile",
                            "navigate to profile", "open profile", "take me to profile", "show my profile"],
                "action": "navigate",
                "target": "/profile",
                "params": None,
                "requires_scope": None,
            },
        ]

        # Check for topic-specific patterns
        topics = self._get_available_topics()

        for topic in topics:
            topic_display = topic.replace("_", " ")

            # Analyst hub for topic
            navigation_patterns.append({
                "keywords": [
                    f"write {topic_display} article",
                    f"create {topic_display} article",
                    f"new {topic_display} article",
                    f"{topic_display} analyst",
                    f"go to {topic_display} analyst",
                    f"open {topic_display} analyst",
                    f"navigate to {topic_display} analyst",
                    f"take me to {topic_display} analyst",
                ],
                "action": "navigate",
                "target": f"/analyst/{topic}",
                "params": {"topic": topic},
                "requires_scope": f"{topic}:analyst",
            })

            # Editor hub for topic
            navigation_patterns.append({
                "keywords": [
                    f"review {topic_display} articles",
                    f"edit {topic_display} articles",
                    f"{topic_display} editor",
                    f"go to {topic_display} editor",
                    f"open {topic_display} editor",
                    f"navigate to {topic_display} editor",
                    f"take me to {topic_display} editor",
                ],
                "action": "navigate",
                "target": f"/editor/{topic}",
                "params": {"topic": topic},
                "requires_scope": f"{topic}:editor",
            })

            # View topic articles
            navigation_patterns.append({
                "keywords": [
                    f"show {topic_display} articles",
                    f"view {topic_display}",
                    f"go to {topic_display}",
                    f"{topic_display} articles",
                    f"open {topic_display}",
                    f"navigate to {topic_display}",
                    f"show me {topic_display}",
                ],
                "action": "navigate",
                "target": f"/?tab={topic}",
                "params": {"topic": topic},
                "requires_scope": None,
            })

        # Generic analyst/editor patterns - these require topic selection
        navigation_patterns.extend([
            {
                "keywords": [
                    # Direct phrases
                    "write article", "create article", "new article",
                    # Phrases with "an" or "a"
                    "write an article", "create an article", "write a article",
                    # Intent phrases
                    "write about", "create an analysis", "write an analysis",
                    "draft an article", "draft article", "compose article",
                    # Research requests that imply article creation
                    "research and write", "please write", "please create",
                    # Navigation
                    "go to analyst", "go to the analyst", "analyst hub",
                    "analyst section", "analyst page", "analyst pane",
                    "open analyst", "navigate to analyst", "take me to analyst",
                    "show analyst", "analyst view"
                ],
                "action": "ask_topic",
                "intent": "analyst",
                "target": None,
                "params": None,
                "requires_scope": ":analyst",  # Any analyst scope
            },
            {
                "keywords": [
                    "review articles", "editor hub",
                    "go to editor", "go to the editor",
                    "editor section", "editor page", "editor pane",
                    "open editor", "navigate to editor", "take me to editor",
                    "show editor", "editor view", "publish articles"
                ],
                "action": "ask_topic",
                "intent": "editor",
                "target": None,
                "params": None,
                "requires_scope": ":editor",  # Any editor scope
            },
        ])

        # Check each pattern
        for pattern in navigation_patterns:
            matched_kw = next((kw for kw in pattern["keywords"] if kw in message_lower), None)
            if matched_kw:
                logger.info(f"🧭 NAV PATTERN MATCH: '{matched_kw}' -> {pattern['action']} {pattern['target']}")
                return {
                    "action": pattern["action"],
                    "target": pattern["target"],
                    "params": pattern["params"],
                    "requires_scope": pattern["requires_scope"],
                    "intent": pattern.get("intent"),  # For ask_topic action
                }

        logger.info(f"🧭 NAV DETECTION: No pattern matched")
        return None

    def _get_available_topics(self) -> List[str]:
        """Get list of available topics from database."""
        from models import Topic
        topics = self.db.query(Topic).filter(Topic.active == True).all()
        return [t.slug for t in topics]

    def _check_navigation_authorization(self, nav_intent: Dict[str, Any]) -> tuple[bool, str]:
        """
        Check if user is authorized for the navigation.

        Args:
            nav_intent: Navigation intent from _detect_navigation_intent

        Returns:
            Tuple of (is_authorized, reason_if_denied)
        """
        requires_scope = nav_intent.get("requires_scope")

        # No scope required
        if not requires_scope:
            return True, ""

        if not self.user_context:
            return False, "You need to be logged in to access this feature."

        scopes = self.user_context.get("scopes", [])

        # Global admin can do anything
        if "global:admin" in scopes:
            return True, ""

        # Check for exact scope match
        if requires_scope in scopes:
            return True, ""

        # Check for partial scope match (e.g., ":analyst" matches "macro:analyst")
        if requires_scope.startswith(":"):
            role_suffix = requires_scope
            if any(scope.endswith(role_suffix) for scope in scopes):
                return True, ""

        # Not authorized
        action = nav_intent.get("action", "navigate")
        target = nav_intent.get("target", "that page")

        if requires_scope == "global:admin":
            return False, f"You need administrator access to go to {target}. This feature is only available to system administrators."
        elif ":analyst" in requires_scope:
            topic = requires_scope.split(":")[0]
            topic_display = topic.replace("_", " ").title() if topic else "content"
            return False, f"You need analyst access to create {topic_display} articles. Contact your administrator to request this permission."
        elif ":editor" in requires_scope:
            topic = requires_scope.split(":")[0]
            topic_display = topic.replace("_", " ").title() if topic else "content"
            return False, f"You need editor access to review {topic_display} articles. Contact your administrator to request this permission."
        else:
            return False, f"You don't have permission to access {target}. Required scope: {requires_scope}"

    def _handle_navigation_intent(self, nav_intent: Dict[str, Any], user_message: str) -> Dict[str, Any]:
        """
        Handle a navigation intent with authorization check.

        Args:
            nav_intent: Navigation intent from _detect_navigation_intent
            user_message: Original user message

        Returns:
            Response dict with navigation command if authorized
        """
        is_authorized, denial_reason = self._check_navigation_authorization(nav_intent)

        if not is_authorized:
            return {
                "response": denial_reason,
                "agent_type": "navigation",
                "routing_reason": "Navigation authorization denied",
                "articles": [],
                "navigation": None,
            }

        # Build friendly response based on action
        action = nav_intent["action"]
        target = nav_intent["target"]
        params = nav_intent.get("params", {})
        intent = nav_intent.get("intent")

        # Handle ask_topic action - user needs to select a topic first
        if action == "ask_topic":
            # Get topics user has access to for this intent
            scopes = self.user_context.get("scopes", []) if self.user_context else []
            required_role = "analyst" if intent == "analyst" else "editor"

            # Find topics user can access
            accessible_topics = []
            for scope in scopes:
                if "global:admin" in scope:
                    # Global admin has access to all topics
                    accessible_topics = self._get_available_topics()
                    break
                if f":{required_role}" in scope or ":admin" in scope:
                    topic_part = scope.split(":")[0]
                    if topic_part and topic_part != "global":
                        accessible_topics.append(topic_part)

            if not accessible_topics:
                return {
                    "response": f"You don't have {required_role} access to any topics.",
                    "agent_type": "navigation",
                    "routing_reason": "No accessible topics for intent",
                    "articles": [],
                    "navigation": None,
                }

            # Format topics for display
            topic_list = [t.replace("_", " ").title() for t in accessible_topics]

            if intent == "analyst":
                response = f"Which topic would you like to write about? You have analyst access to:\n\n"
                for i, topic in enumerate(accessible_topics):
                    response += f"[{topic_list[i]} Analyst](goto:/analyst/{topic})  "
                response += "\n\nClick a button above or tell me which topic you'd like to work on."
            else:
                response = f"Which topic's articles would you like to review? You have editor access to:\n\n"
                for i, topic in enumerate(accessible_topics):
                    response += f"[{topic_list[i]} Editor](goto:/editor/{topic})  "
                response += "\n\nClick a button above or tell me which topic you'd like to review."

            return {
                "response": response,
                "agent_type": "navigation",
                "routing_reason": f"Asking user to select topic for {intent}",
                "articles": [],
                "navigation": None,  # No navigation yet - waiting for topic selection
            }

        if action == "logout":
            response = "Logging you out now. See you next time!"
        elif target and "/analyst" in target:
            topic = params.get("topic", "your chosen topic") if params else "your chosen topic"
            topic_display = topic.replace("_", " ").title() if topic != "your chosen topic" else topic
            response = f"Here's the Analyst Hub for {topic_display} where you can create and manage articles:\n\n[Go to {topic_display} Analyst](goto:{target})"
        elif target and "/editor" in target:
            topic = params.get("topic", "your chosen topic") if params else "your chosen topic"
            topic_display = topic.replace("_", " ").title() if topic != "your chosen topic" else topic
            response = f"Here's the Editor Hub for {topic_display} where you can review and publish articles:\n\n[Go to {topic_display} Editor](goto:{target})"
        elif target and "/admin" in target:
            response = f"Here's the Admin Panel where you can manage users, content, and system settings:\n\n[Go to Admin Panel](goto:{target})"
        elif target and "/profile" in target:
            response = f"Here's your profile settings:\n\n[Go to Profile](goto:{target})"
        elif target and "tab=search" in target:
            response = f"Here's the article search page:\n\n[Go to Search](goto:{target})"
        elif target and "tab=" in target:
            topic = params.get("topic", "") if params else ""
            topic_display = topic.replace("_", " ").title() if topic else "articles"
            response = f"Here are the {topic_display} articles:\n\n[View {topic_display}](goto:{target})"
        elif target == "/":
            response = f"Here's the home page:\n\n[Go to Home](goto:{target})"
        else:
            response = f"Here you go:\n\n[Navigate](goto:{target})"

        return {
            "response": response,
            "agent_type": "navigation",
            "routing_reason": f"User requested navigation: {action}",
            "articles": [],
            "navigation": {
                "action": action,
                "target": target,
                "params": params,
            },
        }

    def _get_user_permissions(self) -> Dict[str, Any]:
        """
        Get detailed permission info for the current user.
        Returns dict with role flags and topic-specific permissions.
        """
        if not self.user_context:
            return {
                "is_authenticated": False,
                "is_admin": False,
                "analyst_topics": [],
                "editor_topics": [],
                "all_topics": [],
            }

        scopes = self.user_context.get("scopes", [])
        is_admin = "global:admin" in scopes

        # Extract topic-specific permissions
        analyst_topics = []
        editor_topics = []
        all_topics = set()

        for scope in scopes:
            if ":" in scope:
                topic, role = scope.split(":", 1)
                if topic != "global":
                    all_topics.add(topic)
                    if role == "analyst":
                        analyst_topics.append(topic)
                    elif role == "editor":
                        editor_topics.append(topic)
                    elif role == "admin":
                        analyst_topics.append(topic)
                        editor_topics.append(topic)

        return {
            "is_authenticated": True,
            "is_admin": is_admin,
            "analyst_topics": analyst_topics,
            "editor_topics": editor_topics,
            "all_topics": list(all_topics),
        }

    def _can_perform_action(self, action_type: str, topic: Optional[str] = None) -> bool:
        """
        Check if user can perform a specific action type.
        This is used BEFORE suggesting an action to filter out unavailable options.

        Args:
            action_type: The action type to check
            topic: Optional topic context for the action

        Returns:
            True if user can perform the action, False otherwise
        """
        perms = self._get_user_permissions()

        if not perms["is_authenticated"]:
            return False

        is_admin = perms["is_admin"]
        analyst_topics = perms["analyst_topics"]
        editor_topics = perms["editor_topics"]

        # Admin-only actions
        admin_actions = [
            "deactivate_article", "reactivate_article", "recall_article",
            "purge_article", "delete_article", "delete_resource",
            "switch_admin_view", "switch_admin_topic", "switch_admin_subview",
        ]
        if action_type in admin_actions:
            return is_admin

        # Analyst actions (require analyst role for the topic)
        analyst_actions = [
            "save_draft", "submit_for_review", "create_new_article",
            "switch_view_editor", "switch_view_preview", "switch_view_resources",
            "add_resource", "link_resource", "unlink_resource", "browse_resources",
            "open_resource_modal", "edit_article", "submit_article",
        ]
        if action_type in analyst_actions:
            if is_admin:
                return True
            if topic:
                return topic in analyst_topics
            return len(analyst_topics) > 0

        # Editor actions (require editor role for the topic)
        editor_actions = ["publish_article", "reject_article"]
        if action_type in editor_actions:
            if is_admin:
                return True
            if topic:
                return topic in editor_topics
            return len(editor_topics) > 0

        # Reader actions (available to all authenticated users)
        reader_actions = [
            "view_article", "open_article", "download_pdf", "rate_article",
            "search_articles", "clear_search", "select_topic_tab", "select_topic",
            "close_modal", "select_article", "select_resource",
            "switch_profile_tab", "save_tonality",
        ]
        if action_type in reader_actions:
            return True

        # Delete account (user can delete their own account)
        if action_type == "delete_account":
            return True

        # Default: allow for authenticated users
        return True

    def _detect_ui_action_intent(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect if the user wants to trigger a UI action (button click, tab selection, etc.)
        Only returns actions the user has permission to perform.

        Args:
            message: User message

        Returns:
            UI action intent dict or None if no action intent detected
        """
        message_lower = message.lower()
        nav_context = getattr(self, 'navigation_context', None) or {}
        current_section = nav_context.get('section', 'home')
        current_role = nav_context.get('role', 'reader')
        current_topic = nav_context.get('topic')
        article_id = nav_context.get('article_id')

        logger.info(f"🔍 UI ACTION DETECTION: message='{message_lower}', section={current_section}, topic={current_topic}")

        # Get user permissions for filtering
        perms = self._get_user_permissions()
        is_admin = perms["is_admin"]
        analyst_topics = perms["analyst_topics"]
        editor_topics = perms["editor_topics"]

        # --- Analyst Edit Page Actions (when editing an article) ---
        # Only show analyst actions if user has analyst permissions for this topic
        can_edit = self._can_perform_action("save_draft", current_topic)

        if current_section == 'analyst' and article_id and can_edit:
            # Save draft
            if any(kw in message_lower for kw in [
                "save", "save this", "save article", "save changes", "save draft",
                "save my work", "save the article", "save it"
            ]):
                return {
                    "action_type": "save_draft",
                    "params": {"article_id": article_id, "topic": current_topic},
                    "description": "Save the current article draft",
                }

            # Submit for review
            if any(kw in message_lower for kw in [
                "submit", "submit this", "submit article", "submit for review",
                "send to editor", "submit to editor", "send for review",
                "mark as ready", "ready for review", "send to review"
            ]):
                return {
                    "action_type": "submit_for_review",
                    "params": {"article_id": article_id, "topic": current_topic},
                    "description": "Submit article for editor review",
                }

            # Switch to editor view
            if any(kw in message_lower for kw in [
                "editor view", "show editor only", "editor only", "just editor",
                "hide preview", "full editor", "switch to editor"
            ]):
                return {
                    "action_type": "switch_view_editor",
                    "params": {"topic": current_topic},
                    "description": "Switch to editor-only view",
                }

            # Switch to preview view
            if any(kw in message_lower for kw in [
                "show preview", "editor preview", "split view", "preview mode",
                "see preview", "toggle preview", "preview pane"
            ]):
                return {
                    "action_type": "switch_view_preview",
                    "params": {"topic": current_topic},
                    "description": "Switch to editor/preview split view",
                }

            # Switch to resources view
            if any(kw in message_lower for kw in [
                "show resources", "resources panel", "view resources", "resources view",
                "see resources", "resource panel", "attached resources", "linked resources"
            ]):
                return {
                    "action_type": "switch_view_resources",
                    "params": {"topic": current_topic},
                    "description": "Switch to editor/resources split view",
                }

            # --- Resource Actions (when editing an article) ---
            # Add/link resource to article
            if any(kw in message_lower for kw in [
                "add resource", "link resource", "attach resource", "add a resource",
                "link a resource", "attach a resource", "include resource",
                "add data", "link data", "attach data"
            ]):
                # Try to detect resource scope (global, topic, or article-specific)
                scope = "article"  # default
                if any(kw in message_lower for kw in ["global resource", "global data", "global"]):
                    scope = "global"
                elif any(kw in message_lower for kw in ["topic resource", "topic data", f"{current_topic} resource"]):
                    scope = "topic"

                return {
                    "action_type": "open_resource_modal",
                    "params": {
                        "article_id": article_id,
                        "scope": scope,
                        "action": "add",
                        "topic": current_topic,
                    },
                    "description": f"Open resource browser to add {scope} resource",
                }

            # Browse/view available resources
            if any(kw in message_lower for kw in [
                "browse resources", "find resources", "search resources",
                "available resources", "what resources", "list resources",
                "show available", "data sources"
            ]):
                scope = "all"
                if "global" in message_lower:
                    scope = "global"
                elif current_topic and (current_topic.replace("_", " ") in message_lower or "topic" in message_lower):
                    scope = "topic"

                return {
                    "action_type": "browse_resources",
                    "params": {
                        "scope": scope,
                        "topic": current_topic,
                    },
                    "description": f"Browse {scope} resources",
                }

            # Unlink/remove resource from article
            if any(kw in message_lower for kw in [
                "remove resource", "unlink resource", "detach resource",
                "remove the resource", "unlink the resource"
            ]):
                resource_id = self._extract_resource_id(message)
                return {
                    "action_type": "unlink_resource",
                    "params": {
                        "article_id": article_id,
                        "resource_id": resource_id,
                        "topic": current_topic,
                    },
                    "description": f"Remove resource from article",
                }

        # --- Analyst Hub Page Actions (when viewing article list) ---
        # Only show if user has analyst permissions
        if current_section == 'analyst' and not article_id and can_edit:
            # Create new article
            if any(kw in message_lower for kw in [
                "create article", "new article", "create new", "start article",
                "write new", "new draft", "create draft", "start new article"
            ]):
                return {
                    "action_type": "create_new_article",
                    "params": {"topic": current_topic},
                    "description": f"Create a new {current_topic} article",
                }

        # --- Edit Article Action (works from any section if user has analyst permissions) ---
        # Detect "edit article #54", "edit article 54", "open article 54 in editor"
        if any(kw in message_lower for kw in [
            "edit article", "open article", "edit the article", "open the article",
            "go to article", "edit this article", "open for editing"
        ]):
            target_id = self._extract_article_id(message) or article_id
            if target_id:
                # Check if user can edit (has analyst permission for some topic)
                if can_edit or analyst_topics:
                    logger.info(f"🎯 EDIT ARTICLE DETECTED: article_id={target_id}")
                    return {
                        "action_type": "edit_article",
                        "params": {"article_id": target_id, "topic": current_topic},
                        "description": f"Edit article #{target_id}",
                    }

        # --- Editor Hub Page Actions (when reviewing articles) ---
        # Only show editor actions if user has editor permissions for this topic
        can_publish = self._can_perform_action("publish_article", current_topic)
        logger.info(f"🔍 UI ACTION EDITOR CHECK: section={current_section}, can_publish={can_publish}, article_id={article_id}")

        if current_section == 'editor' and can_publish:
            # Publish article (with article ID extraction)
            if any(kw in message_lower for kw in [
                "publish this", "publish article", "approve and publish",
                "make it live", "go live", "publish it"
            ]):
                # Try to extract article ID from message
                target_id = article_id or self._extract_article_id(message)
                if target_id:
                    return {
                        "action_type": "publish_article",
                        "params": {"article_id": target_id, "topic": current_topic},
                        "description": f"Publish article #{target_id}",
                    }
                else:
                    return {
                        "action_type": "publish_article",
                        "params": {"topic": current_topic},
                        "description": "Publish the current/selected article",
                        "needs_article_id": True,
                    }

            # Reject article
            if any(kw in message_lower for kw in [
                "reject this", "reject article", "send back", "return to draft",
                "needs revision", "reject it", "send back to draft"
            ]):
                target_id = article_id or self._extract_article_id(message)
                if target_id:
                    return {
                        "action_type": "reject_article",
                        "params": {"article_id": target_id, "topic": current_topic},
                        "description": f"Reject article #{target_id} (return to draft)",
                    }
                else:
                    return {
                        "action_type": "reject_article",
                        "params": {"topic": current_topic},
                        "description": "Reject the current/selected article",
                        "needs_article_id": True,
                    }

        # --- Home Page Actions ---
        if current_section == 'home' or current_section == 'search':
            # Search articles
            if any(kw in message_lower for kw in [
                "search for", "find articles", "search articles", "look for",
                "find me", "search the"
            ]):
                # Extract search query
                search_query = message
                for prefix in ["search for", "find articles about", "search articles about",
                               "look for", "find me", "search the"]:
                    if prefix in message_lower:
                        idx = message_lower.find(prefix) + len(prefix)
                        search_query = message[idx:].strip()
                        break
                return {
                    "action_type": "search_articles",
                    "params": {"search_query": search_query},
                    "description": f"Search articles: {search_query}",
                }

            # Rate article
            if any(kw in message_lower for kw in [
                "rate this", "rate article", "give rating", "rate it",
                "submit rating", "star rating"
            ]):
                # Try to extract rating value
                rating = self._extract_rating(message)
                target_id = article_id or self._extract_article_id(message)
                return {
                    "action_type": "rate_article",
                    "params": {"article_id": target_id, "rating": rating},
                    "description": f"Rate article" + (f" #{target_id}" if target_id else ""),
                }

        # --- Topic Selection (common across pages) ---
        topics = self._get_available_topics()
        logger.info(f"🔍 TOPIC DETECTION: Available topics: {topics}")
        for topic in topics:
            topic_display = topic.replace("_", " ")
            # Check for various ways users might request topic navigation
            topic_patterns = [
                f"switch to {topic_display}",
                f"select {topic_display}",
                f"change to {topic_display}",
                f"{topic_display} topic",
                f"show {topic_display}",
                f"go to {topic_display}",
                f"navigate to {topic_display}",
                f"take me to {topic_display}",
                f"open {topic_display}",
                f"view {topic_display}",
                f"{topic_display} tab",
                f"{topic_display} articles",
                f"show me {topic_display}",
                f"display {topic_display}",
            ]
            # Also check for just the topic name if message is short/direct
            if len(message_lower.split()) <= 3:
                topic_patterns.append(topic_display)
                topic_patterns.append(topic)

            if any(kw in message_lower for kw in topic_patterns):
                logger.info(f"🎯 TOPIC MATCH: '{topic}' matched in message")
                return {
                    "action_type": "select_topic",
                    "params": {"topic": topic},
                    "description": f"Switch to {topic_display} topic",
                }

        # --- Download PDF (context aware) ---
        if any(kw in message_lower for kw in [
            "download pdf", "get pdf", "export pdf", "download as pdf",
            "generate pdf", "save as pdf"
        ]):
            target_id = article_id or self._extract_article_id(message)
            if target_id:
                return {
                    "action_type": "download_pdf",
                    "params": {"article_id": target_id},
                    "description": f"Download PDF for article #{target_id}",
                }

        # --- Close Modal ---
        if any(kw in message_lower for kw in [
            "close modal", "close popup", "close dialog", "close this",
            "dismiss", "cancel"
        ]):
            return {
                "action_type": "close_modal",
                "params": {},
                "description": "Close the current modal/dialog",
            }

        # --- Admin Section Actions ---
        # Only show admin actions if user has admin permissions
        if current_section == 'admin' and is_admin:
            # Admin view switching
            admin_views = {
                "users": ["users", "user list", "user management", "manage users"],
                "groups": ["groups", "group list", "group management", "manage groups"],
                "prompts": ["prompts", "prompt management", "manage prompts", "system prompts"],
                "resources": ["global resources", "resources", "resource management"],
                "topics": ["topics", "topic articles", "content"],
                "topics_admin": ["topic management", "manage topics", "topic settings"],
            }
            for view, keywords in admin_views.items():
                if any(kw in message_lower for kw in [f"show {k}" for k in keywords] + [f"go to {k}" for k in keywords] + keywords):
                    return {
                        "action_type": "switch_admin_view",
                        "params": {"view": view},
                        "description": f"Switch to {view} view",
                    }

            # Admin subview (articles vs resources within a topic)
            if any(kw in message_lower for kw in ["show articles", "article list", "topic articles"]):
                return {
                    "action_type": "switch_admin_subview",
                    "params": {"subview": "articles"},
                    "description": "Switch to articles subview",
                }
            if any(kw in message_lower for kw in ["show topic resources", "topic resources", "resource list"]):
                return {
                    "action_type": "switch_admin_subview",
                    "params": {"subview": "resources"},
                    "description": "Switch to resources subview",
                }

            # Admin article actions (deactivate, reactivate, recall, purge)
            target_id = article_id or self._extract_article_id(message)

            if any(kw in message_lower for kw in [
                "deactivate article", "deactivate this", "disable article",
                "mark inactive", "set inactive"
            ]):
                return {
                    "action_type": "deactivate_article",
                    "params": {"article_id": target_id, "requires_confirmation": True},
                    "description": f"Deactivate article" + (f" #{target_id}" if target_id else ""),
                    "needs_article_id": not target_id,
                }

            if any(kw in message_lower for kw in [
                "reactivate article", "reactivate this", "enable article",
                "mark active", "set active", "restore article"
            ]):
                return {
                    "action_type": "reactivate_article",
                    "params": {"article_id": target_id},
                    "description": f"Reactivate article" + (f" #{target_id}" if target_id else ""),
                    "needs_article_id": not target_id,
                }

            if any(kw in message_lower for kw in [
                "recall article", "recall this", "unpublish article",
                "return to draft", "send back to draft"
            ]):
                return {
                    "action_type": "recall_article",
                    "params": {"article_id": target_id, "requires_confirmation": True},
                    "description": f"Recall article to draft" + (f" #{target_id}" if target_id else ""),
                    "needs_article_id": not target_id,
                }

            if any(kw in message_lower for kw in [
                "purge article", "purge this", "permanently delete",
                "destroy article", "remove permanently"
            ]):
                return {
                    "action_type": "purge_article",
                    "params": {"article_id": target_id, "requires_confirmation": True},
                    "description": f"Permanently delete article" + (f" #{target_id}" if target_id else ""),
                    "needs_article_id": not target_id,
                }

            if any(kw in message_lower for kw in [
                "delete article", "delete this article"
            ]):
                return {
                    "action_type": "delete_article",
                    "params": {"article_id": target_id, "requires_confirmation": True},
                    "description": f"Delete article" + (f" #{target_id}" if target_id else ""),
                    "needs_article_id": not target_id,
                }

            # Delete resource
            resource_id = self._extract_resource_id(message)
            if any(kw in message_lower for kw in [
                "delete resource", "remove resource", "delete this resource"
            ]):
                return {
                    "action_type": "delete_resource",
                    "params": {"resource_id": resource_id, "requires_confirmation": True},
                    "description": f"Delete resource" + (f" #{resource_id}" if resource_id else ""),
                    "needs_resource_id": not resource_id,
                }

            # Delete user (admin only)
            user_id = self._extract_user_id(message)
            if any(kw in message_lower for kw in [
                "delete user", "remove user", "delete this user"
            ]):
                return {
                    "action_type": "delete_user",
                    "params": {"user_id": user_id, "requires_confirmation": True},
                    "description": f"Delete user" + (f" #{user_id}" if user_id else ""),
                    "needs_user_id": not user_id,
                }

            # Delete topic (admin only - very destructive!)
            topic_to_delete = self._extract_topic_name(message)
            if any(kw in message_lower for kw in [
                "delete topic", "remove topic", "delete this topic"
            ]):
                return {
                    "action_type": "delete_topic",
                    "params": {"topic_name": topic_to_delete or current_topic, "requires_confirmation": True},
                    "description": f"Delete topic" + (f" '{topic_to_delete or current_topic}'" if topic_to_delete or current_topic else ""),
                    "needs_topic_name": not (topic_to_delete or current_topic),
                }

        # --- Profile Section Actions ---
        if current_section == 'profile':
            # Tab switching
            profile_tabs = {
                "info": ["profile info", "my info", "account info", "information"],
                "settings": ["settings", "preferences", "options", "configuration"],
            }
            for tab, keywords in profile_tabs.items():
                if any(kw in message_lower for kw in keywords):
                    return {
                        "action_type": "switch_profile_tab",
                        "params": {"tab": tab},
                        "description": f"Switch to {tab} tab",
                    }

            # Save tonality
            if any(kw in message_lower for kw in [
                "save tonality", "save preferences", "save settings",
                "update tonality", "apply settings"
            ]):
                return {
                    "action_type": "save_tonality",
                    "params": {},
                    "description": "Save tonality preferences",
                }

            # Delete account/profile (dangerous!)
            if any(kw in message_lower for kw in [
                "delete account", "delete my account", "remove my account"
            ]):
                return {
                    "action_type": "delete_account",
                    "params": {"requires_confirmation": True},
                    "description": "Delete user account",
                }

            if any(kw in message_lower for kw in [
                "delete profile", "delete my profile", "remove my profile",
                "remove profile"
            ]):
                return {
                    "action_type": "delete_profile",
                    "params": {"requires_confirmation": True},
                    "description": "Delete user profile",
                }

        # --- Select/Focus Article Action (global) ---
        # This works across all sections to focus the chatbot context on a specific article
        # First, try to extract an article ID - if user just says "article 54" or "article id 54", select it
        target_id = self._extract_article_id(message)

        # Check for explicit selection phrases OR just "article [id]" pattern
        is_selection_intent = any(kw in message_lower for kw in [
            "focus on article", "focus article", "select article", "switch to article",
            "focus on #", "look at article", "tell me about article", "show article",
            "focus on the article", "focus on this article", "article id", "use article",
            "consider article", "work with article", "work on article"
        ])

        # Also match simple patterns like "article 54" or "article #54" (just article + number)
        import re
        simple_article_pattern = re.match(r'^article\s*#?\s*(\d+)$', message_lower.strip())

        if target_id and (is_selection_intent or simple_article_pattern):
            return {
                "action_type": "select_article",
                "params": {"article_id": target_id},
                "description": f"Focus on article #{target_id}",
            }
        elif is_selection_intent and not target_id:
            # Intent is clear but no ID found - ask for clarification
            return {
                "action_type": "select_article",
                "params": {},
                "description": "Focus on a specific article",
                "needs_article_id": True,
            }

        # --- Context-Aware Generic Delete Command ---
        # Handle generic "delete" or "delete this" based on current navigation context
        if any(kw in message_lower for kw in ["delete", "remove", "delete this", "remove this"]):
            # Determine what to delete based on context
            logger.info(f"🗑️ CONTEXT DELETE: section={current_section}, role={current_role}, article_id={article_id}")

            # Profile section: delete profile/account
            if current_section == 'profile':
                return {
                    "action_type": "delete_profile",
                    "params": {"requires_confirmation": True},
                    "description": "Delete your profile",
                }

            # Admin section: determine by view/context
            if current_section == 'admin' and is_admin:
                admin_view = nav_context.get('admin_view', 'topics')

                # Users view: delete user
                if admin_view == 'users':
                    user_id = self._extract_user_id(message)
                    return {
                        "action_type": "delete_user",
                        "params": {"user_id": user_id, "requires_confirmation": True},
                        "description": f"Delete user" + (f" #{user_id}" if user_id else ""),
                        "needs_user_id": not user_id,
                    }

                # Topics view with topic selected: delete article or topic
                if admin_view in ['topics', 'topics_admin']:
                    # If viewing a specific article, delete that
                    if article_id:
                        return {
                            "action_type": "delete_article",
                            "params": {"article_id": article_id, "requires_confirmation": True},
                            "description": f"Delete article #{article_id}",
                        }
                    # If in topic management, delete the topic
                    if admin_view == 'topics_admin' and current_topic:
                        return {
                            "action_type": "delete_topic",
                            "params": {"topic_name": current_topic, "requires_confirmation": True},
                            "description": f"Delete topic '{current_topic}'",
                        }

                # Resources view: delete resource
                if admin_view == 'resources':
                    resource_id = self._extract_resource_id(message)
                    return {
                        "action_type": "delete_resource",
                        "params": {"resource_id": resource_id, "requires_confirmation": True},
                        "description": f"Delete resource" + (f" #{resource_id}" if resource_id else ""),
                        "needs_resource_id": not resource_id,
                    }

            # Editor/Analyst section with article: delete that article
            if current_section in ['analyst', 'editor'] and article_id:
                return {
                    "action_type": "delete_article",
                    "params": {"article_id": article_id, "requires_confirmation": True},
                    "description": f"Delete article #{article_id}",
                }

            # Default: ask for clarification
            return {
                "action_type": "clarify_delete",
                "params": {},
                "description": "Clarify what to delete",
                "needs_clarification": True,
                "clarification_message": "What would you like to delete? Please specify: 'delete article #X', 'delete user #Y', 'delete resource #Z', 'delete topic [name]', or 'delete my profile'.",
            }

        return None

    def _extract_article_id(self, message: str) -> Optional[int]:
        """Extract article ID from a message like 'article 123' or 'article #42'."""
        import re
        patterns = [
            r'article\s*#?\s*(\d+)',
            r'#(\d+)',
            r'id\s*:?\s*(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                return int(match.group(1))
        return None

    def _extract_rating(self, message: str) -> Optional[int]:
        """Extract rating value from a message like 'rate 5 stars' or 'give it a 4'."""
        import re
        patterns = [
            r'(\d)\s*stars?',
            r'rate\s*(?:it\s*)?(\d)',
            r'give\s*(?:it\s*)?(?:a\s*)?(\d)',
            r'rating\s*(?:of\s*)?(\d)',
        ]
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                rating = int(match.group(1))
                if 1 <= rating <= 5:
                    return rating
        return None

    def _extract_resource_id(self, message: str) -> Optional[int]:
        """Extract resource ID from a message like 'resource 123' or 'resource #42'."""
        import re
        patterns = [
            r'resource\s*#?\s*(\d+)',
            r'data\s*#?\s*(\d+)',
            r'#(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                return int(match.group(1))
        return None

    def _extract_user_id(self, message: str) -> Optional[int]:
        """Extract user ID from a message like 'user 123' or 'user #42'."""
        import re
        patterns = [
            r'user\s*#?\s*(\d+)',
            r'user\s+id\s*:?\s*(\d+)',
            r'#(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                return int(match.group(1))
        return None

    def _extract_topic_name(self, message: str) -> Optional[str]:
        """Extract topic name from a message like 'topic economics' or 'delete topic fixed_income'."""
        import re
        # Try to match "topic <name>" pattern
        patterns = [
            r'topic\s+["\']?([a-zA-Z0-9_\-\s]+)["\']?',
            r'delete\s+["\']?([a-zA-Z0-9_\-\s]+)["\']?\s+topic',
        ]
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                topic_name = match.group(1).strip()
                # Skip if it's just a common word like "this" or "the"
                if topic_name not in ['this', 'the', 'a', 'an', 'my']:
                    return topic_name.replace(' ', '_')

        # Check if any known topic is mentioned
        topics = self._get_available_topics()
        message_lower = message.lower()
        for topic in topics:
            topic_display = topic.replace('_', ' ')
            if topic in message_lower or topic_display in message_lower:
                return topic

        return None

    def _handle_ui_action_intent(self, action_intent: Dict[str, Any], user_message: str) -> Dict[str, Any]:
        """
        Handle a UI action intent by returning an action command for the frontend.

        Args:
            action_intent: UI action intent from _detect_ui_action_intent
            user_message: Original user message

        Returns:
            Response dict with ui_action for the frontend to execute
        """
        action_type = action_intent["action_type"]
        params = action_intent.get("params", {})
        description = action_intent.get("description", action_type)
        needs_article_id = action_intent.get("needs_article_id", False)
        needs_resource_id = action_intent.get("needs_resource_id", False)

        # Check permissions for certain actions
        if not self._check_action_permissions(action_type, params):
            return {
                "response": f"You don't have permission to perform this action: {description}",
                "agent_type": "ui_action",
                "routing_reason": f"UI action denied: {action_type}",
                "articles": [],
                "ui_action": None,
            }

        # Handle case where article ID is needed but not provided
        if needs_article_id and not params.get("article_id"):
            # Try to use the article from navigation context
            nav_context = getattr(self, 'navigation_context', None) or {}
            context_article_id = nav_context.get('article_id')
            if context_article_id:
                params["article_id"] = context_article_id
            else:
                return {
                    "response": f"Please specify which article you want to {action_type.replace('_', ' ')}. You can say something like 'article #123' or click on an article first to select it.",
                    "agent_type": "ui_action",
                    "routing_reason": f"UI action needs article ID: {action_type}",
                    "articles": [],
                    "ui_action": None,
                }

        # Handle case where resource ID is needed but not provided
        if needs_resource_id and not params.get("resource_id"):
            nav_context = getattr(self, 'navigation_context', None) or {}
            context_resource_id = nav_context.get('resource_id')
            if context_resource_id:
                params["resource_id"] = context_resource_id
            else:
                return {
                    "response": f"Please specify which resource you want to {action_type.replace('_', ' ')}. You can say something like 'resource #123' or click on a resource first to select it.",
                    "agent_type": "ui_action",
                    "routing_reason": f"UI action needs resource ID: {action_type}",
                    "articles": [],
                    "ui_action": None,
                }

        # Handle case where user ID is needed but not provided
        needs_user_id = action_intent.get("needs_user_id", False)
        if needs_user_id and not params.get("user_id"):
            return {
                "response": "Please specify which user you want to delete. You can say something like 'delete user #123' or select a user first.",
                "agent_type": "ui_action",
                "routing_reason": f"UI action needs user ID: {action_type}",
                "articles": [],
                "ui_action": None,
            }

        # Handle case where topic name is needed but not provided
        needs_topic_name = action_intent.get("needs_topic_name", False)
        if needs_topic_name and not params.get("topic_name"):
            return {
                "response": "Please specify which topic you want to delete. You can say something like 'delete topic economics' or navigate to the topic first.",
                "agent_type": "ui_action",
                "routing_reason": f"UI action needs topic name: {action_type}",
                "articles": [],
                "ui_action": None,
            }

        # Handle clarification requests
        needs_clarification = action_intent.get("needs_clarification", False)
        if needs_clarification:
            clarification_message = action_intent.get("clarification_message", "Please be more specific about what you want to delete.")
            return {
                "response": clarification_message,
                "agent_type": "ui_action",
                "routing_reason": "UI action needs clarification",
                "articles": [],
                "ui_action": None,
            }

        # Handle actions that require confirmation
        requires_confirmation = params.get("requires_confirmation", False)
        if requires_confirmation and action_type in ACTIONS_REQUIRING_CONFIRMATION:
            # For publish_article, use HITL button-based confirmation
            if action_type == "publish_article":
                article_id = params.get("article_id")
                import uuid
                return {
                    "response": f"You're about to publish article #{article_id}. This will make it visible to all readers.",
                    "agent_type": "ui_action",
                    "routing_reason": f"HITL confirmation for publish_article",
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

            # Text-based confirmation for other destructive actions
            confirmation_message = self._get_confirmation_message(action_type, params)
            return {
                "response": confirmation_message,
                "agent_type": "ui_action",
                "routing_reason": f"UI action requires confirmation: {action_type}",
                "articles": [],
                "ui_action": {
                    "type": action_type,
                    "params": {
                        **params,
                        "requires_confirmation": True,
                        "confirmation_message": confirmation_message,
                    },
                },
            }

        # Build friendly response message
        response = self._get_action_response_message(action_type, params, description)

        logger.info(f"🎯 UI ACTION: {action_type} with params {params}")

        return {
            "response": response,
            "agent_type": "ui_action",
            "routing_reason": f"UI action triggered: {action_type}",
            "articles": [],
            "ui_action": {
                "type": action_type,
                "params": params,
            },
        }

    def _get_confirmation_message(self, action_type: str, params: Dict[str, Any]) -> str:
        """Generate a confirmation message for destructive actions."""
        article_id = params.get("article_id")
        resource_id = params.get("resource_id")
        user_id = params.get("user_id")
        user_name = params.get("user_name", f"user #{user_id}" if user_id else "the user")
        topic_name = params.get("topic_name", params.get("topic", "the topic"))

        messages = {
            # Article actions
            "purge_article": f"**⚠️ WARNING: This will PERMANENTLY DELETE article #{article_id} and all its data. This action cannot be undone.**\n\nTo confirm, please say 'yes, purge article #{article_id}' or 'confirm purge'.",
            "delete_article": f"**⚠️ WARNING:** Are you sure you want to deactivate article #{article_id}? The article will be hidden but can be reactivated later.\n\nTo confirm, please say 'yes, delete article #{article_id}' or 'confirm delete'.",
            "deactivate_article": f"**⚠️ WARNING:** Are you sure you want to deactivate article #{article_id}? The article will be hidden from readers but can be reactivated later.\n\nTo confirm, please say 'yes, deactivate article #{article_id}' or 'confirm deactivate'.",
            "recall_article": f"**⚠️ WARNING:** Are you sure you want to recall article #{article_id} back to draft status? It will be unpublished and readers will no longer have access.\n\nTo confirm, please say 'yes, recall article #{article_id}' or 'confirm recall'.",
            "publish_article": f"**📢 PUBLISH CONFIRMATION:** You are about to publish article #{article_id}. This will make it visible to all readers.\n\nTo confirm, please say 'yes, publish article #{article_id}' or 'confirm publish'.",
            # Resource actions
            "delete_resource": f"**⚠️ WARNING:** Are you sure you want to delete resource #{resource_id}? This cannot be undone.\n\nTo confirm, please say 'yes, delete resource #{resource_id}' or 'confirm delete'.",
            # User/Account actions
            "delete_account": "**⚠️ WARNING: This will PERMANENTLY DELETE your account and all associated data. This action cannot be undone.**\n\nTo confirm, please say 'yes, delete my account' or 'confirm delete account'.",
            "delete_profile": "**⚠️ WARNING: This will PERMANENTLY DELETE your profile and all associated data. This action cannot be undone.**\n\nTo confirm, please say 'yes, delete my profile' or 'confirm delete profile'.",
            "delete_user": f"**⚠️ WARNING: This will PERMANENTLY DELETE {user_name} and all their data. This action cannot be undone.**\n\nTo confirm, please say 'yes, delete user' or 'confirm delete user'.",
            # Topic actions
            "delete_topic": f"**⚠️ WARNING: This will PERMANENTLY DELETE the topic '{topic_name}' and all its articles, resources, and settings. This action cannot be undone.**\n\nTo confirm, please say 'yes, delete topic {topic_name}' or 'confirm delete topic'.",
        }

        return messages.get(action_type, f"Please confirm this action: {action_type}")

    def _check_action_permissions(self, action_type: str, params: Dict[str, Any]) -> bool:
        """Check if the user has permission to perform the action."""
        if not self.user_context:
            return False

        scopes = self.user_context.get("scopes", [])
        is_admin = "global:admin" in scopes

        # Actions that require specific permissions
        if action_type in ["submit_for_review", "save_draft", "create_new_article"]:
            # Requires analyst role
            topic = params.get("topic") or (getattr(self, 'navigation_context', None) or {}).get('topic')
            if is_admin:
                return True
            if topic:
                return f"{topic}:analyst" in scopes
            return any(":analyst" in s for s in scopes)

        if action_type in ["publish_article", "reject_article"]:
            # Requires editor role
            topic = params.get("topic") or (getattr(self, 'navigation_context', None) or {}).get('topic')
            if is_admin:
                return True
            if topic:
                return f"{topic}:editor" in scopes
            return any(":editor" in s for s in scopes)

        # Admin-only actions
        if action_type in [
            "delete_article", "deactivate_article", "reactivate_article",
            "recall_article", "purge_article", "delete_resource",
            "delete_user", "delete_topic",  # User and topic deletion
            "switch_admin_view", "switch_admin_topic", "switch_admin_subview"
        ]:
            return is_admin

        # All other actions are allowed for authenticated users
        return True

    def _get_action_response_message(self, action_type: str, params: Dict[str, Any], description: str) -> str:
        """Generate a friendly response message for an action."""
        scope = params.get('scope', 'article')
        scope_display = f"{scope} " if scope and scope != 'article' else ""
        view = params.get('view', '')
        tab = params.get('tab', '')
        subview = params.get('subview', '')

        messages = {
            "save_draft": "Saving your article draft now...",
            "submit_for_review": "Submitting your article for editor review...",
            "switch_view_editor": "Switching to editor-only view.",
            "switch_view_preview": "Switching to editor/preview split view.",
            "switch_view_resources": "Switching to show the resources panel.",
            # Resource actions
            "open_resource_modal": f"Opening the {scope_display}resource browser...",
            "browse_resources": f"Browsing {scope_display}resources...",
            "link_resource": f"Linking resource #{params.get('resource_id', '')} to your article...",
            "unlink_resource": f"Removing resource #{params.get('resource_id', '')} from your article...",
            "add_resource": f"Adding {scope_display}resource to your article...",
            "remove_resource": f"Removing resource from your article...",
            # Article actions
            "create_new_article": f"Creating a new article for you...",
            "view_article": f"Opening article #{params.get('article_id', '')}...",
            "edit_article": f"Opening article #{params.get('article_id', '')} in the editor...",
            "submit_article": f"Submitting article #{params.get('article_id', '')} for review...",
            "reject_article": f"Rejecting article #{params.get('article_id', '')} and returning it to draft...",
            "publish_article": f"Publishing article #{params.get('article_id', '')}...",
            "download_pdf": f"Downloading PDF for article #{params.get('article_id', '')}...",
            # Admin article actions
            "deactivate_article": f"Deactivating article #{params.get('article_id', '')}...",
            "reactivate_article": f"Reactivating article #{params.get('article_id', '')}...",
            "recall_article": f"Recalling article #{params.get('article_id', '')} to draft...",
            "purge_article": f"Permanently deleting article #{params.get('article_id', '')}...",
            "delete_article": f"Deleting article #{params.get('article_id', '')}...",
            "delete_resource": f"Deleting resource #{params.get('resource_id', '')}...",
            # Admin view switching
            "switch_admin_view": f"Switching to {view.replace('_', ' ')} view...",
            "switch_admin_topic": f"Switching to {params.get('topic', '').replace('_', ' ').title()} topic...",
            "switch_admin_subview": f"Switching to {subview} subview...",
            # Profile actions
            "switch_profile_tab": f"Switching to {tab} tab...",
            "save_tonality": "Saving your tonality preferences...",
            "delete_account": "Processing account deletion...",
            "delete_profile": "Processing profile deletion...",
            # Admin destructive actions
            "delete_user": f"Deleting user #{params.get('user_id', '')}...",
            "delete_topic": f"Deleting topic '{params.get('topic_name', '')}'...",
            # Home/search actions
            "select_topic_tab": f"Switching to {params.get('topic', '').replace('_', ' ').title()} articles...",
            "rate_article": f"Opening rating dialog" + (f" with {params.get('rating')} stars" if params.get('rating') else "") + "...",
            "search_articles": f"Searching for: {params.get('search_query', '')}...",
            "clear_search": "Clearing search results...",
            "select_topic": f"Switching to {params.get('topic', '').replace('_', ' ').title()} topic...",
            "close_modal": "Closing the dialog...",
            # Context selection
            "select_article": f"Article #{params.get('article_id', '')} selected.",
            "select_resource": f"Resource #{params.get('resource_id', '')} selected.",
        }

        return messages.get(action_type, f"Executing: {description}")

    def _needs_live_data(self, message: str) -> Dict[str, Any]:
        """
        Determine if the query needs live data from content agents.

        Args:
            message: User message

        Returns:
            Dict with 'needs_web_search', 'needs_market_data', and extracted parameters
        """
        message_lower = message.lower()

        result = {
            "needs_web_search": False,
            "needs_market_data": False,
            "stock_symbols": [],
            "search_query": None,
        }

        # Check for news/current events keywords
        news_keywords = [
            "latest", "recent", "today", "news", "current", "happening",
            "breaking", "update", "this week", "this month", "right now"
        ]
        if any(kw in message_lower for kw in news_keywords):
            result["needs_web_search"] = True
            result["search_query"] = message

        # Check for market data keywords
        market_keywords = [
            "price", "stock", "share", "ticker", "trading", "market cap",
            "pe ratio", "dividend", "52 week", "volume", "yield", "treasury",
            "fx rate", "exchange rate", "currency"
        ]
        if any(kw in message_lower for kw in market_keywords):
            result["needs_market_data"] = True

        # Extract stock symbols (1-5 uppercase letters)
        symbols = re.findall(r'\b([A-Z]{1,5})\b', message)
        # Filter out common words that aren't stock symbols
        common_words = {"I", "A", "THE", "AND", "OR", "FOR", "TO", "IN", "ON", "AT", "IS", "IT", "BE", "AS", "AN", "BY", "SO", "IF", "OF", "US", "UK", "EU", "GDP", "CPI", "FED", "ECB", "FX", "PE", "CEO", "CFO", "IPO"}
        result["stock_symbols"] = [s for s in symbols if s not in common_words][:5]

        if result["stock_symbols"]:
            result["needs_market_data"] = True

        return result

    def _fetch_live_data(self, data_needs: Dict[str, Any], topic: str) -> Dict[str, Any]:
        """
        Fetch live data from content agents.

        Args:
            data_needs: Dict from _needs_live_data
            topic: Topic for context

        Returns:
            Dict with web_results and market_data
        """
        results = {
            "web_results": [],
            "market_data": [],
        }

        # Fetch web search results
        if data_needs.get("needs_web_search"):
            query = data_needs.get("search_query", "")
            if query:
                logger.info(f"🌐 Fetching web news for: {query[:50]}...")
                search_result = self.web_search_agent.search_financial_news(query, max_results=5)
                if search_result.get("success"):
                    results["web_results"] = search_result.get("results", [])
                    logger.info(f"   Found {len(results['web_results'])} news articles")

        # Fetch market data
        if data_needs.get("needs_market_data"):
            symbols = data_needs.get("stock_symbols", [])
            for symbol in symbols:
                logger.info(f"📊 Fetching market data for: {symbol}")
                stock_result = self.data_download_agent.fetch_stock_info(symbol)
                if stock_result.get("success"):
                    results["market_data"].append(stock_result)
                    logger.info(f"   Got data for {symbol}")

        return results

    def chat(self, user_message: str, navigation_context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Process user message through main chat agent.

        Args:
            user_message: User's message
            navigation_context: Optional dict with section, topic, article_id, sub_nav

        Returns:
            Dict with 'response', 'agent_type', 'routing_reason', 'articles' (list of referenced articles)
        """
        import time
        start_time = time.time()

        # Store navigation context for use in prompts
        self.navigation_context = navigation_context

        # Rebuild system prompt with navigation context (includes article info)
        self.system_prompt = self._build_system_prompt()

        # Log user context info
        user_name = self.user_context.get("name", "Anonymous") if self.user_context else "Anonymous"

        logger.info("=" * 80)
        logger.info(f"🤖 MAIN CHAT AGENT: New message received")
        logger.info(f"   User: {user_name}")
        if navigation_context:
            logger.info(f"   Navigation: section={navigation_context.get('section')}, topic={navigation_context.get('topic')}")
            if navigation_context.get('article_id'):
                logger.info(f"   Article: #{navigation_context.get('article_id')} - {navigation_context.get('article_headline', 'No headline')}")
        logger.info(f"   Query: '{user_message[:100]}{'...' if len(user_message) > 100 else ''}'")

        # Step 0a: Check if this is an entitlement query (fast path)
        if self._is_entitlement_query(user_message):
            logger.info(f"🔐 ENTITLEMENT QUERY: User asking about permissions")
            response = self._handle_entitlement_query(user_message)
            total_time = time.time() - start_time
            logger.info(f"✓ ENTITLEMENT RESPONSE: {total_time:.2f}s")
            logger.info("=" * 80)

            return {
                'response': response,
                'agent_type': 'entitlements',
                'routing_reason': 'User asked about their permissions/entitlements',
                'articles': []
            }

        # Step 0aa: Check if this is a publish confirmation/cancellation (HITL response)
        publish_confirmation = self._detect_publish_confirmation(user_message)
        if publish_confirmation:
            action = publish_confirmation.get("action")
            article_id = publish_confirmation.get("article_id")

            if action == "confirm" and article_id:
                logger.info(f"✅ PUBLISH CONFIRMATION: Executing publish for article #{article_id}")
                result = self._execute_publish_article(article_id)
                total_time = time.time() - start_time
                logger.info(f"✓ PUBLISH {'SUCCESS' if result.get('success') else 'FAILED'}: {total_time:.2f}s")
                logger.info("=" * 80)

                if result.get("success"):
                    response = f"✅ **Published!** {result.get('message')}"
                else:
                    response = f"❌ **Could not publish.** {result.get('message')}"

                return {
                    'response': response,
                    'agent_type': 'editor',
                    'routing_reason': 'HITL publish confirmation executed',
                    'articles': []
                }

            elif action == "cancel":
                logger.info(f"❌ PUBLISH CANCELLED: User cancelled publish" + (f" for article #{article_id}" if article_id else ""))
                total_time = time.time() - start_time
                logger.info(f"✓ CANCELLATION ACKNOWLEDGED: {total_time:.2f}s")
                logger.info("=" * 80)

                return {
                    'response': "Okay, I've cancelled the publish action. The article remains in its current state.",
                    'agent_type': 'editor',
                    'routing_reason': 'HITL publish cancelled',
                    'articles': []
                }

        # Step 0b: Check if this is a content generation request (analyst editor context)
        gen_intent = self._detect_content_generation_intent(user_message)
        if gen_intent:
            logger.info(f"📝 CONTENT GENERATION: topic={gen_intent.get('topic')}, article_id={gen_intent.get('article_id')}")
            result = self._handle_content_generation(gen_intent, user_message)
            total_time = time.time() - start_time
            logger.info(f"✓ CONTENT GENERATION RESPONSE: {total_time:.2f}s")
            logger.info("=" * 80)
            return result

        # Step 0c: Check if this is a navigation request (fast path)
        nav_intent = self._detect_navigation_intent(user_message)
        if nav_intent:
            logger.info(f"🧭 NAVIGATION INTENT: {nav_intent.get('action')} -> {nav_intent.get('target')}")
            result = self._handle_navigation_intent(nav_intent, user_message)
            total_time = time.time() - start_time
            logger.info(f"✓ NAVIGATION RESPONSE: {total_time:.2f}s")
            logger.info("=" * 80)
            return result

        # Step 0d: Check if this is an interface/how-to question
        if self._is_interface_query(user_message):
            logger.info(f"📖 INTERFACE QUERY: User asking about the interface")
            response = self._handle_interface_query(user_message)
            total_time = time.time() - start_time
            logger.info(f"✓ INTERFACE RESPONSE: {total_time:.2f}s")
            logger.info("=" * 80)

            return {
                'response': response,
                'agent_type': 'interface_help',
                'routing_reason': 'User asked about the interface/navigation',
                'articles': []
            }

        # Step 0e: Check if this is an editor request (when role=editor)
        editor_intent = self._detect_editor_intent(user_message)
        if editor_intent:
            logger.info(f"📝 EDITOR INTENT: {editor_intent.get('action')} for article {editor_intent.get('article_id')}")
            result = self._handle_editor_request(editor_intent, user_message)
            total_time = time.time() - start_time
            logger.info(f"✓ EDITOR RESPONSE: {total_time:.2f}s")
            logger.info("=" * 80)
            return result

        # Step 0f: Check if this is a UI action request (button click, tab selection, etc.)
        ui_action_intent = self._detect_ui_action_intent(user_message)
        if ui_action_intent:
            logger.info(f"🎯 UI ACTION INTENT: {ui_action_intent.get('action_type')}")
            result = self._handle_ui_action_intent(ui_action_intent, user_message)
            total_time = time.time() - start_time
            logger.info(f"✓ UI ACTION RESPONSE: {total_time:.2f}s")
            logger.info("=" * 80)
            return result

        # Step 1: Determine topic for query
        logger.info(f"🔄 ROUTING: Analyzing query to determine topic...")
        routing_start = time.time()
        routing_decision = self._route_query(user_message)
        routing_time = time.time() - routing_start

        agent_type = routing_decision.get('agent', 'general')
        routing_reason = routing_decision.get('reason', 'General conversation')

        logger.info(f"✓ ROUTING COMPLETE: {routing_time:.2f}s")
        logger.info(f"   Selected: {agent_type.upper()}")
        logger.info(f"   Reason: {routing_reason}")

        # Step 2: Check if live data is needed (content agent delegation)
        data_needs = self._needs_live_data(user_message)
        live_data = {"web_results": [], "market_data": []}

        if data_needs.get("needs_web_search") or data_needs.get("needs_market_data"):
            logger.info(f"📡 CONTENT AGENTS: Delegating to fetch live data...")
            if data_needs.get("needs_web_search"):
                logger.info(f"   → WebSearchAgent: news search")
            if data_needs.get("needs_market_data"):
                logger.info(f"   → DataDownloadAgent: {data_needs.get('stock_symbols', [])}")

            live_data = self._fetch_live_data(data_needs, agent_type)

        # Step 3: Handle query based on routing decision
        if agent_type == 'general':
            # Handle general conversation directly with main chat agent
            logger.info(f"💬 GENERAL CHAT MODE: Handling conversation directly")

            chat_start = time.time()
            final_response = self._handle_general_chat(user_message)
            chat_time = time.time() - chat_start

            total_time = time.time() - start_time
            logger.info(f"✓ GENERAL CHAT COMPLETE: {chat_time:.2f}s")
            logger.info(f"⏱️  TOTAL TIME: {total_time:.2f}s")
            logger.info("=" * 80)

            return {
                'response': final_response,
                'agent_type': 'general',
                'routing_reason': routing_reason,
                'articles': []
            }
        else:
            # Search for relevant articles for the topic
            logger.info(f"🔍 SEARCHING ARTICLES: Looking for {agent_type.upper()} articles...")
            search_start = time.time()

            # Search articles using the user's query
            articles = self._search_relevant_articles(agent_type, user_message)
            search_time = time.time() - search_start

            logger.info(f"✓ ARTICLE SEARCH COMPLETE: {search_time:.2f}s")
            logger.info(f"   Found {len(articles)} relevant articles")

            # Search for relevant resources
            resources = []
            if self.resource_query_agents:
                logger.info(f"📚 SEARCHING RESOURCES: Looking for relevant resources...")
                resource_start = time.time()
                resources = self._search_relevant_resources(user_message)
                resource_time = time.time() - resource_start
                logger.info(f"✓ RESOURCE SEARCH COMPLETE: {resource_time:.2f}s")
                logger.info(f"   Found {len(resources)} relevant resources")

            # Use found articles, resources, and live data to craft response
            logger.info(f"📝 SYNTHESIZING: Crafting response using content...")
            synthesis_start = time.time()
            final_response = self._synthesize_response_from_content(
                user_message, articles, resources, agent_type, live_data
            )
            synthesis_time = time.time() - synthesis_start
            logger.info(f"✓ SYNTHESIS COMPLETE: {synthesis_time:.2f}s")

            total_time = time.time() - start_time
            logger.info(f"⏱️  TOTAL TIME: {total_time:.2f}s")
            logger.info("=" * 80)

            return {
                'response': final_response,
                'agent_type': agent_type,
                'routing_reason': routing_reason,
                'articles': articles,
                'resources': resources,
                'live_data': live_data
            }

    def _handle_general_chat(self, user_message: str) -> str:
        """
        Handle general conversation directly without routing to specialists.

        Args:
            user_message: User's message

        Returns:
            Response string
        """
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_message)
        ]

        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"Error in general chat: {e}")
            return "I apologize, but I encountered an error processing your message. Please try again."

    def _search_relevant_articles(self, topic: str, query: str) -> List[Dict]:
        """
        Search for relevant articles for a given topic and query.

        Args:
            topic: Topic to search (macro, equity, fixed_income, esg)
            query: Search query

        Returns:
            List of relevant articles (up to 5)
        """
        try:
            # Search articles using ContentService
            articles = ContentService.search_articles(self.db, topic, query, limit=5)

            # If no results from search, get recent articles
            if not articles:
                logger.info(f"   No search results, falling back to recent articles")
                articles = ContentService.get_recent_articles(self.db, topic, limit=3)

            return articles
        except Exception as e:
            logger.error(f"Error searching articles: {e}")
            return []

    def _search_relevant_resources(self, query: str) -> List[Dict]:
        """
        Search for relevant resources using ResourceQueryAgents.

        Args:
            query: Search query

        Returns:
            List of relevant resources with their content
        """
        if not self.resource_query_agents:
            return []

        all_resources = []

        for agent in self.resource_query_agents:
            try:
                result = agent.query(query, limit=3)
                if result.get("success") and result.get("resources"):
                    all_resources.extend(result["resources"])
            except Exception as e:
                logger.error(f"Error querying resources with {agent.__class__.__name__}: {e}")

        # Sort by similarity score and deduplicate
        all_resources.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)

        # Take top results
        return all_resources[:5]

    def _synthesize_response_from_articles(self, user_query: str, articles: List[Dict], agent_type: str) -> str:
        """
        Use existing articles to craft a specific answer to the user's query.
        Deprecated: Use _synthesize_response_from_content instead.
        """
        return self._synthesize_response_from_content(user_query, articles, [], agent_type)

    def _synthesize_response_from_content(
        self,
        user_query: str,
        articles: List[Dict],
        resources: List[Dict],
        agent_type: str,
        live_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Use existing articles, resources, and live data to craft a specific answer to the user's query.

        Args:
            user_query: User's original question
            articles: List of relevant articles
            resources: List of relevant resources (text, tables)
            agent_type: Type of topic (macro, equity, fixed_income, esg)
            live_data: Optional dict with web_results and market_data from content agents

        Returns:
            Response based on article, resource, and live data content
        """
        live_data = live_data or {"web_results": [], "market_data": []}

        if not articles and not resources and not live_data.get("web_results") and not live_data.get("market_data"):
            # No content found, provide general response
            return self._handle_general_chat(user_query)

        # Build article content for synthesis
        articles_content = ""
        if articles:
            articles_content = "\n### Articles from Knowledge Base:\n"
            for i, article in enumerate(articles, 1):
                articles_content += f"\nArticle {i}: {article['headline']}\n"
                articles_content += f"Keywords: {article.get('keywords', 'N/A')}\n"
                articles_content += f"Content: {article['content'][:500]}...\n"
                articles_content += f"---\n"

        # Build resource content for synthesis
        resources_content = ""
        if resources:
            resources_content = "\n### Resources from Knowledge Base:\n"
            for i, resource in enumerate(resources, 1):
                resources_content += f"\nResource {i}: {resource.get('name', 'Unnamed')}"
                resources_content += f" (Type: {resource.get('type', 'unknown')})\n"
                resources_content += f"Relevance: {resource.get('similarity_score', 0):.2f}\n"
                preview = resource.get('content_preview', '')[:400]
                resources_content += f"Content: {preview}...\n"
                resources_content += f"---\n"

        # Build live data content for synthesis
        live_data_content = ""
        web_results = live_data.get("web_results", [])
        market_data = live_data.get("market_data", [])

        if web_results:
            live_data_content += "\n### Latest News (Live Web Search):\n"
            for i, news in enumerate(web_results[:5], 1):
                live_data_content += f"\nNews {i}: {news.get('title', 'N/A')}\n"
                live_data_content += f"Source: {news.get('source', 'N/A')} | Date: {news.get('date', 'N/A')}\n"
                live_data_content += f"Summary: {news.get('snippet', '')[:300]}\n"
                live_data_content += f"---\n"

        if market_data:
            live_data_content += "\n### Live Market Data:\n"
            for data in market_data:
                info = data.get("info", {})
                live_data_content += f"\n**{data.get('symbol')}** - {info.get('name', 'N/A')}\n"
                live_data_content += f"Sector: {info.get('sector', 'N/A')} | Industry: {info.get('industry', 'N/A')}\n"
                if info.get('market_cap'):
                    live_data_content += f"Market Cap: ${info.get('market_cap', 0):,.0f}\n"
                if info.get('pe_ratio'):
                    live_data_content += f"P/E Ratio: {info.get('pe_ratio', 'N/A'):.2f}\n"
                if info.get('dividend_yield'):
                    live_data_content += f"Dividend Yield: {info.get('dividend_yield', 0)*100:.2f}%\n"
                if info.get('52_week_high') and info.get('52_week_low'):
                    live_data_content += f"52-Week Range: ${info.get('52_week_low', 0):.2f} - ${info.get('52_week_high', 0):.2f}\n"
                live_data_content += f"---\n"

        # Get user name for personalization
        user_name = self.user_context.get("name", "") if self.user_context else ""
        personalization = f"Address the user as {user_name}. " if user_name else ""

        # Check if this looks like an article creation request that wasn't caught by content generation detection
        query_lower = user_query.lower()
        article_creation_keywords = [
            "write an article", "write a article", "write article",
            "create an article", "create a article", "create article",
            "write me an article", "write me a article",
            "write a market", "write an analysis", "write a report",
            "generate an article", "generate article", "generate a article",
            "draft an article", "draft a article", "produce an article",
        ]
        if any(kw in query_lower for kw in article_creation_keywords):
            # This is an article creation request - don't synthesize, guide user instead
            topic_display = agent_type.replace("_", " ").title()
            return f"""It sounds like you want to create an article about {topic_display}.

To generate article content, you have two options:

1. **Navigate to the Analyst Hub**: Say "go to {agent_type} analyst" or click on the {topic_display} analyst section. From there you can create new articles.

2. **Be more specific**: Once in the analyst editor, you can ask me to "write an article about [specific topic]" and I'll generate the content for you.

Would you like me to navigate you to the {topic_display} analyst hub?"""

        synthesis_prompt = f"""You are a helpful financial assistant. A user has asked a question related to {agent_type} research.

Your task: Use the following content to provide a direct, specific answer to the user's question. Be conversational and helpful. {personalization}

User's Question: {user_query}

{articles_content}
{resources_content}
{live_data_content}

Instructions:
1. Directly answer the user's specific question using information from ALL available sources
2. Prioritize live market data and news when available for current/recent questions
3. Use knowledge base articles for background context and analysis
4. Be concise but informative
5. Maintain a helpful, conversational tone
6. Prioritize information from higher relevance resources and more recent articles
7. If resources contain data (tables, statistics), incorporate that data into your response
8. Do NOT include article/resource references or links in your response - they will be added automatically
9. Focus on synthesizing information to answer the question
10. IMPORTANT: If the user asks you to "write", "create", "generate", or "draft" an article or report, do NOT write it. Instead, tell them to use the Analyst Hub to create articles.

Provide your response:"""

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=synthesis_prompt)
        ]

        try:
            response = self.llm.invoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"Error in synthesis: {e}")
            return "I apologize, but I encountered an error processing your question. Please try again."

    def _route_query(self, query: str) -> Dict[str, str]:
        """
        Route query to appropriate content agent or handle as general chat.

        Args:
            query: User query

        Returns:
            Dict with 'agent' and 'reason'
        """
        routing_prompt = """Analyze the user's question and determine which specialist should handle it.

Route to specialists for ANY questions about these topics:

- MACRO: Macroeconomics, economic indicators, GDP, inflation, unemployment, FX markets, currency, central banks, monetary policy, Federal Reserve, ECB, interest rates, economic outlook
- EQUITY: Stocks, shares, equities, company stock analysis, stock markets, stock performance, stock prices, stock valuation, IPOs, specific companies (e.g., Tesla, Apple, NVIDIA), market indices, S&P 500, NASDAQ
- FIXED_INCOME: Bonds, bond yields, bond markets, credit markets, corporate bonds, government bonds, treasuries, credit spreads, debt securities, fixed income investments
- ESG: Environmental, social, governance factors, sustainability, climate risk, ESG ratings, sustainable investing, green bonds, corporate responsibility

- GENERAL: Only for greetings, non-financial questions, questions about the assistant's capabilities, and topics unrelated to investing/finance

IMPORTANT ROUTING RULES:
1. ANY question about stocks, bonds, or economics → route to appropriate specialist
2. Questions about specific companies → EQUITY
3. Questions about interest rates, inflation, economic policy → MACRO
4. Questions about debt markets, yields → FIXED_INCOME
5. Questions about sustainability in investing → ESG
6. Only use GENERAL for non-financial conversations

Examples:
- "Hello" → GENERAL
- "What can you do?" → GENERAL
- "What are interest rates doing?" → MACRO (economic/monetary policy topic)
- "Tell me about Tesla" → EQUITY (company/stock topic)
- "How is Tesla stock doing?" → EQUITY (stock performance)
- "Explain what a bond is" → FIXED_INCOME (bond topic, even educational)
- "What are bond yields today?" → FIXED_INCOME (bond market data)
- "How's the economy?" → MACRO (economic question)
- "Should I invest in tech stocks?" → EQUITY (stock investing)
- "What's happening with inflation?" → MACRO (economic indicator)

Respond with JSON: {"agent": "general|macro|equity|fixed_income|esg", "reason": "brief explanation"}"""

        messages = [
            SystemMessage(content=routing_prompt),
            HumanMessage(content=f"Route this query: {query}")
        ]

        # Use JSON mode for structured output
        llm_with_json = self.llm.bind(response_format={"type": "json_object"})

        try:
            response = llm_with_json.invoke(messages)
            routing_data = json.loads(response.content)

            agent = routing_data.get('agent', 'general').lower()
            reason = routing_data.get('reason', 'General conversation')

            # Validate agent
            valid_agents = ['general', 'macro', 'equity', 'fixed_income', 'esg']
            if agent not in valid_agents:
                agent = 'general'
                reason = f"Default routing (invalid selection)"

            return {'agent': agent, 'reason': reason}

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Routing JSON parsing error: {e}")
            return {'agent': 'general', 'reason': 'Default routing (parsing error)'}

    def _generate_headline_from_content(self, content: str, topic: str) -> str:
        """
        Generate a headline from article content.

        Args:
            content: Article content in markdown
            topic: Topic slug

        Returns:
            Generated headline
        """
        try:
            # Use the first 1000 chars of content for context
            content_preview = content[:1000] if content else ""

            prompt = f"""Based on the following article content, generate a concise, professional headline.
The headline should:
- Be clear and informative
- Be 60-100 characters long
- Capture the main topic and key insight
- Be suitable for a financial research article

Topic: {topic}

Article content preview:
{content_preview}

Generate only the headline, no quotes or extra formatting:"""

            messages = [
                SystemMessage(content="You are a financial editor creating article headlines."),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            headline = response.content.strip().strip('"\'')
            return headline[:120] if len(headline) > 120 else headline

        except Exception as e:
            logger.warning(f"Failed to generate headline: {e}")
            return f"{topic.replace('_', ' ').title()} Analysis"

    def _generate_keywords_from_content(self, content: str, topic: str) -> str:
        """
        Generate keywords from article content.

        Args:
            content: Article content in markdown
            topic: Topic slug

        Returns:
            Comma-separated keywords
        """
        try:
            # Use the first 2000 chars of content for context
            content_preview = content[:2000] if content else ""

            prompt = f"""Based on the following article content, generate relevant keywords for search and categorization.
The keywords should:
- Be 5-10 keywords, comma-separated
- Include key companies, concepts, and themes mentioned
- Be relevant for financial research
- Include specific terms (stock symbols, economic indicators, etc.)

Topic: {topic}

Article content preview:
{content_preview}

Generate only the comma-separated keywords, no extra text:"""

            messages = [
                SystemMessage(content="You are a financial analyst tagging articles for search."),
                HumanMessage(content=prompt)
            ]

            response = self.llm.invoke(messages)
            keywords = response.content.strip()
            # Clean up any extra formatting
            keywords = keywords.replace('"', '').replace("'", "")
            return keywords[:200] if len(keywords) > 200 else keywords

        except Exception as e:
            logger.warning(f"Failed to generate keywords: {e}")
            return topic.replace('_', ' ')

    # ==========================================================================
    # NEW LANGGRAPH-BASED CHAT METHOD (v2)
    # ==========================================================================

    def chat_v2(
        self,
        user_message: str,
        navigation_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process user message through the new LangGraph-based workflow.

        This is the new chat method that uses a proper LangGraph StateGraph
        for routing and delegation. It replaces the procedural if-else chain
        in chat() with a structured graph-based approach.

        Features:
        - LangGraph StateGraph with explicit nodes and edges
        - Intent-based routing to specialized handlers
        - Topic-based permission enforcement from JWT scopes
        - HITL support with checkpointing
        - Dynamic topics from database

        Args:
            user_message: User's message
            navigation_context: Optional dict with section, topic, article_id, etc.

        Returns:
            Dict with 'response', 'agent_type', 'routing_reason', 'articles',
            and optional 'ui_action', 'navigation', 'editor_content', 'confirmation'
        """
        import time
        from agents.main_graph import MainChatGraph
        from agents.permission_utils import build_permission_context_for_prompt

        start_time = time.time()

        # Log request
        user_name = self.user_context.get("name", "Anonymous") if self.user_context else "Anonymous"
        logger.info("=" * 80)
        logger.info(f"🤖 MAIN CHAT AGENT (v2/LangGraph): New message")
        logger.info(f"   User: {user_name}")
        if navigation_context:
            logger.info(f"   Nav: section={navigation_context.get('section')}, "
                       f"topic={navigation_context.get('topic')}, "
                       f"role={navigation_context.get('role')}")
        logger.info(f"   Query: '{user_message[:100]}{'...' if len(user_message) > 100 else ''}'")

        try:
            # Convert navigation_context dict to NavigationContext if provided
            nav_ctx = None
            if navigation_context:
                nav_ctx = create_navigation_context(
                    section=navigation_context.get("section", "home"),
                    role=navigation_context.get("role", "reader"),
                    topic=navigation_context.get("topic"),
                    article_id=navigation_context.get("article_id"),
                    article_headline=navigation_context.get("article_headline"),
                    article_keywords=navigation_context.get("article_keywords"),
                    article_status=navigation_context.get("article_status"),
                    sub_nav=navigation_context.get("sub_nav"),
                    view_mode=navigation_context.get("view_mode"),
                    resource_id=navigation_context.get("resource_id"),
                    resource_name=navigation_context.get("resource_name"),
                    resource_type=navigation_context.get("resource_type"),
                    admin_view=navigation_context.get("admin_view"),
                )

            # Build user context if not already present
            if not self.user_context:
                logger.warning("⚠️ No user_context available, using defaults")
                user_ctx = create_user_context(
                    user_id=self.user_id,
                    email="unknown@example.com",
                    name="Unknown",
                    scopes=[]
                )
            else:
                user_ctx = self.user_context

            # Create the graph and invoke
            graph = MainChatGraph(
                user_context=user_ctx,
                enable_hitl=True
            )

            # Generate thread ID for conversation continuity
            thread_id = f"chat_{self.user_id}"

            # Invoke the graph
            response = graph.invoke(
                message=user_message,
                navigation_context=nav_ctx,
                thread_id=thread_id
            )

            # Handle None response (shouldn't happen but safety check)
            if response is None:
                logger.error("Graph returned None response - this shouldn't happen")
                response = {
                    "response": "I apologize, but I encountered an unexpected error.",
                    "agent_type": "error",
                    "routing_reason": "Graph returned None"
                }

            # Log completion
            total_time = time.time() - start_time
            logger.info(f"✓ LANGGRAPH RESPONSE: agent={response.get('agent_type', 'unknown')}, {total_time:.2f}s")
            logger.info("=" * 80)

            return response

        except Exception as e:
            logger.exception(f"❌ LangGraph chat_v2 failed: {e}")
            total_time = time.time() - start_time
            logger.info(f"⏱️  FAILED after {total_time:.2f}s")
            logger.info("=" * 80)

            return {
                "response": f"I apologize, but I encountered an error processing your request: {str(e)}",
                "agent_type": "error",
                "routing_reason": f"Error: {str(e)}",
                "articles": []
            }

    async def achat_v2(
        self,
        user_message: str,
        navigation_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Async version of chat_v2 for FastAPI endpoints.

        Args:
            user_message: User's message
            navigation_context: Optional navigation context

        Returns:
            Response dict
        """
        import time
        from agents.main_graph import MainChatGraph

        start_time = time.time()

        try:
            # Convert navigation_context dict to NavigationContext if provided
            nav_ctx = None
            if navigation_context:
                nav_ctx = create_navigation_context(
                    section=navigation_context.get("section", "home"),
                    role=navigation_context.get("role", "reader"),
                    topic=navigation_context.get("topic"),
                    article_id=navigation_context.get("article_id"),
                    article_headline=navigation_context.get("article_headline"),
                    article_keywords=navigation_context.get("article_keywords"),
                    article_status=navigation_context.get("article_status"),
                    sub_nav=navigation_context.get("sub_nav"),
                    view_mode=navigation_context.get("view_mode"),
                )

            # Build user context
            user_ctx = self.user_context or create_user_context(
                user_id=self.user_id,
                email="unknown@example.com",
                name="Unknown",
                scopes=[]
            )

            # Create graph and invoke asynchronously
            graph = MainChatGraph(
                user_context=user_ctx,
                enable_hitl=True
            )

            thread_id = f"chat_{self.user_id}"

            response = await graph.ainvoke(
                message=user_message,
                navigation_context=nav_ctx,
                thread_id=thread_id
            )

            total_time = time.time() - start_time
            logger.info(f"✓ ASYNC LANGGRAPH RESPONSE: {total_time:.2f}s")

            return response

        except Exception as e:
            logger.exception(f"❌ Async LangGraph chat_v2 failed: {e}")
            return {
                "response": f"Error: {str(e)}",
                "agent_type": "error",
                "routing_reason": f"Error: {str(e)}",
                "articles": []
            }

    def chat_auto(
        self,
        user_message: str,
        navigation_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Automatically choose between chat() and chat_v2() based on feature flag.

        This method provides a migration path - when USE_LANGGRAPH_CHAT is True,
        it uses the new LangGraph-based workflow. Otherwise, it uses the legacy
        procedural approach.

        Args:
            user_message: User's message
            navigation_context: Optional navigation context

        Returns:
            Response dict
        """
        if USE_LANGGRAPH_CHAT:
            logger.info("🔄 Using LangGraph chat (v2)")
            return self.chat_v2(user_message, navigation_context)
        else:
            logger.info("🔄 Using legacy chat (v1)")
            return self.chat(user_message, navigation_context)

