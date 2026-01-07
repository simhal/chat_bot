"""
Router node for the main chat graph.

This node classifies user intent and determines which handler node should
process the request. It uses keyword-based classification to route messages
to navigation, UI action, content generation, editor workflow, general chat,
or entitlements nodes.

Navigation Logic:
- "switch to {topic}" - Changes topic within current role section (UI action)
- "go to {topic}" - Navigates to READER section of that topic
- "go to {section}" - Navigates to specific section (analyst, editor, admin)
- Action commands with topic - Navigate to appropriate role section first

Examples:
- "switch to equity" -> UI action to change topic dropdown (stays in current section)
- "go to macro" -> Navigate to /reader/macro
- "go to analyst" -> Navigate to /analyst/{current_topic}
- "write a new equity article" -> Navigate to /analyst/equity + content generation
- "review macro articles" -> Navigate to /editor/macro + editor workflow
"""

from typing import Dict, Any, Optional
import logging

from agents.state import AgentState, IntentClassification, IntentType

logger = logging.getLogger(__name__)


# Topic slugs - these should match database topics
# Used to detect topic mentions in messages
KNOWN_TOPICS = {
    "macro", "equity", "fixed_income", "fixed-income", "esg", "technical"
}

# Topic aliases for natural language matching
TOPIC_ALIASES = {
    "macro": ["macro", "macroeconomic", "economy", "economics"],
    "equity": ["equity", "equities", "stock", "stocks"],
    "fixed_income": ["fixed income", "fixed-income", "bonds", "credit", "debt"],
    "esg": ["esg", "sustainability", "environmental", "climate"],
    "technical": ["technical", "tech", "charts", "technical analysis"]
}

# Section/role keywords (for explicit section navigation)
# Topic navigation without explicit section goes to home page with topic selected
SECTION_KEYWORDS = {
    "analyst": ["analyst hub", "analyst section", "my drafts", "my articles", "write article"],
    "editor": ["editor hub", "editor section", "editorial", "pending articles", "review article"],
    "admin": ["admin panel", "admin section", "admin dashboard"],
    "admin_content": ["content management", "manage content", "admin content"],
    "admin_global": ["global admin", "system admin", "global settings"]
}


def router_node(state: AgentState) -> Dict[str, Any]:
    """
    Classify user intent and route to appropriate handler node.

    Routing priority:
    1. Action commands (write, review, approve) -> content_generation or editor_workflow
    2. "switch to" commands -> ui_action (topic/tab change within section)
    3. Navigation commands (go to, navigate to) -> navigation
    4. Entitlement queries -> entitlements
    5. Context-based routing -> based on current section
    6. Default -> general_chat
    """
    messages = state.get("messages", [])
    if not messages:
        return {
            "intent": IntentClassification(
                intent_type="general_chat",
                confidence=0.0,
                details={"reason": "No messages provided"}
            ),
            "routing_reason": "No messages to process"
        }

    # Get the last user message
    last_message = messages[-1]
    user_message = last_message.content if hasattr(last_message, 'content') else str(last_message)
    message_lower = user_message.lower()

    # Get navigation context
    nav_context = state.get("navigation_context") or {}
    current_section = nav_context.get("section", "home")
    current_role = nav_context.get("role", "reader")
    current_topic = nav_context.get("topic")
    article_id = nav_context.get("article_id")

    # Extract topic from message if mentioned
    mentioned_topic = _extract_topic_from_message(message_lower)

    # 1. Check for ACTION commands first (these may require navigation + action)
    action_intent = _check_action_commands(
        message_lower, mentioned_topic, current_topic, current_section, current_role, article_id
    )
    if action_intent:
        logger.info(f"Router: Action command detected: {action_intent['intent_type']}")
        return {
            "intent": action_intent,
            "routing_reason": action_intent["details"].get("reason", "Action command")
        }

    # 2. Check for "switch to" commands (UI action - stay in current section)
    if "switch to" in message_lower or "change to" in message_lower:
        intent = _handle_switch_command(message_lower, mentioned_topic, current_section)
        if intent:
            logger.info(f"Router: Switch command -> ui_action")
            return {
                "intent": intent,
                "routing_reason": intent["details"].get("reason", "Switch command")
            }

    # 3. Check for navigation commands
    nav_intent = _check_navigation_commands(
        message_lower, mentioned_topic, current_topic, current_section
    )
    if nav_intent:
        logger.info(f"Router: Navigation command detected")
        return {
            "intent": nav_intent,
            "routing_reason": nav_intent["details"].get("reason", "Navigation command")
        }

    # 4. Check for entitlement queries
    entitlement_keywords = [
        "what can i do", "my permissions", "what am i allowed",
        "my role", "my access", "what actions", "entitled"
    ]
    if any(kw in message_lower for kw in entitlement_keywords):
        return {
            "intent": IntentClassification(
                intent_type="entitlements",
                confidence=0.9,
                details={"reason": "Entitlement query detected"}
            ),
            "routing_reason": "Entitlement query"
        }

    # 5. Context-based routing
    context_intent = _classify_by_context(
        message_lower, current_section, current_role, current_topic, article_id
    )
    if context_intent:
        logger.info(f"Router: Context-based routing to {context_intent['intent_type']}")
        return {
            "intent": context_intent,
            "routing_reason": context_intent["details"].get("reason", "Context-based")
        }

    # 6. Default to general chat
    logger.info(f"Router: Defaulting to general_chat")
    return {
        "intent": IntentClassification(
            intent_type="general_chat",
            confidence=0.5,
            details={
                "reason": "No specific intent detected",
                "topic": mentioned_topic or current_topic
            }
        ),
        "routing_reason": "Default to general chat"
    }


