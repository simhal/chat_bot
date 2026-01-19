"""
Intent Classifier for LLM-based routing.

This module provides sophisticated intent classification using LLM with
structured output. It replaces keyword-based classification in the router
node for more accurate, context-aware intent detection.

Features:
- LLM-based classification using OpenAI structured outputs
- Few-shot examples for consistent classification
- Context-aware prompts (section, topic, user roles)
- Configurable via environment variables
- Rule-based fallback if LLM fails
"""

from typing import Dict, Any, Optional, List
import logging
import os
import json

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agents.state import IntentClassification, IntentType, NavigationContext

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

USE_LLM_CLASSIFIER = os.getenv("INTENT_CLASSIFIER_USE_LLM", "true").lower() == "true"
CLASSIFIER_MODEL = os.getenv("INTENT_CLASSIFIER_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
CLASSIFIER_TEMPERATURE = float(os.getenv("INTENT_CLASSIFIER_TEMPERATURE", "0.1"))

# Singleton LLM instance for performance
_classifier_llm = None


def _get_classifier_llm() -> ChatOpenAI:
    """Get singleton LLM instance for classification."""
    global _classifier_llm
    if _classifier_llm is None:
        _classifier_llm = ChatOpenAI(
            model=CLASSIFIER_MODEL,
            temperature=CLASSIFIER_TEMPERATURE,
            api_key=os.getenv("OPENAI_API_KEY", "")
        )
        logger.info(f"Intent classifier initialized with model: {CLASSIFIER_MODEL}")
    return _classifier_llm


# =============================================================================
# Few-Shot Examples
# =============================================================================

FEW_SHOT_EXAMPLES = [
    # Navigation / UI Actions
    {
        "message": "take me to the equity section",
        "context": {"section": "home", "topic": None},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.95,
            "action": "goto_home",
            "topic": "equity",
            "reason": "User wants to navigate to equity topic on home page"
        }
    },
    {
        "message": "I want to see my analyst dashboard",
        "context": {"section": "home", "topic": "macro"},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.93,
            "action": "goto_analyst",
            "reason": "User wants to navigate to analyst hub"
        }
    },
    {
        "message": "switch to the preview tab",
        "context": {"section": "analyst", "topic": "equity"},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.92,
            "action": "switch_view_preview",
            "reason": "User wants to switch to preview view within current page"
        }
    },
    {
        "message": "show me the editor view",
        "context": {"section": "analyst", "topic": "macro"},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.91,
            "action": "switch_view_editor",
            "reason": "User wants to switch to editor view for writing"
        }
    },
    {
        "message": "I want to see the resources",
        "context": {"section": "analyst", "topic": "equity"},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.90,
            "action": "switch_view_resources",
            "reason": "User wants to view attached resources"
        }
    },
    {
        "message": "take me to the editor dashboard",
        "context": {"section": "home", "topic": "macro"},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.94,
            "action": "goto_editor",
            "reason": "User wants to navigate to editor hub"
        }
    },
    {
        "message": "go to editor",
        "context": {"section": "home", "topic": None},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.95,
            "action": "goto_editor",
            "reason": "User wants to navigate to the editor page/hub"
        }
    },
    {
        "message": "go to analyst",
        "context": {"section": "home", "topic": None},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.95,
            "action": "goto_analyst",
            "reason": "User wants to navigate to the analyst page/hub"
        }
    },
    # Edit Article
    {
        "message": "edit article #9",
        "context": {"section": "analyst", "topic": "equity"},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.95,
            "action": "edit_article",
            "article_id": 9,
            "reason": "User wants to open article #9 in the article editor"
        }
    },
    {
        "message": "open article 15 in the editor",
        "context": {"section": "analyst", "topic": "macro"},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.94,
            "action": "edit_article",
            "article_id": 15,
            "reason": "User wants to edit article #15"
        }
    },
    # Admin Navigation
    {
        "message": "take me to the macro admin",
        "context": {"section": "analyst", "topic": "macro"},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.95,
            "action": "goto_topic_admin",
            "topic": "macro",
            "reason": "User wants to navigate to topic admin dashboard"
        }
    },
    {
        "message": "go to admin",
        "context": {"section": "home", "topic": "equity"},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.94,
            "action": "goto_topic_admin",
            "topic": "equity",
            "reason": "User wants to navigate to admin dashboard"
        }
    },
    {
        "message": "manage topics",
        "context": {"section": "admin", "topic": None},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.93,
            "action": "goto_admin_global",
            "reason": "User wants to navigate to global admin for topic management"
        }
    },
    {
        "message": "go to global admin",
        "context": {"section": "home", "topic": None},
        "classification": {
            "intent_type": "ui_action",
            "confidence": 0.95,
            "action": "goto_admin_global",
            "reason": "User wants to navigate to global admin dashboard"
        }
    },

    # Content Generation
    {
        "message": "help me write something about inflation trends",
        "context": {"section": "analyst", "topic": "macro"},
        "classification": {
            "intent_type": "content_generation",
            "confidence": 0.94,
            "topic": "macro",
            "action": "create",
            "reason": "User wants to create content about a macro topic"
        }
    },
    {
        "message": "I need to draft a new article",
        "context": {"section": "analyst", "topic": "equity"},
        "classification": {
            "intent_type": "content_generation",
            "confidence": 0.91,
            "topic": "equity",
            "action": "create",
            "reason": "User wants to create new article content"
        }
    },
    # Content Editing - Regenerate parts
    {
        "message": "rephrase the title",
        "context": {"section": "analyst", "topic": "equity", "article_id": 42, "article_headline": "Market Analysis"},
        "classification": {
            "intent_type": "content_generation",
            "confidence": 0.95,
            "action": "regenerate_headline",
            "article_id": 42,
            "reason": "User wants to rephrase/regenerate the headline from existing content"
        }
    },
    {
        "message": "generate new keywords from the content",
        "context": {"section": "analyst", "topic": "macro", "article_id": 15},
        "classification": {
            "intent_type": "content_generation",
            "confidence": 0.94,
            "action": "regenerate_keywords",
            "article_id": 15,
            "reason": "User wants to regenerate keywords based on headline and content"
        }
    },
    {
        "message": "rewrite the content",
        "context": {"section": "analyst", "topic": "equity", "article_id": 10},
        "classification": {
            "intent_type": "content_generation",
            "confidence": 0.93,
            "action": "regenerate_content",
            "article_id": 10,
            "reason": "User wants to rewrite/regenerate the article content"
        }
    },
    {
        "message": "create new keywords",
        "context": {"section": "analyst", "topic": "macro", "article_headline": "Fed Rate Decision"},
        "classification": {
            "intent_type": "content_generation",
            "confidence": 0.92,
            "action": "regenerate_keywords",
            "reason": "User wants to generate keywords from existing headline/content"
        }
    },

    # Analyst Workflow - Submit for Review
    {
        "message": "submit this for review",
        "context": {"section": "analyst", "article_id": 42, "article_status": "draft"},
        "classification": {
            "intent_type": "editor_workflow",
            "confidence": 0.95,
            "action": "submit",
            "article_id": 42,
            "reason": "Analyst wants to submit draft article for editorial review"
        }
    },
    {
        "message": "submit it",
        "context": {"section": "analyst", "article_id": 10, "article_status": "draft"},
        "classification": {
            "intent_type": "editor_workflow",
            "confidence": 0.93,
            "action": "submit",
            "article_id": 10,
            "reason": "Analyst wants to submit the current draft for review"
        }
    },

    # Editor Workflow - Publish/Reject
    {
        "message": "this article looks good, let's publish it",
        "context": {"section": "editor", "article_id": 42, "article_status": "editor"},
        "classification": {
            "intent_type": "editor_workflow",
            "confidence": 0.96,
            "action": "publish",
            "article_id": 42,
            "reason": "Editor wants to publish the article"
        }
    },
    {
        "message": "approve this article",
        "context": {"section": "editor", "article_id": 42, "article_status": "editor"},
        "classification": {
            "intent_type": "editor_workflow",
            "confidence": 0.95,
            "action": "publish",
            "article_id": 42,
            "reason": "Editor wants to approve and publish the article"
        }
    },
    {
        "message": "can you show me what's waiting for my review",
        "context": {"section": "editor", "topic": "macro"},
        "classification": {
            "intent_type": "editor_workflow",
            "confidence": 0.90,
            "action": "list_pending",
            "topic": "macro",
            "reason": "Editor wants to see articles pending review"
        }
    },
    {
        "message": "send this back with feedback",
        "context": {"section": "editor", "article_id": 15, "article_status": "editor"},
        "classification": {
            "intent_type": "editor_workflow",
            "confidence": 0.93,
            "action": "reject",
            "article_id": 15,
            "reason": "Editor wants to reject article and return to analyst"
        }
    },

    # Status-Aware Invalid Actions
    {
        "message": "submit this article",
        "context": {"section": "analyst", "article_id": 42, "article_status": "editor"},
        "classification": {
            "intent_type": "general_chat",
            "confidence": 0.90,
            "reason": "Article already submitted (status=editor). Guide user to editor hub to track review."
        }
    },
    {
        "message": "publish this now",
        "context": {"section": "analyst", "article_id": 10, "article_status": "draft", "role": "analyst"},
        "classification": {
            "intent_type": "editor_workflow",
            "confidence": 0.85,
            "action": "submit",
            "article_id": 10,
            "reason": "Analyst cannot publish directly. Interpreting as submit for review (draft→editor)."
        }
    },
    {
        "message": "edit this article",
        "context": {"section": "analyst", "article_id": 25, "article_status": "published"},
        "classification": {
            "intent_type": "general_chat",
            "confidence": 0.88,
            "reason": "Article is published. Editing requires admin to recall it first."
        }
    },

    # Entitlements
    {
        "message": "what features do I have access to",
        "context": {"section": "home"},
        "classification": {
            "intent_type": "entitlements",
            "confidence": 0.94,
            "reason": "User asking about their available features/permissions"
        }
    },
    {
        "message": "am I able to publish articles",
        "context": {"section": "analyst"},
        "classification": {
            "intent_type": "entitlements",
            "confidence": 0.92,
            "reason": "User asking about specific permission (publishing)"
        }
    },
    {
        "message": "what's my role here",
        "context": {"section": "home"},
        "classification": {
            "intent_type": "entitlements",
            "confidence": 0.91,
            "reason": "User asking about their role/access level"
        }
    },

    # General Chat (domain-specific)
    {
        "message": "what's your take on the fed's latest decision",
        "context": {"section": "home", "topic": "macro"},
        "classification": {
            "intent_type": "general_chat",
            "confidence": 0.95,
            "topic": "macro",
            "reason": "User asking about macroeconomic topic - general Q&A"
        }
    },
    {
        "message": "explain bond yields to me",
        "context": {"section": "home"},
        "classification": {
            "intent_type": "general_chat",
            "confidence": 0.93,
            "topic": "fixed_income",
            "reason": "User asking for explanation of financial concept"
        }
    },
    {
        "message": "hello, how are you today",
        "context": {"section": "home"},
        "classification": {
            "intent_type": "general_chat",
            "confidence": 0.98,
            "reason": "General greeting/conversation"
        }
    },
]


