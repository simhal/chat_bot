"""
Intent Classifier for LLM-based routing.

This module provides sophisticated intent classification using LLM with
structured output. It's used by the router node when keyword-based
classification is insufficient or when higher accuracy is needed.
"""

from typing import Dict, Any, Optional, List
import logging
import os
import json

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agents.state import IntentClassification, IntentType, NavigationContext

logger = logging.getLogger(__name__)


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
    use_llm: bool = True
) -> IntentClassification:
    """
    Classify user intent using LLM with structured output.

    This is a more sophisticated classification than keyword matching,
    providing higher accuracy for ambiguous messages.

    Args:
        message: The user's message to classify
        navigation_context: Current frontend navigation context
        user_scopes: User's permission scopes
        use_llm: Whether to use LLM (can be disabled for testing)

    Returns:
        IntentClassification with type, confidence, and details
    """
    nav_ctx = navigation_context or {}
    scopes = user_scopes or []

    # Build classification prompt
    prompt = _build_classification_prompt(message, nav_ctx, scopes)

    if use_llm:
        try:
            result = _classify_with_llm(prompt)
            return _convert_to_intent_classification(result)
        except Exception as e:
            logger.warning(f"LLM classification failed, falling back to rules: {e}")
            return _classify_with_rules(message, nav_ctx, scopes)
    else:
        return _classify_with_rules(message, nav_ctx, scopes)


def _build_classification_prompt(
    message: str,
    nav_context: Dict[str, Any],
    user_scopes: List[str]
) -> str:
    """Build the prompt for LLM classification."""
    # Determine available actions based on scopes
    available_roles = _extract_roles_from_scopes(user_scopes)

    prompt = f"""Classify the user's intent based on their message and context.

## User Message
"{message}"

## Current Context
- Section: {nav_context.get('section', 'home')}
- Topic: {nav_context.get('topic', 'not specified')}
- Role: {nav_context.get('role', 'reader')}
- Article ID: {nav_context.get('article_id', 'none')}
- Article Headline: {nav_context.get('article_headline', 'none')}

## User's Roles
{', '.join(available_roles) if available_roles else 'reader only'}

## Intent Types

1. **navigation** - User wants to go to a different page/section
   Examples: "go to home", "take me to the analyst hub", "open profile"

2. **ui_action** - User wants to trigger a specific UI action
   Examples: "save this", "submit for review", "delete the article", "switch to preview"

3. **content_generation** - User wants to create/write article content
   Examples: "write about inflation", "generate an article", "draft a piece on stocks"
   Note: Only available if user has analyst role

4. **editor_workflow** - User wants to perform editorial actions
   Examples: "approve this article", "reject with feedback", "review the pending articles"
   Note: Only available if user has editor role

5. **entitlements** - User is asking about permissions/access
   Examples: "what can I do", "what's my role", "am I allowed to publish"

6. **general_chat** - General question or conversation
   Examples: "what's happening in the market", "explain GDP", "tell me about bonds"

## Classification Rules
- Consider the current context (section, topic, article)
- Consider the user's roles - don't classify as content_generation if they're not an analyst
- If the message is ambiguous, lean toward general_chat
- Extract any article IDs, topics, or specific targets mentioned

Provide your classification with confidence score (0.0-1.0) and reasoning."""

    return prompt


def _classify_with_llm(prompt: str) -> ClassificationResult:
    """Use LLM to classify the intent."""
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.1,  # Low temperature for classification
        api_key=os.getenv("OPENAI_API_KEY", "")
    )

    # Use structured output
    structured_llm = llm.with_structured_output(ClassificationResult)

    result = structured_llm.invoke(prompt)
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

    # Navigation keywords
    nav_keywords = ["go to", "navigate", "take me", "open", "switch to", "show me"]
    if any(kw in message_lower for kw in nav_keywords):
        return IntentClassification(
            intent_type="navigation",
            confidence=0.8,
            details={"reason": "Navigation keyword detected"}
        )

    # Entitlement keywords
    entitle_keywords = ["what can i", "my role", "my permission", "am i allowed", "entitled"]
    if any(kw in message_lower for kw in entitle_keywords):
        return IntentClassification(
            intent_type="entitlements",
            confidence=0.8,
            details={"reason": "Permission question detected"}
        )

    # Content generation (if analyst)
    if "analyst" in available_roles or "admin" in available_roles:
        content_keywords = ["write", "generate", "create article", "draft", "compose"]
        if any(kw in message_lower for kw in content_keywords):
            return IntentClassification(
                intent_type="content_generation",
                confidence=0.75,
                details={
                    "reason": "Content generation keyword detected",
                    "topic": nav_context.get("topic")
                }
            )

    # Editor workflow (if editor)
    if "editor" in available_roles or "admin" in available_roles:
        editor_keywords = ["approve", "reject", "publish", "review", "pending"]
        if any(kw in message_lower for kw in editor_keywords):
            return IntentClassification(
                intent_type="editor_workflow",
                confidence=0.75,
                details={
                    "reason": "Editorial action keyword detected",
                    "action": _infer_editor_action(message_lower),
                    "topic": nav_context.get("topic"),
                    "article_id": nav_context.get("article_id")
                }
            )

    # UI action keywords
    ui_keywords = ["save", "submit", "delete", "click", "switch view"]
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


def _infer_topic(message: str) -> Optional[str]:
    """Infer topic from message."""
    topic_keywords = {
        "macro": ["economy", "gdp", "inflation", "fed", "interest rate"],
        "equity": ["stock", "equity", "company", "earnings"],
        "fixed_income": ["bond", "yield", "treasury", "credit"],
        "esg": ["esg", "sustainability", "climate", "governance"]
    }

    for topic, keywords in topic_keywords.items():
        if any(kw in message for kw in keywords):
            return topic

    return None