def _extract_topic_from_message(message: str) -> Optional[str]:
    """Extract topic slug from message using aliases."""
    for topic_slug, aliases in TOPIC_ALIASES.items():
        if any(alias in message for alias in aliases):
            # Normalize to underscore format
            return topic_slug.replace("-", "_")
    return None


def _check_action_commands(
    message: str,
    mentioned_topic: Optional[str],
    current_topic: Optional[str],
    current_section: str,
    current_role: str,
    article_id: Optional[int]
) -> Optional[IntentClassification]:
    """
    Check for action commands that may require navigation + action.

    Examples:
    - "write a new equity article" -> analyst section + content_generation
    - "review macro articles" -> editor section + editor_workflow
    - "approve this article" -> editor_workflow (if already in editor section)
    """
    topic = mentioned_topic or current_topic

    # Content generation keywords (requires analyst role)
    content_keywords = ["write", "draft", "compose", "create article", "new article", "author"]
    if any(kw in message for kw in content_keywords):
        return IntentClassification(
            intent_type="content_generation",
            confidence=0.9,
            details={
                "reason": "Content generation command detected",
                "topic": topic,
                "article_id": article_id,
                "requires_section": "analyst",
                "navigate_first": current_section != "analyst"
            }
        )

    # Editor workflow keywords (requires editor role)
    editor_keywords = ["review", "approve", "reject", "publish", "send back", "pending"]
    if any(kw in message for kw in editor_keywords):
        # Determine action
        action = "review"
        if any(w in message for w in ["approve", "publish", "accept"]):
            action = "approve"
        elif any(w in message for w in ["reject", "decline", "send back"]):
            action = "reject"
        elif any(w in message for w in ["pending", "queue", "list"]):
            action = "list_pending"

        return IntentClassification(
            intent_type="editor_workflow",
            confidence=0.9,
            details={
                "reason": f"Editor workflow command detected: {action}",
                "action": action,
                "topic": topic,
                "article_id": article_id,
                "requires_section": "editor",
                "navigate_first": current_section != "editor"
            }
        )

    return None