class ClassificationResult(BaseModel):
    """Structured output for intent classification."""
    intent_type: str = Field(
        description="Type of intent: navigation, ui_action, content_generation, editor_workflow, general_chat, or entitlements"
    )
    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0",
        ge=0.0,
        le=1.0
    )
    topic: Optional[str] = Field(
        default=None,
        description="Detected topic: macro, equity, fixed_income, or esg"
    )
    article_id: Optional[int] = Field(
        default=None,
        description="Article ID mentioned in the message"
    )
    action: Optional[str] = Field(
        default=None,
        description="Specific action requested (for ui_action or editor_workflow)"
    )
    target: Optional[str] = Field(
        default=None,
        description="Navigation target (for navigation intent)"
    )
    reason: str = Field(
        description="Brief explanation of why this classification was chosen"
    )


def classify_intent(
    message: str,
    navigation_context: Optional[NavigationContext] = None,
    user_scopes: Optional[List[str]] = None,
    use_llm: Optional[bool] = None
) -> IntentClassification:
    """
    Classify user intent using LLM with structured output.

    This is a more sophisticated classification than keyword matching,
    providing higher accuracy for ambiguous messages through:
    - Few-shot examples for consistent classification
    - Context awareness (section, topic, user roles)
    - OpenAI structured outputs for reliable JSON responses

    Args:
        message: The user's message to classify
        navigation_context: Current frontend navigation context
        user_scopes: User's permission scopes
        use_llm: Whether to use LLM. If None, uses INTENT_CLASSIFIER_USE_LLM env var

    Returns:
        IntentClassification with type, confidence, and details
    """
    nav_ctx = navigation_context or {}
    scopes = user_scopes or []

    # Determine whether to use LLM (allow override, default to env var)
    should_use_llm = use_llm if use_llm is not None else USE_LLM_CLASSIFIER

    if should_use_llm:
        try:
            # Build classification prompt with few-shot examples
            prompt = _build_classification_prompt(message, nav_ctx, scopes)
            result = _classify_with_llm(prompt)
            intent = _convert_to_intent_classification(result)
            logger.info(f"LLM classified '{message[:50]}...' as {intent['intent_type']} "
                       f"(confidence: {intent['confidence']:.2f})")
            return intent
        except Exception as e:
            logger.warning(f"LLM classification failed, falling back to rules: {e}")
            return _classify_with_rules(message, nav_ctx, scopes)
    else:
        logger.debug(f"Using rule-based classification (LLM disabled)")
        return _classify_with_rules(message, nav_ctx, scopes)


