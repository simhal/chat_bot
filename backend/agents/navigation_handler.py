"""Navigation and UI action handling for the main chat agent."""

from typing import Dict, Optional, List, Any
import logging
import re

logger = logging.getLogger("uvicorn")

# UI Action types that can be triggered by the chatbot
UI_ACTION_TYPES = [
    # Analyst Edit Page Actions
    'save_draft',
    'submit_for_review',
    'switch_view_editor',
    'switch_view_preview',
    'switch_view_resources',
    # Resource Actions (for article editor)
    'add_resource',
    'remove_resource',
    'link_resource',
    'unlink_resource',
    'browse_resources',
    'open_resource_modal',
    # Analyst Hub Page Actions
    'create_new_article',
    'view_article',
    'edit_article',
    'submit_article',
    # Editor Hub Page Actions
    'reject_article',
    'publish_article',
    'download_pdf',
    # Admin Article Actions (require confirmation)
    'deactivate_article',
    'reactivate_article',
    'recall_article',
    'purge_article',
    'delete_article',
    'delete_resource',
    # Admin View Switching
    'switch_admin_view',
    'switch_admin_topic',
    'switch_admin_subview',
    # Profile Page Actions
    'switch_profile_tab',
    'save_tonality',
    'delete_account',
    # Home Page Actions
    'select_topic_tab',
    'rate_article',
    'open_article',
    'search_articles',
    'clear_search',
    # Common Actions
    'select_topic',
    'close_modal',
    'confirm_action',
    'cancel_action',
    # Context Update Actions
    'select_article',
    'select_resource',
]

# Actions that require explicit user confirmation
ACTIONS_REQUIRING_CONFIRMATION = [
    # Article destructive actions
    'purge_article',
    'delete_article',
    'deactivate_article',
    'recall_article',
    'publish_article',  # Publishing makes content public - requires confirmation
    # Resource destructive actions
    'delete_resource',
    # User/Account destructive actions
    'delete_account',
    'delete_profile',  # Alias for delete_account
    'delete_user',
    # Topic destructive actions
    'delete_topic',
]


