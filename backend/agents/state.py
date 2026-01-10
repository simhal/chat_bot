"""
State schema for multi-agent LangGraph system.

This module defines:
1. Pydantic models for API validation (ChatResponse, NavigationContextModel, UserContextModel)
2. TypedDict schemas for LangGraph state management (AgentState, NavigationContext, etc.)

The Pydantic models are used at API boundaries for validation.
The TypedDicts are used internally by LangGraph nodes.
"""

from typing import TypedDict, List, Literal, Optional, Annotated, Dict, Any
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
import operator


# =============================================================================
# Pydantic Models (for API validation and response structure)
# =============================================================================

class ChatResponse(BaseModel):
    """
    Response structure sent to frontend.
    Using Pydantic ensures the response is always valid.
    """
    response: str
    agent_type: str = "general"
    routing_reason: str = ""
    articles: List[Dict[str, Any]] = Field(default_factory=list)
    ui_action: Optional[Dict[str, Any]] = None
    navigation: Optional[Dict[str, Any]] = None
    editor_content: Optional[Dict[str, Any]] = None
    confirmation: Optional[Dict[str, Any]] = None


class NavigationContextModel(BaseModel):
    """
    Pydantic model for navigation context from frontend.
    Can be used directly in FastAPI request models.
    """
    section: str = "home"
    topic: Optional[str] = None
    article_id: Optional[int] = None
    article_headline: Optional[str] = None
    article_keywords: Optional[str] = None
    article_status: Optional[str] = None
    role: str = "reader"
    sub_nav: Optional[str] = None
    view_mode: Optional[str] = None
    resource_id: Optional[int] = None
    resource_name: Optional[str] = None
    resource_type: Optional[str] = None
    admin_view: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for use with TypedDict-based state."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class UserContextModel(BaseModel):
    """
    Pydantic model for user context.
    Includes automatic role parsing from scopes.
    """
    user_id: int
    email: str
    name: str
    surname: Optional[str] = None
    picture: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    highest_role: str = "reader"
    topic_roles: Dict[str, str] = Field(default_factory=dict)
    chat_tonality_text: Optional[str] = None
    content_tonality_text: Optional[str] = None

    @classmethod
    def from_scopes(
        cls,
        user_id: int,
        email: str,
        name: str,
        scopes: List[str],
        surname: Optional[str] = None,
        picture: Optional[str] = None,
        chat_tonality_text: Optional[str] = None,
        content_tonality_text: Optional[str] = None,
    ) -> "UserContextModel":
        """Create UserContext with automatic role parsing from scopes."""
        topic_roles: Dict[str, str] = {}
        highest_role = "reader"
        role_levels = {"admin": 4, "analyst": 3, "editor": 2, "reader": 1}

        for scope in scopes:
            if ":" in scope:
                topic, role = scope.split(":", 1)
                if role in role_levels:
                    if topic != "global":
                        current_level = role_levels.get(topic_roles.get(topic, "reader"), 0)
                        if role_levels.get(role, 0) > current_level:
                            topic_roles[topic] = role
                    if role_levels.get(role, 0) > role_levels.get(highest_role, 0):
                        highest_role = role

        return cls(
            user_id=user_id,
            email=email,
            name=name,
            surname=surname,
            picture=picture,
            scopes=scopes,
            highest_role=highest_role,
            topic_roles=topic_roles,
            chat_tonality_text=chat_tonality_text,
            content_tonality_text=content_tonality_text,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for use with TypedDict-based state."""
        return self.model_dump()


# =============================================================================
# Type Literals
# =============================================================================

# Agent type literals for LangGraph routing
AgentType = Literal[
    "general", "analyst", "editor", "article_query",
    "web_search", "data_download", "resource_query",
    "ui_action", "content_generation", "editor_workflow", "entitlements"
]

# Intent types for router node classification
IntentType = Literal[
    "navigation",
    "ui_action",
    "content_generation",
    "editor_workflow",
    "general_chat",
    "entitlements"
]

# Role hierarchy levels
RoleType = Literal["admin", "analyst", "editor", "reader"]


# =============================================================================
# TypedDict Schemas (for LangGraph state)
# =============================================================================

class NavigationContext(TypedDict, total=False):
    """Frontend navigation context sent with each chat request."""
    section: str
    topic: Optional[str]
    sub_nav: Optional[str]
    article_id: Optional[int]
    article_headline: Optional[str]
    article_keywords: Optional[str]
    article_status: Optional[str]
    role: str
    resource_id: Optional[int]
    resource_name: Optional[str]
    resource_type: Optional[str]
    view_mode: Optional[str]
    admin_view: Optional[str]


class IntentClassification(TypedDict):
    """Result of the router node's intent classification."""
    intent_type: IntentType
    confidence: float
    details: Dict[str, Any]


class UserContext(TypedDict):
    """Runtime user context loaded from JWT and database."""
    user_id: int
    email: str
    name: str
    surname: Optional[str]
    picture: Optional[str]
    scopes: List[str]
    highest_role: RoleType
    topic_roles: Dict[str, RoleType]
    chat_tonality_text: Optional[str]
    content_tonality_text: Optional[str]


class AgentState(TypedDict):
    """
    Simplified state passed between nodes in the LangGraph.

    Removed unused fields:
    - tool_results, last_tool_call, available_tools (never used)
    - iterations, max_iterations (never used)
    - workflow_context (rarely used, can be added back if needed)
    - final_response (now built directly from other fields)
    """
    # === Input ===
    messages: Annotated[List[BaseMessage], operator.add]
    user_context: Optional[UserContext]
    navigation_context: Optional[NavigationContext]

    # === Routing ===
    selected_agent: Optional[str]
    routing_reason: Optional[str]
    intent: Optional[IntentClassification]

    # === Output ===
    response_text: Optional[str]
    ui_action: Optional[Dict[str, Any]]
    navigation: Optional[Dict[str, Any]]
    editor_content: Optional[Dict[str, Any]]
    confirmation: Optional[Dict[str, Any]]
    article_context: Optional[Dict[str, Any]]  # Validated article info for frontend context update
    referenced_articles: List[Dict[str, Any]]

    # === Control Flow ===
    is_final: bool
    requires_hitl: bool
    hitl_decision: Optional[str]
    error: Optional[str]


# =============================================================================
# State Creation Helpers
# =============================================================================

def create_initial_state(
    user_context: UserContext,
    messages: Optional[List[BaseMessage]] = None,
    navigation_context: Optional[NavigationContext] = None,
) -> AgentState:
    """Create an initial AgentState with proper defaults."""
    return AgentState(
        messages=messages or [],
        user_context=user_context,
        navigation_context=navigation_context,
        selected_agent=None,
        routing_reason=None,
        intent=None,
        response_text=None,
        ui_action=None,
        navigation=None,
        editor_content=None,
        confirmation=None,
        article_context=None,
        referenced_articles=[],
        is_final=False,
        requires_hitl=False,
        hitl_decision=None,
        error=None,
    )


def create_user_context(
    user_id: int,
    email: str,
    name: str,
    scopes: List[str],
    surname: Optional[str] = None,
    picture: Optional[str] = None,
    chat_tonality_text: Optional[str] = None,
    content_tonality_text: Optional[str] = None,
) -> UserContext:
    """Create a UserContext with automatic role parsing from scopes."""
    topic_roles: Dict[str, RoleType] = {}
    highest_role: RoleType = "reader"
    role_levels = {"admin": 4, "analyst": 3, "editor": 2, "reader": 1}

    for scope in scopes:
        if ":" in scope:
            topic, role = scope.split(":", 1)
            if role in role_levels:
                if topic != "global":
                    current_level = role_levels.get(topic_roles.get(topic, "reader"), 0)
                    if role_levels.get(role, 0) > current_level:
                        topic_roles[topic] = role  # type: ignore
                if role_levels.get(role, 0) > role_levels.get(highest_role, 0):
                    highest_role = role  # type: ignore

    return UserContext(
        user_id=user_id,
        email=email,
        name=name,
        surname=surname,
        picture=picture,
        scopes=scopes,
        highest_role=highest_role,
        topic_roles=topic_roles,
        chat_tonality_text=chat_tonality_text,
        content_tonality_text=content_tonality_text,
    )


def create_navigation_context(
    section: str = "home",
    role: str = "reader",
    topic: Optional[str] = None,
    article_id: Optional[int] = None,
    article_headline: Optional[str] = None,
    article_keywords: Optional[str] = None,
    article_status: Optional[str] = None,
    sub_nav: Optional[str] = None,
    view_mode: Optional[str] = None,
    resource_id: Optional[int] = None,
    resource_name: Optional[str] = None,
    resource_type: Optional[str] = None,
    admin_view: Optional[str] = None,
) -> NavigationContext:
    """Create a NavigationContext from provided values."""
    ctx: NavigationContext = {"section": section, "role": role}
    if topic is not None:
        ctx["topic"] = topic
    if article_id is not None:
        ctx["article_id"] = article_id
    if article_headline is not None:
        ctx["article_headline"] = article_headline
    if article_keywords is not None:
        ctx["article_keywords"] = article_keywords
    if article_status is not None:
        ctx["article_status"] = article_status
    if sub_nav is not None:
        ctx["sub_nav"] = sub_nav
    if view_mode is not None:
        ctx["view_mode"] = view_mode
    if resource_id is not None:
        ctx["resource_id"] = resource_id
    if resource_name is not None:
        ctx["resource_name"] = resource_name
    if resource_type is not None:
        ctx["resource_type"] = resource_type
    if admin_view is not None:
        ctx["admin_view"] = admin_view
    return ctx


# =============================================================================
# Workflow State Helpers (for analyst workflows)
# =============================================================================

class WorkflowContext(TypedDict, total=False):
    """Context for analyst research workflows."""
    current_step: str
    article_id: Optional[int]
    resources: List[Dict[str, Any]]
    search_results: List[Dict[str, Any]]


def update_workflow_step(state: AgentState, step: str, article_id: Optional[int] = None) -> AgentState:
    """Update workflow progress in state."""
    # AgentState doesn't have workflow_context anymore, so this is a no-op
    # Kept for backwards compatibility with analyst_agent.py
    return state


def add_resource_to_workflow(state: AgentState, resource: Dict[str, Any]) -> AgentState:
    """Add a resource to the workflow context."""
    # AgentState doesn't have workflow_context anymore, so this is a no-op
    # Kept for backwards compatibility with analyst_agent.py
    return state