def _build_classification_prompt(
    message: str,
    nav_context: Dict[str, Any],
    user_scopes: List[str]
) -> str:
    """Build the prompt for LLM classification with few-shot examples."""
    # Determine available actions based on scopes
    available_roles = _extract_roles_from_scopes(user_scopes)

    # Build few-shot examples section
    examples_text = _build_examples_section()

    prompt = f"""You are an intent classifier for a financial research platform. Classify the user's message into one of the intent types below.

## Intent Types

1. **ui_action** - User wants to navigate to a page OR trigger a UI action

   **Page Navigation** (use these action values):
   - goto_home: "go to home", "show me articles", "take me to home page"
   - goto_analyst: "go to analyst hub", "analyst dashboard", "open analyst section"
   - goto_editor: "go to editor hub", "editor dashboard", "open editor section", "go to editor"
   - goto_topic_admin: "go to admin", "take me to {{topic}} admin", "admin panel", "admin dashboard"
   - goto_admin_global: "global admin", "manage topics", "manage users", "system settings"
   - goto_profile: "go to profile", "my profile", "account settings"
   - goto_search: "open search", "search for articles"
   - edit_article: "edit article #9", "open article 15 in editor" - MUST extract article_id from message

   **Admin Navigation Notes**:
   - "take me to macro admin" → goto_topic_admin with topic="macro"
   - "go to admin" → goto_topic_admin (uses current topic from context)
   - "global admin" or "manage topics" → goto_admin_global

   **Topic Selection** (when user mentions a topic name like equity, macro, etc.):
   - select_topic: "switch to equity", "show me macro articles"
   - goto_home with topic: "go to equity section" (navigates to home with topic selected)

   **View Switching** (within analyst page only):
   - switch_view_preview: "switch to preview", "show preview"
   - switch_view_editor: "switch to editor view", "show editor"
   - switch_view_resources: "show resources", "view resources tab"

   IMPORTANT: "editor dashboard" or "editor hub" means goto_editor (the editor PAGE).
   "editor view" or "switch to editor" in analyst context means switch_view_editor (a TAB within analyst page).

2. **content_generation** - User wants to create or edit article content
   - Actions:
     - create (default): "write about inflation", "help me draft an article"
     - regenerate_headline: "rephrase the title", "generate a new headline", "rewrite the headline"
     - regenerate_keywords: "create new keywords", "generate keywords from the content", "update keywords"
     - regenerate_content: "rewrite the content", "regenerate the article", "rephrase the content"
   - IMPORTANT: For regenerate actions, article context (article_id, headline, keywords) must be present
   - Note: Only valid if user has analyst or admin role

3. **editor_workflow** - Article workflow actions (analyst submit OR editor publish/reject)
   - Analyst actions (requires analyst role):
     - submit: "submit for review", "submit it", "submit the article" - sends DRAFT to editor queue
   - Editor actions (requires editor role):
     - publish: "publish this", "approve it", "go live" - publishes EDITOR status article
     - reject: "reject", "send back", "request changes" - returns to analyst
     - list_pending: "show pending", "what's waiting for review"
     - review: "review this article"
   - The system checks article status and applies correct permissions

4. **entitlements** - User is asking about their permissions or access
   - Examples: "what can I do", "what's my role", "am I allowed to publish", "show my permissions"

5. **general_chat** - General question, conversation, or domain Q&A
   - Examples: "what's happening in the market", "explain GDP", "tell me about bonds", "hello"
   - Use this for any financial/research questions that don't fit other categories

## Classification Rules
- Consider the current context (section, topic, article being viewed)
- Consider the user's roles - don't classify as content_generation without analyst role
- Navigation requests should be ui_action with appropriate action field
- IMPORTANT: Do NOT set topic field for navigation to analyst/editor/admin/profile pages unless explicitly mentioned
- IMPORTANT: If user says "go to" or "navigate" but the target is unclear, classify as general_chat to ask for clarification. Do NOT default to goto_home.
- If the message is ambiguous, lean toward general_chat
- Extract topic only if the user explicitly mentions a topic name (macro, equity, fixed_income, esg)
- Extract article_id if mentioned or from context
{examples_text}
## Current Request

**User Message:** "{message}"

**Current Context:**
- Section: {nav_context.get('section', 'home')}
- Topic: {nav_context.get('topic', 'not specified')}
- Role: {nav_context.get('role', 'reader')}
- Article ID: {nav_context.get('article_id', 'none')}
- Article Status: {nav_context.get('article_status', 'none')}
- Article Headline: {nav_context.get('article_headline', 'none')}
- Article Keywords: {nav_context.get('article_keywords', 'none')}

**User's Available Roles:** {', '.join(available_roles) if available_roles else 'reader only'}

## Article Status Workflow Reference
- **draft**: Analyst is writing. Valid: save, edit, regenerate_*, submit (→ editor)
- **editor**: In review queue. Analyst: view only. Editor: review, publish, reject
- **pending_approval**: Awaiting HITL. No actions until approved/rejected.
- **published**: Live article. Reader: view, rate. Admin: recall, deactivate.

Use article_status to validate actions. Example: "submit" on status=editor is invalid (already submitted).

Provide your classification with confidence score (0.0-1.0) and brief reasoning."""

    return prompt