class NavigationHandler:
    """Handles navigation intents and UI actions for the main chat agent."""

    def __init__(self, db, user_context: Optional[Dict[str, Any]] = None):
        """
        Initialize navigation handler.

        Args:
            db: Database session
            user_context: User context for permissions
        """
        self.db = db
        self.user_context = user_context
        self.navigation_context = None

    def set_navigation_context(self, context: Optional[Dict[str, Any]]):
        """Set the current navigation context."""
        self.navigation_context = context

    def detect_navigation_intent(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect if the user wants to navigate somewhere in the app.

        Args:
            message: User message

        Returns:
            Navigation intent dict or None if no navigation intent detected
        """
        message_lower = message.lower()
        nav_context = self.navigation_context or {}
        current_topic = nav_context.get('topic')

        logger.info(f"🔍 NAVIGATION DETECTION: message='{message_lower[:50]}...'")
        if current_topic:
            logger.info(f"   Context: section={nav_context.get('section')}, topic={current_topic}")

        # Build navigation patterns
        navigation_patterns = [
            # Logout
            {
                "keywords": ["logout", "log out", "sign out", "sign off", "log me out"],
                "action": "logout",
                "target": None,
                "params": None,
                "requires_scope": None,
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

    def check_navigation_authorization(self, nav_intent: Dict[str, Any]) -> tuple[bool, str]:
        """
        Check if user is authorized for the navigation.

        Args:
            nav_intent: Navigation intent from detect_navigation_intent

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

    def handle_navigation_intent(self, nav_intent: Dict[str, Any], user_message: str) -> Dict[str, Any]:
        """
        Handle a navigation intent with authorization check.

        Args:
            nav_intent: Navigation intent from detect_navigation_intent
            user_message: Original user message

        Returns:
            Response dict with navigation command if authorized
        """
        is_authorized, denial_reason = self.check_navigation_authorization(nav_intent)

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
            if "/admin/global" in target:
                response = f"Here's the Global Admin Panel where you can manage users, groups, and system settings:\n\n[Go to Global Admin](goto:{target})"
            else:
                response = f"Here's the Topic Admin Panel where you can manage articles and content:\n\n[Go to Topic Admin](goto:{target})"
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

    def detect_ui_action_intent(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect if the user wants to perform a UI action (button click, tab selection, etc.).

        Args:
            message: User message

        Returns:
            UI action intent dict or None if no UI action detected
        """
        nav_context = self.navigation_context or {}
        current_section = nav_context.get('section', 'home')
        current_topic = nav_context.get('topic')
        article_id = nav_context.get('article_id')
        current_role = nav_context.get('role', 'reader')

        message_lower = message.lower()

        # Map natural language to UI actions based on current context

        # Profile page actions
        if current_section == 'profile':
            if any(kw in message_lower for kw in ["tonality", "custom prompt", "writing style", "my preferences"]):
                return {
                    "action_type": "switch_profile_tab",
                    "params": {"tab": "tonality"},
                    "description": "Switch to tonality settings",
                }
            if any(kw in message_lower for kw in ["save my", "save tonality", "save preferences", "update preferences"]):
                return {
                    "action_type": "save_tonality",
                    "params": {},
                    "description": "Save tonality preferences",
                }
            if any(kw in message_lower for kw in ["delete my account", "delete account", "remove my account"]):
                return {
                    "action_type": "delete_account",
                    "params": {},
                    "description": "Delete user account",
                    "requires_confirmation": True,
                }

        # Admin page actions
        if current_section == 'admin':
            # View switching
            if any(kw in message_lower for kw in ["show articles", "view articles", "article list", "articles view"]):
                return {
                    "action_type": "switch_admin_view",
                    "params": {"view": "articles"},
                    "description": "Switch to articles view",
                }
            if any(kw in message_lower for kw in ["show resources", "view resources", "resource list", "resources view"]):
                return {
                    "action_type": "switch_admin_view",
                    "params": {"view": "resources"},
                    "description": "Switch to resources view",
                }

            # Topic switching
            topics = self._get_available_topics()
            for topic in topics:
                topic_display = topic.replace("_", " ")
                if topic_display in message_lower or topic in message_lower:
                    return {
                        "action_type": "switch_admin_topic",
                        "params": {"topic": topic},
                        "description": f"Switch to {topic_display} topic",
                    }

            # Article actions
            article_id_match = self._extract_article_id(message)
            if article_id_match:
                if any(kw in message_lower for kw in ["deactivate", "disable", "hide"]):
                    return {
                        "action_type": "deactivate_article",
                        "params": {"article_id": article_id_match},
                        "description": f"Deactivate article #{article_id_match}",
                        "requires_confirmation": True,
                    }
                if any(kw in message_lower for kw in ["reactivate", "enable", "unhide", "restore"]):
                    return {
                        "action_type": "reactivate_article",
                        "params": {"article_id": article_id_match},
                        "description": f"Reactivate article #{article_id_match}",
                    }
                if any(kw in message_lower for kw in ["recall", "unpublish"]):
                    return {
                        "action_type": "recall_article",
                        "params": {"article_id": article_id_match},
                        "description": f"Recall article #{article_id_match}",
                        "requires_confirmation": True,
                    }
                if any(kw in message_lower for kw in ["purge", "permanently delete"]):
                    return {
                        "action_type": "purge_article",
                        "params": {"article_id": article_id_match},
                        "description": f"Permanently delete article #{article_id_match}",
                        "requires_confirmation": True,
                    }
                if any(kw in message_lower for kw in ["delete article", "remove article"]):
                    return {
                        "action_type": "delete_article",
                        "params": {"article_id": article_id_match},
                        "description": f"Delete article #{article_id_match}",
                        "requires_confirmation": True,
                    }

            # Resource actions
            resource_id_match = self._extract_resource_id(message)
            if resource_id_match and any(kw in message_lower for kw in ["delete resource", "remove resource"]):
                return {
                    "action_type": "delete_resource",
                    "params": {"resource_id": resource_id_match},
                    "description": f"Delete resource #{resource_id_match}",
                    "requires_confirmation": True,
                }

        # Analyst page actions
        if current_section == 'analyst':
            can_edit = current_role in ['analyst', 'admin']

            # Article editing context
            if article_id and can_edit:
                # View switching
                if any(kw in message_lower for kw in ["editor view", "edit mode", "write mode", "editor"]):
                    return {
                        "action_type": "switch_view_editor",
                        "params": {},
                        "description": "Switch to editor view",
                    }
                if any(kw in message_lower for kw in ["preview", "preview mode", "see preview"]):
                    return {
                        "action_type": "switch_view_preview",
                        "params": {},
                        "description": "Switch to preview view",
                    }
                if any(kw in message_lower for kw in ["resources", "resource view", "attachments", "files"]):
                    return {
                        "action_type": "switch_view_resources",
                        "params": {},
                        "description": "Switch to resources view",
                    }

                # Save/Submit
                if any(kw in message_lower for kw in ["save draft", "save my work", "save changes", "save article"]):
                    return {
                        "action_type": "save_draft",
                        "params": {},
                        "description": "Save article as draft",
                    }
                if any(kw in message_lower for kw in ["submit for review", "submit article", "send for review", "request review"]):
                    return {
                        "action_type": "submit_for_review",
                        "params": {},
                        "description": "Submit article for review",
                    }

                # Resource actions
                if any(kw in message_lower for kw in ["add resource", "attach resource", "upload resource"]):
                    return {
                        "action_type": "open_resource_modal",
                        "params": {},
                        "description": "Open resource upload dialog",
                    }
                if any(kw in message_lower for kw in ["browse resources", "find resources", "search resources"]):
                    return {
                        "action_type": "browse_resources",
                        "params": {},
                        "description": "Browse available resources",
                    }

            # Analyst hub (no article selected)
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

        # Editor page actions
        if current_section == 'editor':
            can_review = current_role in ['editor', 'admin']

            if article_id and can_review:
                if any(kw in message_lower for kw in ["reject", "send back", "request changes", "needs changes"]):
                    return {
                        "action_type": "reject_article",
                        "params": {"article_id": article_id},
                        "description": f"Reject article #{article_id}",
                    }
                if any(kw in message_lower for kw in ["publish", "approve", "approve article"]):
                    return {
                        "action_type": "publish_article",
                        "params": {"article_id": article_id},
                        "description": f"Publish article #{article_id}",
                        "requires_confirmation": True,
                    }
                if any(kw in message_lower for kw in ["download pdf", "get pdf", "export pdf"]):
                    return {
                        "action_type": "download_pdf",
                        "params": {"article_id": article_id},
                        "description": f"Download PDF for article #{article_id}",
                    }

        # Home page actions
        if current_section == 'home':
            # Topic tab selection
            topics = self._get_available_topics()
            for topic in topics:
                topic_display = topic.replace("_", " ")
                if f"show {topic_display}" in message_lower or f"go to {topic_display}" in message_lower:
                    return {
                        "action_type": "select_topic_tab",
                        "params": {"topic": topic},
                        "description": f"Switch to {topic_display} tab",
                    }

            # Article interactions
            article_id_match = self._extract_article_id(message)
            if article_id_match:
                if any(kw in message_lower for kw in ["open article", "view article", "read article", "show article"]):
                    return {
                        "action_type": "open_article",
                        "params": {"article_id": article_id_match},
                        "description": f"Open article #{article_id_match}",
                    }

                # Rating
                rating = self._extract_rating(message)
                if rating and any(kw in message_lower for kw in ["rate", "give", "stars"]):
                    return {
                        "action_type": "rate_article",
                        "params": {"article_id": article_id_match, "rating": rating},
                        "description": f"Rate article #{article_id_match} with {rating} stars",
                    }

            # Search
            if any(kw in message_lower for kw in ["search for", "find articles about", "look for"]):
                # Extract search query
                search_terms = message_lower
                for prefix in ["search for", "find articles about", "look for"]:
                    if prefix in search_terms:
                        search_terms = search_terms.split(prefix, 1)[1].strip()
                        break
                return {
                    "action_type": "search_articles",
                    "params": {"query": search_terms},
                    "description": f"Search for '{search_terms}'",
                }
            if any(kw in message_lower for kw in ["clear search", "reset search", "show all"]):
                return {
                    "action_type": "clear_search",
                    "params": {},
                    "description": "Clear search filter",
                }

        return None

    def _extract_article_id(self, message: str) -> Optional[int]:
        """Extract article ID from message like 'article #123' or 'article 123'."""
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

    def _extract_rating(self, message: str) -> Optional[int]:
        """Extract rating (1-5) from message."""
        patterns = [
            r"(\d)\s*stars?",
            r"rate\s*(?:it\s*)?(\d)",
            r"give\s*(?:it\s*)?(\d)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                rating = int(match.group(1))
                if 1 <= rating <= 5:
                    return rating
        return None

    def _extract_resource_id(self, message: str) -> Optional[int]:
        """Extract resource ID from message."""
        patterns = [
            r"resource\s*#?(\d+)",
            r"resource\s+id\s*:?\s*(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message.lower())
            if match:
                return int(match.group(1))
        return None

    def handle_ui_action_intent(self, action_intent: Dict[str, Any], user_message: str) -> Dict[str, Any]:
        """
        Handle a UI action intent.

        Args:
            action_intent: Action intent from detect_ui_action_intent
            user_message: Original user message

        Returns:
            Response dict with UI action
        """
        action_type = action_intent["action_type"]
        params = action_intent.get("params", {})
        description = action_intent.get("description", "")
        requires_confirmation = action_intent.get("requires_confirmation", False)

        # Check if action is in the list requiring confirmation
        if action_type in ACTIONS_REQUIRING_CONFIRMATION:
            requires_confirmation = True

        # Check permissions
        if not self._check_action_permissions(action_type, params):
            return {
                "response": f"You don't have permission to perform this action: {description}",
                "agent_type": "ui_action",
                "routing_reason": "Permission denied for UI action",
                "articles": [],
                "ui_action": None,
            }

        # If confirmation required, return confirmation request
        if requires_confirmation:
            confirmation_message = self._get_confirmation_message(action_type, params)
            import uuid
            return {
                "response": confirmation_message,
                "agent_type": "ui_action",
                "routing_reason": f"Confirmation required for {action_type}",
                "articles": [],
                "confirmation": {
                    "id": str(uuid.uuid4()),
                    "type": action_type,
                    "title": f"Confirm: {description}",
                    "message": confirmation_message,
                    "params": params,
                    "confirm_label": "Confirm",
                    "cancel_label": "Cancel",
                },
            }

        # Return action for frontend to execute
        response_message = self._get_action_response_message(action_type, params, description)

        return {
            "response": response_message,
            "agent_type": "ui_action",
            "routing_reason": f"UI action: {action_type}",
            "articles": [],
            "ui_action": {
                "action_type": action_type,
                "params": params,
                "description": description,
            },
        }

    def _check_action_permissions(self, action_type: str, params: Dict[str, Any]) -> bool:
        """Check if user has permission to perform the action."""
        if not self.user_context:
            return False

        scopes = self.user_context.get("scopes", [])
        is_admin = "global:admin" in scopes

        # Actions that require specific permissions
        if action_type in ["submit_for_review", "save_draft", "create_new_article"]:
            # Requires analyst role
            topic = params.get("topic") or (self.navigation_context or {}).get('topic')
            if is_admin:
                return True
            return f"{topic}:analyst" in scopes or any(":analyst" in s for s in scopes)

        if action_type in ["publish_article", "reject_article"]:
            # Requires editor role
            topic = params.get("topic") or (self.navigation_context or {}).get('topic')
            if is_admin:
                return True
            return f"{topic}:editor" in scopes or any(":editor" in s for s in scopes)

        if action_type in ["deactivate_article", "reactivate_article", "recall_article",
                          "purge_article", "delete_article", "delete_resource"]:
            # Requires admin role
            topic = params.get("topic") or (self.navigation_context or {}).get('topic')
            if is_admin:
                return True
            return f"{topic}:admin" in scopes

        if action_type == "delete_account":
            # User can only delete their own account
            return True

        # Most UI actions are allowed
        return True

    def _get_confirmation_message(self, action_type: str, params: Dict[str, Any]) -> str:
        """Get confirmation message for an action."""
        messages = {
            "deactivate_article": f"Are you sure you want to deactivate article #{params.get('article_id')}? It will be hidden from readers.",
            "recall_article": f"Are you sure you want to recall article #{params.get('article_id')}? It will be unpublished.",
            "purge_article": f"Are you sure you want to PERMANENTLY DELETE article #{params.get('article_id')}? This cannot be undone!",
            "delete_article": f"Are you sure you want to delete article #{params.get('article_id')}?",
            "delete_resource": f"Are you sure you want to delete resource #{params.get('resource_id')}?",
            "delete_account": "Are you sure you want to delete your account? This action cannot be undone!",
            "publish_article": f"Are you sure you want to publish article #{params.get('article_id')}? It will be visible to all readers.",
        }
        return messages.get(action_type, f"Are you sure you want to perform this action?")

    def _get_action_response_message(self, action_type: str, params: Dict[str, Any], description: str) -> str:
        """Get response message for an action."""
        nav_context = self.navigation_context or {}
        topic = nav_context.get('topic', '')
        scope_display = f" for {topic.replace('_', ' ').title()}" if topic else ""

        messages = {
            "switch_view_editor": "Switching to editor view...",
            "switch_view_preview": "Switching to preview view...",
            "switch_view_resources": "Switching to resources view...",
            "save_draft": "Saving your draft...",
            "submit_for_review": f"Submitting{scope_display} article for review...",
            "open_resource_modal": "Opening resource upload dialog...",
            "browse_resources": f"Browsing{scope_display} resources...",
            "add_resource": f"Adding{scope_display} resource to your article...",
            "remove_resource": f"Removing resource from your article...",
            "create_new_article": f"Creating a new article for you...",
            "view_article": f"Opening article #{params.get('article_id', '')}...",
            "edit_article": f"Opening article #{params.get('article_id', '')} in the editor...",
            "submit_article": f"Submitting article #{params.get('article_id', '')} for review...",
            "reject_article": f"Sending article #{params.get('article_id', '')} back for revisions...",
            "download_pdf": f"Generating PDF for article #{params.get('article_id', '')}...",
            "switch_admin_view": f"Switching to {params.get('view', 'new')} view...",
            "switch_admin_topic": f"Switching to {params.get('topic', '').replace('_', ' ').title()} topic...",
            "select_topic_tab": f"Switching to {params.get('topic', '').replace('_', ' ').title()} articles...",
            "open_article": f"Opening article #{params.get('article_id', '')}...",
            "rate_article": f"Rating article #{params.get('article_id', '')} with {params.get('rating', '')} stars...",
            "search_articles": f"Searching for '{params.get('query', '')}'...",
            "clear_search": "Clearing search filter...",
            "switch_profile_tab": f"Switching to {params.get('tab', '')} settings...",
            "save_tonality": "Saving your preferences...",
        }
        return messages.get(action_type, f"Performing action: {description}")
