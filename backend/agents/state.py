"""State schema for multi-agent LangGraph system."""

from typing import TypedDict, List, Literal, Optional, Annotated
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    """
    State passed between nodes in the LangGraph.
    This state carries information throughout the multi-agent workflow.
    """

    # Message history with conversation context
    # operator.add ensures messages are appended, not replaced
    messages: Annotated[List[BaseMessage], operator.add]

    # Selected specialist agent type (determined by router)
    selected_agent: Optional[Literal["equity", "economist", "fixed_income"]]

    # Router's reasoning for agent selection
    routing_reason: Optional[str]

    # User context
    user_id: int
    user_custom_prompt: Optional[str]

    # Iteration tracking (prevent infinite loops)
    iterations: int

    # Final response flag
    is_final: bool
