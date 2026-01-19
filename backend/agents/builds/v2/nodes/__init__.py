"""
LangGraph node implementations for the main chat graph.

This module contains role-based node functions that process state in the
chat graph workflow. Each node handles a specific role context and
updates the AgentState accordingly.

Role-based Nodes:
    router_node: Routes messages based on role context and intent
    navigation_node: Handles navigation requests (goto_* actions)
    user_node: Handles user profile and permission queries
    reader_node: Handles reader context (browse, search, rate)
    analyst_node: Handles analyst context (content creation, resources)
    editor_node: Handles editor context (review, publish, reject)
    admin_node: Handles admin context (delete, deactivate, manage)
    general_chat_node: Handles general Q&A and conversation
    response_builder: Assembles final response from state

Analyst Sub-graphs:
    article_content_node: Content generation sub-graph
    resource_node: Resource management sub-graph
"""

from agents.builds.v2.nodes.router_node import router_node, route_by_intent
from agents.builds.v2.nodes.navigation_node import navigation_node
from agents.builds.v2.nodes.general_chat_node import general_chat_node
from agents.builds.v2.nodes.response_builder import response_builder_node

# Role-based nodes (imported directly in graph.py for clarity)
# from agents.builds.v2.nodes.user_node import user_node
# from agents.builds.v2.nodes.reader_node import reader_node
# from agents.builds.v2.nodes.analyst_node import analyst_node
# from agents.builds.v2.nodes.editor_node import editor_node
# from agents.builds.v2.nodes.admin_node import admin_node

__all__ = [
    # Core routing
    "router_node",
    "route_by_intent",
    # Common nodes
    "navigation_node",
    "general_chat_node",
    "response_builder_node",
]
