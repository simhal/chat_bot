"""LangGraph multi-agent system builder."""

from typing import Literal, Dict
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from agents.state import AgentState
from agents.router_agent import RouterAgent
from agents.equity_agent import EquityAgent
from agents.economist_agent import EconomistAgent
from agents.fixed_income_agent import FixedIncomeAgent
from conversation_memory import create_conversation_memory


class MultiAgentGraph:
    """
    Build and manage the multi-agent LangGraph.
    Implements supervisor pattern with conditional routing.
    """

    def __init__(self, user_id: int, custom_prompt: str = None):
        """
        Initialize multi-agent graph.

        Args:
            user_id: User ID for conversation isolation
            custom_prompt: Optional user-specific custom prompt
        """
        self.user_id = user_id
        self.custom_prompt = custom_prompt

        # Initialize LLM from chatbot_agent settings
        from chatbot_agent import settings
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=settings.agent_temperature,
            api_key=settings.openai_api_key
        )

        # Initialize agents
        self.router = RouterAgent(self.llm, custom_prompt)
        self.equity_agent = EquityAgent(self.llm, custom_prompt)
        self.economist_agent = EconomistAgent(self.llm, custom_prompt)
        self.fixed_income_agent = FixedIncomeAgent(self.llm, custom_prompt)

        # Build graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """
        Construct the LangGraph workflow with conditional routing.

        Graph structure:
            User Query → Router → [Conditional Edge] → Specialist → END
        """
        # Create graph with AgentState schema
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("router", self.router.route)
        workflow.add_node("equity", self.equity_agent.process)
        workflow.add_node("economist", self.economist_agent.process)
        workflow.add_node("fixed_income", self.fixed_income_agent.process)

        # Set entry point
        workflow.set_entry_point("router")

        # Add conditional routing from router to specialists
        workflow.add_conditional_edges(
            "router",
            self._route_to_specialist,
            {
                "equity": "equity",
                "economist": "economist",
                "fixed_income": "fixed_income"
            }
        )

        # All specialists route to END
        workflow.add_edge("equity", END)
        workflow.add_edge("economist", END)
        workflow.add_edge("fixed_income", END)

        return workflow.compile()

    def _route_to_specialist(self, state: AgentState) -> Literal["equity", "economist", "fixed_income"]:
        """
        Conditional edge function - routes based on router's decision.

        Args:
            state: Current agent state with selected_agent

        Returns:
            Agent type to route to
        """
        selected = state.get("selected_agent")

        # Validate selection
        if selected in ["equity", "economist", "fixed_income"]:
            return selected

        # Default to equity if invalid
        return "equity"

    def invoke(self, message: str) -> Dict[str, str]:
        """
        Invoke the multi-agent graph with a user message.
        Handles conversation memory and returns response with metadata.

        Args:
            message: User's message

        Returns:
            Dictionary with response, agent_type, and routing_reason
        """
        # Load conversation history from Redis
        memory = create_conversation_memory(self.user_id)
        history = memory.messages

        # Create initial state
        initial_state: AgentState = {
            "messages": history + [HumanMessage(content=message)],
            "selected_agent": None,
            "routing_reason": None,
            "user_id": self.user_id,
            "user_custom_prompt": self.custom_prompt,
            "iterations": 0,
            "is_final": False
        }

        # Invoke graph
        try:
            final_state = self.graph.invoke(initial_state)

            # Extract final message
            final_messages = final_state["messages"]
            final_message = final_messages[-1]

            # Save to conversation history
            memory.add_user_message(message)
            memory.add_ai_message(final_message.content)

            return {
                "response": final_message.content,
                "agent_type": final_state.get("selected_agent"),
                "routing_reason": final_state.get("routing_reason")
            }

        except Exception as e:
            # Error handling
            error_message = f"Error in multi-agent system: {str(e)}"
            print(error_message)

            # Save error to history for context
            memory.add_user_message(message)
            memory.add_ai_message(f"I apologize, but I encountered an error processing your request: {str(e)}")

            return {
                "response": f"I apologize, but I encountered an error: {str(e)}",
                "agent_type": None,
                "routing_reason": "Error occurred"
            }