def _build_examples_section() -> str:
    """Build the few-shot examples section for the prompt."""
    examples_text = "\n## Examples\n"

    # Select diverse examples (one per intent type)
    selected_examples = []
    intent_types_seen = set()

    for ex in FEW_SHOT_EXAMPLES:
        intent_type = ex["classification"]["intent_type"]
        if intent_type not in intent_types_seen:
            selected_examples.append(ex)
            intent_types_seen.add(intent_type)
        if len(selected_examples) >= 5:  # Limit for token efficiency
            break

    for ex in selected_examples:
        ctx = ex.get("context", {})
        ctx_str = f"section={ctx.get('section', 'home')}"
        if ctx.get("topic"):
            ctx_str += f", topic={ctx['topic']}"
        if ctx.get("article_id"):
            ctx_str += f", article_id={ctx['article_id']}"
        if ctx.get("article_status"):
            ctx_str += f", article_status={ctx['article_status']}"
        if ctx.get("article_headline"):
            ctx_str += f", article_headline=\"{ctx['article_headline']}\""

        classification = ex["classification"]
        class_str = json.dumps(classification, indent=2)

        examples_text += f"""
Message: "{ex['message']}"
Context: {ctx_str}
Classification:
{class_str}
"""

    return examples_text


def _classify_with_llm(prompt: str) -> ClassificationResult:
    """Use LLM to classify the intent with structured output."""
    llm = _get_classifier_llm()

    # Use structured output for reliable JSON responses
    structured_llm = llm.with_structured_output(ClassificationResult)

    result = structured_llm.invoke(prompt)
    logger.debug(f"LLM classification result: {result.intent_type} (confidence: {result.confidence})")
    return result


