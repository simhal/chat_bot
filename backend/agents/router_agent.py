"""Master router agent that selects appropriate specialist."""

from typing import Dict, Literal
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from agents.state import AgentState
from services.prompt_service import PromptService
import json


class RouterAgent:
    """
    Master router that analyzes queries and selects the appropriate specialist.
    Uses LLM with JSON mode for structured output.
    """

    def __init__(self, llm: ChatOpenAI, custom_prompt: str = None):
        """
        Initialize router agent.

        Args:
            llm: ChatOpenAI LLM instance
            custom_prompt: Optional user-specific custom prompt
        """
        self.llm = llm
        self.custom_prompt = custom_prompt

        # Get system prompt from PromptService
        self.system_prompt = PromptService.build_full_prompt("router", custom_prompt)

    def route(self, state: AgentState) -> AgentState:
        """
        Analyze the latest user message and route to appropriate specialist.
        Uses JSON mode for structured, reliable output.

        Args:
            state: Current agent state

        Returns:
            Updated state with selected_agent and routing_reason
        """
        # Get latest user message
        messages = state["messages"]
        latest_message = messages[-1].content

        # Create routing prompt
        routing_messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Route this query: {latest_message}")
        ]

        # Use structured output (JSON mode) for reliable routing
        llm_with_json = self.llm.bind(response_format={"type": "json_object"})

        # Get routing decision
        try:
            response = llm_with_json.invoke(routing_messages)

            # Parse JSON response
            routing_data = json.loads(response.content)

            selected_agent = routing_data.get("agent", "equity").lower()
            routing_reason = routing_data.get("reason", "Query analysis")

            # Validate agent selection
            valid_agents: list[Literal["equity", "economist", "fixed_income"]] = [
                "equity", "economist", "fixed_income"
            ]

            if selected_agent not in valid_agents:
                # Default to equity if invalid selection
                selected_agent = "equity"
                routing_reason = f"Default routing (invalid selection: {selected_agent})"

            # Update state
            state["selected_agent"] = selected_agent
            state["routing_reason"] = routing_reason
            state["iterations"] += 1

        except (json.JSONDecodeError, KeyError) as e:
            # Fallback if JSON parsing fails
            print(f"Router JSON parsing error: {e}")
            state["selected_agent"] = "equity"
            state["routing_reason"] = "Default routing (parsing error)"
            state["iterations"] += 1

        return state
