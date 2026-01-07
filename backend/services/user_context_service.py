"""
User context service for building agent UserContext from JWT and database.

This module provides utilities to construct the UserContext TypedDict
used by agents for permission checking and personalization.
"""

from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from agents.state import UserContext, create_user_context


class UserContextService:
    """
    Service for building UserContext from various sources.

    Provides methods to construct UserContext from:
    - JWT payload + database lookup
    - User ID (for Celery tasks)
    - Raw dictionaries
    """

    @staticmethod
    def build(user: Dict[str, Any], db: Session) -> UserContext:
        """
        Build UserContext from JWT payload and database.

        Args:
            user: Dict containing JWT payload (from get_current_user dependency)
            db: Database session for loading user preferences

        Returns:
            Populated UserContext
        """
        from models import User

        # Support both 'user_id' and 'sub' (JWT standard claim)
        user_id = user.get("user_id") or user.get("sub")
        if not user_id:
            raise ValueError("user_id not found in JWT payload (checked 'user_id' and 'sub')")

        # Ensure user_id is an integer
        user_id = int(user_id)

        # Load user from database for preferences
        db_user = db.query(User).filter(User.id == user_id).first()

        # Get tonality preferences
        chat_tonality_text = None
        content_tonality_text = None

        if db_user:
            # Load chat tonality from user preferences
            if db_user.chat_tonality_id:
                from models import PromptModule
                chat_tonality = db.query(PromptModule).filter(
                    PromptModule.id == db_user.chat_tonality_id
                ).first()
                if chat_tonality:
                    chat_tonality_text = chat_tonality.content

            # Load content tonality from user preferences
            if db_user.content_tonality_id:
                from models import PromptModule
                content_tonality = db.query(PromptModule).filter(
                    PromptModule.id == db_user.content_tonality_id
                ).first()
                if content_tonality:
                    content_tonality_text = content_tonality.content

        # Extract scopes from JWT
        scopes = user.get("scopes", [])
        if isinstance(scopes, str):
            scopes = scopes.split(",") if scopes else []

        # Get user info - prefer JWT, fallback to database
        name = user.get("name") or (db_user.name if db_user else "") or ""
        surname = user.get("surname") or (db_user.surname if db_user else None)
        email = user.get("email") or (db_user.email if db_user else "") or ""
        picture = user.get("picture") or (db_user.picture if db_user else None)

        # Debug logging
        import logging
        logger = logging.getLogger("uvicorn")
        logger.info(f"🔐 UserContext build: user_id={user_id}, name='{name}', email='{email}'")
        logger.info(f"   JWT name: '{user.get('name')}', DB name: '{db_user.name if db_user else 'N/A'}'")
        logger.info(f"   Scopes: {scopes}")

        return create_user_context(
            user_id=user_id,
            email=email,
            name=name,
            scopes=scopes,
            surname=surname,
            picture=picture,
            chat_tonality_text=chat_tonality_text,
            content_tonality_text=content_tonality_text,
        )

    @staticmethod
    def build_from_id(user_id: int, db: Session) -> UserContext:
        """
        Build UserContext from user ID (for Celery tasks).

        Args:
            user_id: Database user ID
            db: Database session

        Returns:
            Populated UserContext
        """
        from models import User, Group

        # Load user from database
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        # Build scopes from group memberships
        scopes = UserContextService._get_user_scopes(user, db)

        # Get tonality preferences
        chat_tonality_text = None
        content_tonality_text = None

        if user.chat_tonality_id:
            from models import PromptModule
            chat_tonality = db.query(PromptModule).filter(
                PromptModule.id == user.chat_tonality_id
            ).first()
            if chat_tonality:
                chat_tonality_text = chat_tonality.content

        if user.content_tonality_id:
            from models import PromptModule
            content_tonality = db.query(PromptModule).filter(
                PromptModule.id == user.content_tonality_id
            ).first()
            if content_tonality:
                content_tonality_text = content_tonality.content

        return create_user_context(
            user_id=user.id,
            email=user.email,
            name=user.name,
            scopes=scopes,
            surname=user.surname,
            picture=user.picture,
            chat_tonality_text=chat_tonality_text,
            content_tonality_text=content_tonality_text,
        )

    @staticmethod
    def _get_user_scopes(user: Any, db: Session) -> List[str]:
        """
        Get permission scopes for a user from their group memberships.

        Args:
            user: User model instance
            db: Database session

        Returns:
            List of scope strings (e.g., ["macro:analyst", "equity:reader"])
        """
        from models import Group

        scopes = []

        # Get all groups the user belongs to
        groups = db.query(Group).filter(
            Group.users.contains(user)
        ).all()

        for group in groups:
            # Build scope from topic and role
            if group.topic_id:
                # Topic-scoped group
                topic = group.topic
                if topic:
                    scope = f"{topic.slug}:{group.role}"
                    scopes.append(scope)
            else:
                # Global group (no topic)
                scope = f"global:{group.role}"
                scopes.append(scope)

        # If no groups, default to reader
        if not scopes:
            scopes = ["global:reader"]

        return scopes

    @staticmethod
    def build_from_dict(data: Dict[str, Any]) -> UserContext:
        """
        Build UserContext from a dictionary (for testing or API use).

        Args:
            data: Dictionary with user context fields

        Returns:
            UserContext instance
        """
        return create_user_context(
            user_id=data.get("user_id", 0),
            email=data.get("email", ""),
            name=data.get("name", ""),
            scopes=data.get("scopes", ["global:reader"]),
            surname=data.get("surname"),
            picture=data.get("picture"),
            chat_tonality_text=data.get("chat_tonality_text"),
            content_tonality_text=data.get("content_tonality_text"),
        )

    @staticmethod
    def get_topic_role(context: UserContext, topic: str) -> Optional[str]:
        """
        Get user's role for a specific topic from UserContext.

        Args:
            context: UserContext instance
            topic: Topic slug

        Returns:
            Role name or None
        """
        # Check direct topic role
        if topic in context.get("topic_roles", {}):
            return context["topic_roles"][topic]

        # Check global role
        for scope in context.get("scopes", []):
            if scope.startswith("global:"):
                return scope.split(":", 1)[1]

        return None

    @staticmethod
    def has_permission(
        context: UserContext,
        required_role: str,
        topic: Optional[str] = None,
    ) -> bool:
        """
        Check if UserContext has required permission.

        Args:
            context: UserContext instance
            required_role: Required role level
            topic: Optional topic for topic-scoped check

        Returns:
            True if user has permission
        """
        from services.permission_service import PermissionService

        return PermissionService.check_permission(
            user_scopes=context.get("scopes", []),
            required_role=required_role,
            topic=topic,
        )