def _classify_with_rules(
    message: str,
    nav_context: Dict[str, Any],
    user_scopes: List[str]
) -> IntentClassification:
    """
    Rule-based classification as fallback.

    This is a simplified version of the router_node logic.
    """
    message_lower = message.lower()
    available_roles = _extract_roles_from_scopes(user_scopes)

    # Navigation keywords (include "goto" without space)
    nav_keywords = ["go to", "goto", "navigate", "take me", "open", "switch to", "show me"]
    if any(kw in message_lower for kw in nav_keywords):
        # Infer the navigation action from the message
        action_type = _infer_navigation_action(message_lower, nav_context)

        if action_type:
            # Clear target found - return ui_action
            # Also include topic if detected (for goto_home with topic)
            details = {
                "reason": "Navigation keyword detected",
                "action_type": action_type
            }
            # Detect and include topic for navigation
            detected_topic = _infer_topic(message_lower)
            if detected_topic:
                details["topic"] = detected_topic
            return IntentClassification(
                intent_type="ui_action",
                confidence=0.8,
                details=details
            )
        else:
            # No clear target - ask for clarification via general_chat
            return IntentClassification(
                intent_type="general_chat",
                confidence=0.6,
                details={
                    "reason": "Navigation intent detected but target unclear - needs clarification",
                    "needs_clarification": True,
                    "clarification_type": "navigation_target"
                }
            )

    # Entitlement keywords
    entitle_keywords = ["what can i", "my role", "my permission", "am i allowed", "entitled"]
    if any(kw in message_lower for kw in entitle_keywords):
        return IntentClassification(
            intent_type="entitlements",
            confidence=0.8,
            details={"reason": "Permission question detected"}
        )

    # Content generation/editing (if analyst)
    if "analyst" in available_roles or "admin" in available_roles:
        # Check for regenerate/rephrase actions first (more specific)
        regenerate_headline_kw = ["rephrase the title", "rephrase the headline", "regenerate headline",
                                   "new headline", "rewrite the title", "rewrite headline"]
        regenerate_keywords_kw = ["regenerate keywords", "create new keywords", "generate keywords",
                                   "new keywords", "update keywords", "keywords from"]
        regenerate_content_kw = ["rewrite the content", "regenerate content", "rephrase the content",
                                  "rewrite the article", "regenerate article"]

        if any(kw in message_lower for kw in regenerate_headline_kw):
            return IntentClassification(
                intent_type="content_generation",
                confidence=0.85,
                details={
                    "reason": "Headline regeneration request detected",
                    "action": "regenerate_headline",
                    "topic": nav_context.get("topic"),
                    "article_id": nav_context.get("article_id")
                }
            )

        if any(kw in message_lower for kw in regenerate_keywords_kw):
            return IntentClassification(
                intent_type="content_generation",
                confidence=0.85,
                details={
                    "reason": "Keyword regeneration request detected",
                    "action": "regenerate_keywords",
                    "topic": nav_context.get("topic"),
                    "article_id": nav_context.get("article_id")
                }
            )

        if any(kw in message_lower for kw in regenerate_content_kw):
            return IntentClassification(
                intent_type="content_generation",
                confidence=0.85,
                details={
                    "reason": "Content regeneration request detected",
                    "action": "regenerate_content",
                    "topic": nav_context.get("topic"),
                    "article_id": nav_context.get("article_id")
                }
            )

        # General content creation
        content_keywords = ["write", "generate", "create article", "draft", "compose"]
        if any(kw in message_lower for kw in content_keywords):
            return IntentClassification(
                intent_type="content_generation",
                confidence=0.75,
                details={
                    "reason": "Content generation keyword detected",
                    "action": "create",
                    "topic": nav_context.get("topic")
                }
            )

    # Content generation requests from any user (node will handle permissions/guidance)
    content_keywords = ["write", "generate", "create article", "draft", "compose", "write an article"]
    if any(kw in message_lower for kw in content_keywords):
        return IntentClassification(
            intent_type="content_generation",
            confidence=0.70,
            details={
                "reason": "Content generation request - node will check permissions",
                "action": "create",
                "topic": nav_context.get("topic")
            }
        )

    # Submit action from any user (node will check permissions and guide appropriately)
    if any(kw in message_lower for kw in ["submit", "submit for review", "send for review"]):
        return IntentClassification(
            intent_type="editor_workflow",
            confidence=0.80,
            details={
                "reason": "Submit request - node will check permissions",
                "action": "submit",
                "topic": nav_context.get("topic"),
                "article_id": nav_context.get("article_id")
            }
        )

    # Editor workflow actions from any user (node will check permissions and guide appropriately)
    editor_keywords = ["approve", "reject", "publish", "review article", "pending articles"]
    if any(kw in message_lower for kw in editor_keywords):
        return IntentClassification(
            intent_type="editor_workflow",
            confidence=0.70,
            details={
                "reason": "Editorial action request - node will check permissions",
                "action": _infer_editor_action(message_lower),
                "topic": nav_context.get("topic"),
                "article_id": nav_context.get("article_id")
            }
        )

    # UI action keywords (excluding "submit" which is handled above)
    ui_keywords = ["save", "delete", "click", "switch view"]
    if any(kw in message_lower for kw in ui_keywords):
        return IntentClassification(
            intent_type="ui_action",
            confidence=0.7,
            details={"reason": "UI action keyword detected"}
        )

    # Default to general chat
    return IntentClassification(
        intent_type="general_chat",
        confidence=0.5,
        details={
            "reason": "No specific intent detected",
            "topic": _infer_topic(message_lower)
        }
    )


