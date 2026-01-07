"""
State schema for multi-agent LangGraph system.

This module defines the TypedDict schemas used for state management across
the agent hierarchy. The state flows through LangGraph nodes and carries
user context, workflow tracking, and tool results.

Architecture:
    The main chat graph uses these state schemas:
    - NavigationContext: Frontend location/context sent with each request
    - IntentClassification: Router node's classification of user intent
    - UserContext: User identity, permissions, and personalization
    - WorkflowContext: Multi-step workflow tracking for HITL
    - AgentState: Full state passed between LangGraph nodes
"""

from typing import TypedDict, List, Literal, Optional, Annotated, Dict, Any
from langchain_core.messages import BaseMessage
import operator
import uuid
from datetime import datetime


# Agent type literals - extended for new architecture
AgentType = Literal[
    # Legacy specialists (deprecated, kept for backward compatibility)
    "equity", "economist", "fixed_income",
    # New unified agents
    "general", "analyst", "editor", "article_query",
    # Sub-agents (internal routing)
    "web_search", "data_download", "resource_query",
    # LangGraph node types
    "navigation", "ui_action", "content_generation", "editor_workflow", "entitlements"
]

# Intent types for router node classification
IntentType = Literal[
    "navigation",          # Navigate to different page/section
    "ui_action",           # Trigger UI action (button click, tab switch)
    "content_generation",  # Generate article content
    "editor_workflow",     # Editor actions (review, publish, reject)
    "general_chat",        # General Q&A and topic-specific queries
    "entitlements"         # Permission/access questions
]

# Role hierarchy levels
RoleType = Literal["admin", "analyst", "editor", "reader"]

# Topic types - DEPRECATED: Use TopicManager.get_available_topics() instead
# Kept for backward compatibility only
TopicType = Literal["macro", "equity", "fixed_income", "esg"]


class NavigationContext(TypedDict, total=False):
    """
    Frontend navigation context sent with each chat request.
    Provides the agent with awareness of where the user is and what they're doing.
    """
    # Page location
    section: str  # home, analyst, editor, admin, profile, search
    topic: Optional[str]  # Current topic slug (e.g., 'macro', 'equity')
    sub_nav: Optional[str]  # Sub-navigation state (e.g., 'drafts', 'pending')

    # Article context
    article_id: Optional[int]  # Currently focused article ID
    article_headline: Optional[str]  # Article headline for display
    article_keywords: Optional[str]  # Article keywords for context
    article_status: Optional[str]  # Article status (draft, editor, published)

    # User role in current context
    role: str  # reader, analyst, editor, admin

    # Resource context
    resource_id: Optional[int]  # Currently focused resource ID
    resource_name: Optional[str]  # Resource name
    resource_type: Optional[str]  # Resource type

    # View state
    view_mode: Optional[str]  # editor, preview, resources
    admin_view: Optional[str]  # For admin section specific views


class IntentClassification(TypedDict):
    """
    Result of the router node's intent classification.
    Determines which handler node will process the request.
    """
    intent_type: IntentType  # Which handler to route to
    confidence: float  # 0.0 to 1.0 confidence score
    details: Dict[str, Any]  # Extracted details (topic, article_id, action, etc.)


class UserContext(TypedDict):
    """
    Runtime user context loaded from JWT and database.
    Available to all agents and tools for permission checking and personalization.
    """
    # Identity
    user_id: int
    email: str
    name: str
    surname: Optional[str]
    picture: Optional[str]

    # Permissions - parsed from JWT scopes
    scopes: List[str]  # e.g., ["macro:analyst", "equity:reader", "global:admin"]
    highest_role: RoleType  # Highest role across all topics

    # Topic-specific roles
    topic_roles: Dict[str, RoleType]  # e.g., {"macro": "analyst", "equity": "reader"}

    # Personalization - loaded from user preferences
    chat_tonality_text: Optional[str]  # Tonality prompt for chat responses
    content_tonality_text: Optional[str]  # Tonality prompt for generated content