def _handle_switch_command(
    message: str,
    mentioned_topic: Optional[str],
    current_section: str
) -> Optional[IntentClassification]:
    """
    Handle "switch to" commands - changes topic/tab within current section.

    "switch to equity" -> Change topic dropdown to equity (stay in current section)
    "switch to preview" -> Change view tab to preview
    """
    # If a topic is mentioned, switch to that topic
    if mentioned_topic:
        return IntentClassification(
            intent_type="ui_action",
            confidence=0.9,
            details={
                "reason": f"Switch topic to {mentioned_topic} within {current_section}",
                "action_type": "switch_topic",
                "topic": mentioned_topic,
                "stay_in_section": current_section
            }
        )

    # Check for view/tab switches
    if "preview" in message:
        return IntentClassification(
            intent_type="ui_action",
            confidence=0.9,
            details={
                "reason": "Switch to preview view",
                "action_type": "switch_view_preview"
            }
        )
    if "edit" in message or "editor" in message:
        return IntentClassification(
            intent_type="ui_action",
            confidence=0.9,
            details={
                "reason": "Switch to editor view",
                "action_type": "switch_view_editor"
            }
        )
    if "resource" in message:
        return IntentClassification(
            intent_type="ui_action",
            confidence=0.9,
            details={
                "reason": "Switch to resources view",
                "action_type": "switch_view_resources"
            }
        )

    return None


def _check_navigation_commands(
    message: str,
    mentioned_topic: Optional[str],
    current_topic: Optional[str],
    current_section: str
) -> Optional[IntentClassification]:
    """
    Check for navigation commands.

    Navigation keywords: go to, navigate to, take me to, open, show me

    Routes (matching SvelteKit frontend):
    - "go to {topic}" -> Navigate to / (home) with topic param
    - "go to analyst hub" -> Navigate to /analyst/{topic}
    - "go to editor hub" -> Navigate to /editor/{topic}
    - "go to admin" -> Navigate to /admin
    - "go to admin content" -> Navigate to /admin/content
    - "go to global admin" -> Navigate to /admin/global
    - "go to profile" -> Navigate to /profile
    - "go to home" -> Navigate to /
    """
    nav_keywords = ["go to", "got to", "navigate to", "navigat to", "take me to",
                    "open", "show me", "bring me to", "head to"]

    if not any(kw in message for kw in nav_keywords):
        return None

    topic = mentioned_topic or current_topic

    # === Admin Routes (check specific ones first) ===
    # Global admin
    if "global admin" in message or "system admin" in message or "admin global" in message:
        return IntentClassification(
            intent_type="navigation",
            confidence=0.95,
            details={
                "reason": "Navigate to global admin",
                "target": "admin_global",
                "route": "/admin/global"
            }
        )

    # Admin content
    if "content management" in message or "manage content" in message or "admin content" in message:
        return IntentClassification(
            intent_type="navigation",
            confidence=0.95,
            details={
                "reason": "Navigate to content management",
                "target": "admin_content",
                "route": "/admin/content"
            }
        )

    # Admin dashboard (generic admin)
    if "admin" in message and not any(x in message for x in ["global", "content"]):
        return IntentClassification(
            intent_type="navigation",
            confidence=0.9,
            details={
                "reason": "Navigate to admin dashboard",
                "target": "admin",
                "route": "/admin"
            }
        )

    # === User Routes ===
    # Home
    if "home" in message or "front page" in message or "main page" in message:
        return IntentClassification(
            intent_type="navigation",
            confidence=0.95,
            details={
                "reason": "Navigate to home",
                "target": "home",
                "route": "/"
            }
        )

    # Profile
    if "profile" in message or "my account" in message or "account settings" in message:
        return IntentClassification(
            intent_type="navigation",
            confidence=0.95,
            details={
                "reason": "Navigate to profile",
                "target": "profile",
                "route": "/profile"
            }
        )

    # === Role-based Section Navigation ===
    # Analyst hub
    if any(kw in message for kw in SECTION_KEYWORDS["analyst"]):
        if topic:
            return IntentClassification(
                intent_type="navigation",
                confidence=0.9,
                details={
                    "reason": f"Navigate to analyst hub for {topic}",
                    "target": "analyst",
                    "topic": topic,
                    "route": f"/analyst/{topic}"
                }
            )
        else:
            return IntentClassification(
                intent_type="navigation",
                confidence=0.85,
                details={
                    "reason": "Navigate to analyst hub (no topic specified)",
                    "target": "analyst",
                    "route": "/analyst"
                }
            )

    # Editor hub
    if any(kw in message for kw in SECTION_KEYWORDS["editor"]):
        if topic:
            return IntentClassification(
                intent_type="navigation",
                confidence=0.9,
                details={
                    "reason": f"Navigate to editor hub for {topic}",
                    "target": "editor",
                    "topic": topic,
                    "route": f"/editor/{topic}"
                }
            )
        else:
            return IntentClassification(
                intent_type="navigation",
                confidence=0.85,
                details={
                    "reason": "Navigate to editor hub (no topic specified)",
                    "target": "editor",
                    "route": "/editor"
                }
            )

    # === Topic Navigation (goes to home with topic) ===
    # "go to equity" -> / with topic=equity (home page will select the topic)
    if mentioned_topic:
        return IntentClassification(
            intent_type="navigation",
            confidence=0.9,
            details={
                "reason": f"Navigate to home with {mentioned_topic} topic",
                "target": "home",
                "topic": mentioned_topic,
                "route": "/",
                "params": {"topic": mentioned_topic}
            }
        )

    # Fallback - navigate to home
    return IntentClassification(
        intent_type="navigation",
        confidence=0.6,
        details={
            "reason": "Navigation intent detected, going to home",
            "target": "home",
            "route": "/"
        }
    )