def _convert_to_intent_classification(result: ClassificationResult) -> IntentClassification:
    """Convert LLM result to IntentClassification."""
    # Validate intent type
    valid_types = ["navigation", "ui_action", "content_generation",
                   "editor_workflow", "general_chat", "entitlements"]
    intent_type = result.intent_type if result.intent_type in valid_types else "general_chat"

    details = {
        "reason": result.reason
    }

    if result.topic:
        details["topic"] = result.topic
    if result.article_id:
        details["article_id"] = result.article_id
    if result.action:
        # Use action_type for ui_action intents (expected by ui_action_node.py)
        # Use action for editor_workflow intents (expected by editor_workflow_node.py)
        if intent_type == "ui_action":
            details["action_type"] = result.action
        else:
            details["action"] = result.action
    if result.target:
        details["target"] = result.target

    return IntentClassification(
        intent_type=intent_type,  # type: ignore
        confidence=result.confidence,
        details=details
    )


def _extract_roles_from_scopes(scopes: List[str]) -> List[str]:
    """Extract unique roles from scope list."""
    roles = set()
    for scope in scopes:
        if ":" in scope:
            _, role = scope.split(":", 1)
            roles.add(role)
    return list(roles)


def _infer_editor_action(message: str) -> str:
    """Infer specific editor action from message."""
    if any(w in message for w in ["approve", "publish", "accept"]):
        return "approve"
    if any(w in message for w in ["reject", "decline", "send back"]):
        return "reject"
    if any(w in message for w in ["pending", "queue", "list"]):
        return "list_pending"
    return "review"


