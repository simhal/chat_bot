"""LangChain-based agentic chatbot with tools and Redis-backed memory using LangGraph."""

from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import Tool
from langchain_community.tools import DuckDuckGoSearchRun
from langgraph.prebuilt import create_react_agent
from conversation_memory import create_conversation_memory, clear_conversation_history
from pydantic_settings import BaseSettings


class ChatbotSettings(BaseSettings):
    """Settings for the chatbot agent."""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    agent_temperature: float = 0.7

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = ChatbotSettings()


def create_chatbot_tools() -> List[Tool]:
    """
    Create tools for the chatbot agent.

    Add more tools here as needed (calculator, database queries, APIs, etc.)
    """
    tools = []

    # Web search tool
    try:
        search = DuckDuckGoSearchRun()
        search_tool = Tool(
            name="web_search",
            description="Search the web for current information. Use this when you need up-to-date information or facts about current events, people, places, or things. Input should be a search query.",
            func=search.run
        )
        tools.append(search_tool)
    except Exception as e:
        # If DuckDuckGo search fails, continue without it
        print(f"Warning: Could not initialize web search tool: {e}")

    # Add more tools here in the future:
    # - Calculator tool
    # - Database query tool
    # - API integration tools
    # - Custom business logic tools

    return tools


class ChatbotAgent:
    """Agentic chatbot with tools and Redis-backed conversation memory."""

    def __init__(self, user_id: int):
        """
        Initialize chatbot agent for a specific user.

        Args:
            user_id: User ID for conversation context isolation
        """
        self.user_id = user_id

        # Create Redis-backed message history
        self.message_history = create_conversation_memory(user_id)

        # Initialize LLM
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            temperature=settings.agent_temperature,
            api_key=settings.openai_api_key
        )

        # Create tools
        self.tools = create_chatbot_tools()

        # System prompt for the agent
        self.system_message = """You are a helpful AI assistant with access to various tools.

Use the available tools when needed to provide accurate and helpful responses.
Be conversational and remember the context of the conversation.

When you don't need tools, respond directly based on your knowledge and the conversation history."""

        # Create agent using LangGraph (modern approach)
        if self.tools:
            self.agent = create_react_agent(
                self.llm,
                self.tools,
                state_modifier=self.system_message
            )
        else:
            # Fallback: No tools available
            self.agent = None

    def chat(self, message: str) -> str:
        """
        Process a user message and return the agent's response.

        Args:
            message: User's message

        Returns:
            Agent's response
        """
        try:
            # Load conversation history from Redis
            chat_history = self.message_history.messages

            if self.agent and self.tools:
                # Use LangGraph agent with tools and memory
                from langchain_core.messages import HumanMessage

                # Add user message to history
                self.message_history.add_user_message(message)

                # Invoke agent with full message history
                response = self.agent.invoke(
                    {"messages": chat_history + [HumanMessage(content=message)]}
                )

                # Extract the last message from the agent
                assistant_message = response["messages"][-1].content

                # Save assistant response to history
                self.message_history.add_ai_message(assistant_message)

                return assistant_message
            else:
                # Fallback: Use LLM directly with memory
                from langchain_core.messages import HumanMessage, SystemMessage

                messages = [SystemMessage(content=self.system_message)]

                # Add conversation history
                messages.extend(chat_history)

                # Add current message
                messages.append(HumanMessage(content=message))

                # Get response from LLM
                response = self.llm.invoke(messages)
                assistant_message = response.content

                # Save to message history
                self.message_history.add_user_message(message)
                self.message_history.add_ai_message(assistant_message)

                return assistant_message

        except Exception as e:
            error_message = f"I apologize, but I encountered an error: {str(e)}"
            return error_message

    def clear_history(self) -> None:
        """Clear conversation history for this user."""
        clear_conversation_history(self.user_id)

    def get_history(self) -> List[Dict[str, Any]]:
        """Get conversation history from Redis."""
        chat_history = self.message_history.messages

        messages = []
        for msg in chat_history:
            if hasattr(msg, 'content'):
                role = "user" if msg.__class__.__name__ == "HumanMessage" else "assistant"
                messages.append({"role": role, "content": msg.content})

        return messages
