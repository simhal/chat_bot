"""Base class for specialist agents."""

from abc import ABC, abstractmethod
from typing import List
from langchain_core.tools import Tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from agents.state import AgentState
from services.prompt_service import PromptService


class BaseSpecialistAgent(ABC):
    """
    Base class for all specialist financial analyst agents.
    Each specialist extends this class and implements their specific tools.
    """

    def __init__(self, agent_type: str, llm: ChatOpenAI, custom_prompt: str = None):
        """
        Initialize specialist agent.

        Args:
            agent_type: Type of agent (equity, economist, fixed_income)
            llm: ChatOpenAI LLM instance
            custom_prompt: Optional user-specific custom prompt
        """
        self.agent_type = agent_type
        self.llm = llm
        self.custom_prompt = custom_prompt

        # Load system prompt from PromptService
        self.system_prompt = PromptService.build_full_prompt(agent_type, custom_prompt)

        # Create tools
        self.tools = self.create_tools()

        # Create ReAct agent with tools
        if self.tools:
            self.agent = create_react_agent(
                self.llm,
                self.tools,
                state_modifier=self.system_prompt
            )
        else:
            # Fallback: no tools available
            self.agent = None

    @abstractmethod
    def create_tools(self) -> List[Tool]:
        """
        Create specialist-specific tools.
        Must be implemented by each specialist agent.

        Returns:
            List of LangChain Tool objects
        """
        pass

    def process(self, state: AgentState) -> AgentState:
        """
        Process the query using this specialist agent.
        Invokes the ReAct agent with message history.

        Args:
            state: Current agent state with messages and context

        Returns:
            Updated agent state with new messages
        """
        if self.agent:
            # Invoke ReAct agent with full message history
            result = self.agent.invoke({"messages": state["messages"]})

            # Update state with new messages
            state["messages"] = result["messages"]
        else:
            # Fallback: use LLM directly without tools
            from langchain_core.messages import AIMessage

            response = self.llm.invoke(state["messages"])
            state["messages"].append(AIMessage(content=response.content))

        # Mark as final response
        state["is_final"] = True

        return state