def _infer_navigation_action(message: str, nav_context: Dict[str, Any]) -> Optional[str]:
    """
    Infer specific navigation action from message.

    Returns None if no clear target is detected - caller should ask for clarification.
    """
    # Check for specific page navigation targets
    if any(w in message for w in ["analyst", "analyst hub", "analyst dashboard"]):
        return "goto_analyst"
    if any(w in message for w in ["editor hub", "editor dashboard", "editor section"]):
        return "goto_editor"
    # "editor" alone without "view" should also be goto_editor
    if "editor" in message and "view" not in message:
        return "goto_editor"
    # Admin navigation - distinguish between topic admin and global admin
    if any(w in message for w in ["global admin", "manage topics", "manage users", "system admin"]):
        return "goto_admin_global"
    if any(w in message for w in ["admin", "admin panel", "admin dashboard", "content admin"]):
        return "goto_topic_admin"
    if any(w in message for w in ["profile", "my account", "account settings"]):
        return "goto_profile"
    if "search" in message:
        return "goto_search"
    if any(w in message for w in ["home", "main page", "front page"]):
        return "goto_home"

    # View switching (within analyst section)
    if nav_context.get("section") == "analyst":
        if "preview" in message:
            return "switch_view_preview"
        if "editor" in message and "view" in message:
            return "switch_view_editor"
        if "resource" in message:
            return "switch_view_resources"

    # Check if message mentions a topic name - navigate to home with that topic
    from agents.topic_manager import infer_topic
    detected_topic = infer_topic(message, ai_only=False)
    if detected_topic:
        return "goto_home"

    # No clear target detected - return None to trigger clarification
    return None


def _infer_topic(message: str) -> Optional[str]:
    """Infer topic from message using dynamic TopicManager."""
    from agents.topic_manager import infer_topic
    return infer_topic(message)