class WorkflowContext(TypedDict):
    """
    Tracking context for multi-step agent workflows.
    Used for maintaining state across Celery tasks and HITL interrupts.
    """
    # Workflow identity
    workflow_id: str  # UUID for this workflow instance
    workflow_type: str  # e.g., "research", "publish", "review"
    started_at: str  # ISO timestamp

    # Article context
    article_id: Optional[int]  # Article being created/edited
    topic: Optional[str]  # Topic slug

    # Resource tracking
    resources_created: List[int]  # IDs of resources created during workflow
    resources_attached: List[int]  # IDs of resources attached to article

    # Step tracking
    current_step: str  # Current step name
    completed_steps: List[str]  # List of completed step names

    # HITL state
    awaiting_approval: bool  # True if waiting for human approval
    approval_request_id: Optional[int]  # ID of pending approval request


class AgentState(TypedDict):
    """
    State passed between nodes in the LangGraph.
    Enhanced state carries user context, workflow tracking, and tool results.

    This is the central state schema for the main chat graph. Each node reads
    from and writes to this state as messages flow through the graph.
    """
    # === Message History ===
    # operator.add ensures messages are appended, not replaced
    messages: Annotated[List[BaseMessage], operator.add]

    # === Routing ===
    # Selected agent type (determined by router)
    selected_agent: Optional[AgentType]
    # Router's reasoning for agent selection
    routing_reason: Optional[str]
    # Intent classification from router node
    intent: Optional[IntentClassification]

    # === User Context ===
    user_context: Optional[UserContext]
    # Navigation context from frontend
    navigation_context: Optional[NavigationContext]

    # === Legacy Fields (kept for backward compatibility) ===
    user_id: int
    user_custom_prompt: Optional[str]

    # === Workflow Context ===
    workflow_context: Optional[WorkflowContext]

    # === Tool Execution ===
    # Results from tool calls for audit/debugging
    tool_results: Dict[str, Any]
    last_tool_call: Optional[str]

    # === Available Tools ===
    # Filtered list of tool names based on user permissions
    available_tools: List[str]

    # === Response Building ===
    # Final response text to display to user
    response_text: Optional[str]
    # UI action to trigger in frontend
    ui_action: Optional[Dict[str, Any]]
    # Navigation command for frontend
    navigation: Optional[Dict[str, Any]]
    # Content for editor injection
    editor_content: Optional[Dict[str, Any]]
    # HITL confirmation dialog parameters
    confirmation: Optional[Dict[str, Any]]
    # Articles referenced in response
    referenced_articles: List[Dict[str, Any]]
    # Final assembled response object
    final_response: Optional[Dict[str, Any]]

    # === Control Flow ===
    # Iteration tracking (prevent infinite loops)
    iterations: int
    max_iterations: int

    # Final response flag
    is_final: bool

    # HITL interrupt flag
    requires_hitl: bool

    # HITL decision (set when resuming from checkpoint)
    hitl_decision: Optional[str]

    # Error tracking
    error: Optional[str]


