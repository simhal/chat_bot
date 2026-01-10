"""
Prompt and tonality tools for user customization.

These tools allow users to customize their chat experience
by setting tonality preferences for chat and content generation.
"""

from typing import Optional, List
from langchain_core.tools import tool
import json
import logging

logger = logging.getLogger("uvicorn")


# =============================================================================
# Tonality Tools (Reader+)
# =============================================================================

@tool
def get_tonalities() -> str:
    """
    Get available tonality options for chat and content.

    Use this tool to show users the available tonality
    settings they can choose from.

    Returns:
        JSON string with available tonality options
    """
    try:
        from database import SessionLocal
        from models import Tonality

        db = SessionLocal()
        try:
            tonalities = db.query(Tonality).filter(
                Tonality.active == True
            ).order_by(Tonality.name).all()

            formatted = [
                {
                    "id": t.id,
                    "name": t.name,
                    "description": t.description,
                    "can_be_chat_tonality": t.can_be_chat_tonality,
                    "can_be_content_tonality": t.can_be_content_tonality,
                }
                for t in tonalities
            ]

            return json.dumps({
                "success": True,
                "message": f"Found {len(formatted)} available tonalities",
                "tonalities": formatted,
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error getting tonalities: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error getting tonalities: {str(e)}",
            "tonalities": [],
        })


@tool
def get_user_tonality_settings(user_id: int) -> str:
    """
    Get current tonality settings for a user.

    Use this tool to see what tonality preferences
    a user has currently set.

    Args:
        user_id: The user's ID

    Returns:
        JSON string with user's current tonality settings
    """
    try:
        from database import SessionLocal
        from models import User

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                return json.dumps({
                    "success": False,
                    "message": f"User {user_id} not found",
                })

            chat_tonality = None
            content_tonality = None

            if user.chat_tonality:
                chat_tonality = {
                    "id": user.chat_tonality.id,
                    "name": user.chat_tonality.name,
                    "text": user.chat_tonality.tonality_text,
                }

            if user.content_tonality:
                content_tonality = {
                    "id": user.content_tonality.id,
                    "name": user.content_tonality.name,
                    "text": user.content_tonality.tonality_text,
                }

            return json.dumps({
                "success": True,
                "message": "Retrieved user tonality settings",
                "user_id": user_id,
                "chat_tonality": chat_tonality,
                "content_tonality": content_tonality,
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error getting user tonality settings: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error getting settings: {str(e)}",
        })


@tool
def set_user_chat_tonality(
    user_id: int,
    tonality_id: int,
) -> str:
    """
    Set the chat tonality for a user.

    Use this tool to update a user's chat conversation style.
    The tonality affects how the AI responds in conversations.

    Args:
        user_id: The user's ID
        tonality_id: ID of the tonality to set

    Returns:
        JSON string with result
    """
    try:
        from database import SessionLocal
        from models import User, Tonality

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                return json.dumps({
                    "success": False,
                    "message": f"User {user_id} not found",
                })

            tonality = db.query(Tonality).filter(
                Tonality.id == tonality_id,
                Tonality.active == True,
                Tonality.can_be_chat_tonality == True,
            ).first()

            if not tonality:
                return json.dumps({
                    "success": False,
                    "message": f"Tonality {tonality_id} not found or not available for chat",
                })

            user.chat_tonality_id = tonality_id
            db.commit()

            return json.dumps({
                "success": True,
                "message": f"Chat tonality set to '{tonality.name}'",
                "user_id": user_id,
                "tonality_id": tonality_id,
                "tonality_name": tonality.name,
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error setting chat tonality: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error setting tonality: {str(e)}",
        })


@tool
def set_user_content_tonality(
    user_id: int,
    tonality_id: int,
) -> str:
    """
    Set the content tonality for a user.

    Use this tool to update a user's content generation style.
    The tonality affects how articles and reports are written.

    Args:
        user_id: The user's ID
        tonality_id: ID of the tonality to set

    Returns:
        JSON string with result
    """
    try:
        from database import SessionLocal
        from models import User, Tonality

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                return json.dumps({
                    "success": False,
                    "message": f"User {user_id} not found",
                })

            tonality = db.query(Tonality).filter(
                Tonality.id == tonality_id,
                Tonality.active == True,
                Tonality.can_be_content_tonality == True,
            ).first()

            if not tonality:
                return json.dumps({
                    "success": False,
                    "message": f"Tonality {tonality_id} not found or not available for content",
                })

            user.content_tonality_id = tonality_id
            db.commit()

            return json.dumps({
                "success": True,
                "message": f"Content tonality set to '{tonality.name}'",
                "user_id": user_id,
                "tonality_id": tonality_id,
                "tonality_name": tonality.name,
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error setting content tonality: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error setting tonality: {str(e)}",
        })


@tool
def clear_user_tonality(
    user_id: int,
    tonality_type: str,
) -> str:
    """
    Clear a user's tonality setting.

    Use this tool to reset a tonality preference to default.

    Args:
        user_id: The user's ID
        tonality_type: Type to clear ("chat" or "content")

    Returns:
        JSON string with result
    """
    try:
        from database import SessionLocal
        from models import User

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                return json.dumps({
                    "success": False,
                    "message": f"User {user_id} not found",
                })

            if tonality_type == "chat":
                user.chat_tonality_id = None
                message = "Chat tonality cleared"
            elif tonality_type == "content":
                user.content_tonality_id = None
                message = "Content tonality cleared"
            else:
                return json.dumps({
                    "success": False,
                    "message": f"Invalid tonality type: {tonality_type}. Use 'chat' or 'content'",
                })

            db.commit()

            return json.dumps({
                "success": True,
                "message": message,
                "user_id": user_id,
                "tonality_type": tonality_type,
            })

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error clearing tonality: {e}")
        return json.dumps({
            "success": False,
            "message": f"Error clearing tonality: {str(e)}",
        })


# =============================================================================
# Tool Collections
# =============================================================================

def get_tonality_query_tools() -> List:
    """Get tonality query tools (Reader+)."""
    return [
        get_tonalities,
        get_user_tonality_settings,
    ]


def get_tonality_update_tools() -> List:
    """Get tonality update tools (Reader+)."""
    return [
        set_user_chat_tonality,
        set_user_content_tonality,
        clear_user_tonality,
    ]


def get_all_prompt_tools() -> List:
    """Get all prompt/tonality tools."""
    return get_tonality_query_tools() + get_tonality_update_tools()