def _classify_by_context(
    message: str,
    section: str,
    role: str,
    topic: Optional[str],
    article_id: Optional[int]
) -> Optional[IntentClassification]:
    """
    Context-aware classification based on current section and role.
    """
    # In analyst section with article context - likely content related
    if section == "analyst" and article_id:
        content_hints = ["help", "improve", "edit", "change", "update", "modify", "suggest"]
        if any(hint in message for hint in content_hints):
            return IntentClassification(
                intent_type="content_generation",
                confidence=0.7,
                details={
                    "reason": "In analyst context with article, detected editing intent",
                    "topic": topic,
                    "article_id": article_id
                }
            )

    # In editor section - likely editorial action
    if section == "editor":
        editor_hints = ["article", "this", "it", "status"]
        if any(hint in message for hint in editor_hints):
            return IntentClassification(
                intent_type="editor_workflow",
                confidence=0.7,
                details={
                    "reason": "In editor context, detected editorial intent",
                    "topic": topic,
                    "article_id": article_id,
                    "action": "review"
                }
            )

    # In admin section - could be admin actions
    if section == "admin":
        admin_hints = ["delete", "remove", "deactivate", "recall", "purge"]
        if any(hint in message for hint in admin_hints):
            return IntentClassification(
                intent_type="ui_action",
                confidence=0.7,
                details={
                    "reason": "In admin context, detected admin action",
                    "action_type": "admin_action"
                }
            )

    return None


def route_by_intent(state: AgentState) -> str:
    """
    Conditional edge function for LangGraph routing.

    Returns the name of the node to route to based on intent classification.
    """
    intent = state.get("intent")

    if not intent:
        logger.warning("Router: No intent in state, defaulting to general_chat")
        return "general_chat"

    intent_type = intent.get("intent_type", "general_chat")

    # Map intent types to node names
    route_map: Dict[IntentType, str] = {
        "navigation": "navigation",
        "ui_action": "ui_action",
        "content_generation": "content_generation",
        "editor_workflow": "editor_workflow",
        "general_chat": "general_chat",
        "entitlements": "entitlements",
    }

    node_name = route_map.get(intent_type, "general_chat")
    logger.info(f"Router: Routing to node '{node_name}' for intent '{intent_type}'")

    return node_name