def create_initial_state(
    user_context: UserContext,
    messages: Optional[List[BaseMessage]] = None,
    available_tools: Optional[List[str]] = None,
    workflow_type: Optional[str] = None,
    topic: Optional[str] = None,
    navigation_context: Optional[NavigationContext] = None,
) -> AgentState:
    """
    Create an initial AgentState with proper defaults.

    Args:
        user_context: The user's context (required)
        messages: Optional initial messages
        available_tools: Optional list of available tool names
        workflow_type: Optional workflow type for tracking
        topic: Optional topic slug
        navigation_context: Optional frontend navigation context

    Returns:
        Initialized AgentState
    """
    workflow_context = None
    if workflow_type:
        workflow_context = WorkflowContext(
            workflow_id=str(uuid.uuid4()),
            workflow_type=workflow_type,
            started_at=datetime.utcnow().isoformat(),
            article_id=None,
            topic=topic,
            resources_created=[],
            resources_attached=[],
            current_step="start",
            completed_steps=[],
            awaiting_approval=False,
            approval_request_id=None,
        )

    return AgentState(
        messages=messages or [],
        selected_agent=None,
        routing_reason=None,
        intent=None,
        user_context=user_context,
        navigation_context=navigation_context,
        user_id=user_context["user_id"],
        user_custom_prompt=user_context.get("chat_tonality_text"),
        workflow_context=workflow_context,
        tool_results={},
        last_tool_call=None,
        available_tools=available_tools or [],
        response_text=None,
        ui_action=None,
        navigation=None,
        editor_content=None,
        confirmation=None,
        referenced_articles=[],
        final_response=None,
        iterations=0,
        max_iterations=10,
        is_final=False,
        requires_hitl=False,
        hitl_decision=None,
        error=None,
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
    """
    Create a NavigationContext from provided values.

    This helper ensures consistent creation of navigation context objects
    that are sent from the frontend with each chat request.

    Args:
        section: Current page section (home, analyst, editor, admin, profile, search)
        role: User's role in current context (reader, analyst, editor, admin)
        topic: Current topic slug
        article_id: Currently focused article ID
        article_headline: Article headline for context
        article_keywords: Article keywords
        article_status: Article workflow status
        sub_nav: Sub-navigation state
        view_mode: Current view mode (editor, preview, resources)
        resource_id: Currently focused resource ID
        resource_name: Resource name
        resource_type: Resource type
        admin_view: Admin section view

    Returns:
        Populated NavigationContext
    """
    ctx: NavigationContext = {
        "section": section,
        "role": role,
    }

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
    """
    Create a UserContext from provided values.

    Args:
        user_id: User's database ID
        email: User's email address
        name: User's first name
        scopes: List of permission scopes from JWT
        surname: Optional surname
        picture: Optional profile picture URL
        chat_tonality_text: Optional chat tonality prompt
        content_tonality_text: Optional content tonality prompt

    Returns:
        Populated UserContext
    """
    # Parse topic-specific roles from scopes
    topic_roles: Dict[str, RoleType] = {}
    highest_role: RoleType = "reader"

    role_levels = {"admin": 4, "analyst": 3, "editor": 2, "reader": 1}

    for scope in scopes:
        if ":" in scope:
            topic, role = scope.split(":", 1)
            if role in role_levels:
                # Track topic-specific role
                if topic != "global":
                    current_level = role_levels.get(topic_roles.get(topic, "reader"), 0)
                    if role_levels.get(role, 0) > current_level:
                        topic_roles[topic] = role  # type: ignore

                # Track highest overall role
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


def update_workflow_step(
    state: AgentState,
    new_step: str,
    article_id: Optional[int] = None,
) -> AgentState:
    """
    Update the workflow context with a new step.

    Args:
        state: Current agent state
        new_step: Name of the new step
        article_id: Optional article ID to set

    Returns:
        Updated AgentState (new dict, doesn't mutate input)
    """
    if not state.get("workflow_context"):
        return state

    workflow = dict(state["workflow_context"])
    completed = list(workflow.get("completed_steps", []))

    # Mark current step as completed
    current = workflow.get("current_step")
    if current and current not in completed:
        completed.append(current)

    workflow["completed_steps"] = completed
    workflow["current_step"] = new_step

    if article_id is not None:
        workflow["article_id"] = article_id

    return {**state, "workflow_context": workflow}


def add_resource_to_workflow(
    state: AgentState,
    resource_id: int,
    attached: bool = False,
) -> AgentState:
    """
    Add a resource ID to the workflow tracking.

    Args:
        state: Current agent state
        resource_id: ID of the created/attached resource
        attached: Whether the resource was attached to an article

    Returns:
        Updated AgentState
    """
    if not state.get("workflow_context"):
        return state

    workflow = dict(state["workflow_context"])

    if attached:
        attached_list = list(workflow.get("resources_attached", []))
        if resource_id not in attached_list:
            attached_list.append(resource_id)
        workflow["resources_attached"] = attached_list
    else:
        created_list = list(workflow.get("resources_created", []))
        if resource_id not in created_list:
            created_list.append(resource_id)
        workflow["resources_created"] = created_list

    return {**state, "workflow_context": workflow}
