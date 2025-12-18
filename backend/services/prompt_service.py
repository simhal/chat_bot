"""Service for loading and composing modular prompt templates."""

from typing import Optional, List, Dict
from functools import lru_cache
from sqlalchemy.orm import Session
from models import PromptModule, PromptType, User
from database import SessionLocal
import threading
import logging

logger = logging.getLogger("uvicorn")


class PromptService:
    """
    Service for loading and composing modular prompt templates.

    Prompt composition:
    - Chat Agent: general + chat_specific + tonality (user selected) + chat_constraint
    - Content Agent: general + content_topic (per topic) + tonality (user selected) + article_constraint

    Permission model:
    - general, chat_specific, chat_constraint, article_constraint, tonality: global:admin only
    - content_topic: {topic}:admin can edit their topic's prompts
    - Users can only SELECT which tonality to use (not edit)
    """

    # Thread-safe cache invalidation lock
    _cache_lock = threading.Lock()

    # =========================================================================
    # MODULAR PROMPT RETRIEVAL
    # =========================================================================

    @staticmethod
    @lru_cache(maxsize=32)
    def _get_prompt_module_cached(prompt_type: str, prompt_group: Optional[str] = None) -> Optional[str]:
        """
        Get a single prompt module by type and optional group.
        Returns the active, default template text.
        """
        db = SessionLocal()
        try:
            query = db.query(PromptModule).filter(
                PromptModule.prompt_type == prompt_type,
                PromptModule.is_active == True
            )

            if prompt_group:
                query = query.filter(PromptModule.prompt_group == prompt_group)

            # Get the default one, or first active if no default
            template = query.filter(PromptModule.is_default == True).first()
            if not template:
                template = query.order_by(PromptModule.sort_order).first()

            return template.template_text if template else None
        finally:
            db.close()

    @staticmethod
    @lru_cache(maxsize=64)
    def _get_user_tonality_cached(user_id: int, tonality_type: str) -> Optional[str]:
        """
        Get user's selected tonality prompt text.
        tonality_type: 'chat' or 'content'
        """
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return None

            if tonality_type == 'chat' and user.chat_tonality_id:
                tonality = db.query(PromptModule).filter(
                    PromptModule.id == user.chat_tonality_id,
                    PromptModule.is_active == True
                ).first()
                return tonality.template_text if tonality else None

            elif tonality_type == 'content' and user.content_tonality_id:
                tonality = db.query(PromptModule).filter(
                    PromptModule.id == user.content_tonality_id,
                    PromptModule.is_active == True
                ).first()
                return tonality.template_text if tonality else None

            return None
        finally:
            db.close()

    # =========================================================================
    # COMPOSED PROMPTS FOR AGENTS
    # =========================================================================

    @staticmethod
    def get_chat_system_prompt(user_id: Optional[int] = None) -> str:
        """
        Compose the full chat agent system prompt.

        Composition: general + chat_specific + tonality (user) + chat_constraint

        Args:
            user_id: Optional user ID for tonality selection

        Returns:
            Composed system prompt string
        """
        with PromptService._cache_lock:
            # Get each module
            general = PromptService._get_prompt_module_cached(PromptType.GENERAL.value)
            chat_specific = PromptService._get_prompt_module_cached(PromptType.CHAT_SPECIFIC.value)
            chat_constraint = PromptService._get_prompt_module_cached(PromptType.CHAT_CONSTRAINT.value)

            # Get user tonality or default
            tonality = None
            if user_id:
                tonality = PromptService._get_user_tonality_cached(user_id, 'chat')
            if not tonality:
                tonality = PromptService._get_prompt_module_cached(PromptType.TONALITY.value)

        # Compose with fallbacks
        parts = []
        if general:
            parts.append(general)
        else:
            parts.append(PromptService._get_default_general_prompt())

        if chat_specific:
            parts.append(chat_specific)

        if tonality:
            parts.append(tonality)

        if chat_constraint:
            parts.append(chat_constraint)
        else:
            parts.append(PromptService._get_default_chat_constraint())

        return "\n\n".join(parts)

    @staticmethod
    def get_content_system_prompt(topic: str, user_id: Optional[int] = None) -> str:
        """
        Compose the full content agent system prompt for a specific topic.

        Composition: general + content_topic (for topic) + tonality (user) + article_constraint

        Args:
            topic: Topic type (macro, equity, fixed_income, esg)
            user_id: Optional user ID for tonality selection

        Returns:
            Composed system prompt string
        """
        with PromptService._cache_lock:
            # Get each module
            general = PromptService._get_prompt_module_cached(PromptType.GENERAL.value)
            content_topic = PromptService._get_prompt_module_cached(PromptType.CONTENT_TOPIC.value, topic)
            article_constraint = PromptService._get_prompt_module_cached(PromptType.ARTICLE_CONSTRAINT.value)

            # Get user tonality or default
            tonality = None
            if user_id:
                tonality = PromptService._get_user_tonality_cached(user_id, 'content')
            if not tonality:
                tonality = PromptService._get_prompt_module_cached(PromptType.TONALITY.value)

        # Compose with fallbacks
        parts = []
        if general:
            parts.append(general)
        else:
            parts.append(PromptService._get_default_general_prompt())

        if content_topic:
            parts.append(content_topic)
        else:
            parts.append(PromptService._get_default_content_topic_prompt(topic))

        if tonality:
            parts.append(tonality)

        if article_constraint:
            parts.append(article_constraint)
        else:
            parts.append(PromptService._get_default_article_constraint())

        return "\n\n".join(parts)

    # =========================================================================
    # BACKWARD COMPATIBILITY (Legacy methods)
    # =========================================================================

    @staticmethod
    def get_main_chat_template(user_id: Optional[int] = None, template_name: str = "default") -> str:
        """
        BACKWARD COMPATIBLE: Get main chat agent template.
        Now uses the modular prompt composition.
        """
        return PromptService.get_chat_system_prompt(user_id)

    @staticmethod
    def get_content_agent_template(agent_type: str, template_name: str = "default") -> str:
        """
        BACKWARD COMPATIBLE: Get content agent template.
        Now uses the modular prompt composition.
        """
        return PromptService.get_content_system_prompt(agent_type)

    # =========================================================================
    # TONALITY MANAGEMENT
    # =========================================================================

    @staticmethod
    def get_available_tonalities(db: Session) -> List[Dict]:
        """
        Get all available tonality options for user selection.

        Returns:
            List of tonality dicts with id, name, description, is_default
        """
        tonalities = db.query(PromptModule).filter(
            PromptModule.prompt_type == PromptType.TONALITY.value,
            PromptModule.is_active == True
        ).order_by(PromptModule.sort_order).all()

        return [{
            'id': t.id,
            'name': t.name,
            'description': t.description,
            'prompt_group': t.prompt_group,
            'is_default': t.is_default
        } for t in tonalities]

    @staticmethod
    def set_user_tonality(db: Session, user_id: int, chat_tonality_id: Optional[int], content_tonality_id: Optional[int]) -> bool:
        """
        Set user's tonality preferences.

        Args:
            db: Database session
            user_id: User ID
            chat_tonality_id: ID of tonality for chat (or None for default)
            content_tonality_id: ID of tonality for content (or None for default)

        Returns:
            True if successful
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        # Validate tonality IDs if provided
        if chat_tonality_id:
            tonality = db.query(PromptModule).filter(
                PromptModule.id == chat_tonality_id,
                PromptModule.prompt_type == PromptType.TONALITY.value,
                PromptModule.is_active == True
            ).first()
            if not tonality:
                raise ValueError(f"Invalid chat_tonality_id: {chat_tonality_id}")

        if content_tonality_id:
            tonality = db.query(PromptModule).filter(
                PromptModule.id == content_tonality_id,
                PromptModule.prompt_type == PromptType.TONALITY.value,
                PromptModule.is_active == True
            ).first()
            if not tonality:
                raise ValueError(f"Invalid content_tonality_id: {content_tonality_id}")

        user.chat_tonality_id = chat_tonality_id
        user.content_tonality_id = content_tonality_id
        db.commit()

        # Invalidate user tonality cache
        PromptService.invalidate_user_cache(user_id)

        return True

    @staticmethod
    def get_user_tonality_preferences(db: Session, user_id: int) -> Dict:
        """
        Get user's current tonality preferences.

        Returns:
            Dict with chat_tonality and content_tonality (full objects or None)
        """
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {'chat_tonality': None, 'content_tonality': None}

        result = {'chat_tonality': None, 'content_tonality': None}

        if user.chat_tonality_id:
            tonality = db.query(PromptModule).filter(
                PromptModule.id == user.chat_tonality_id
            ).first()
            if tonality:
                result['chat_tonality'] = {
                    'id': tonality.id,
                    'name': tonality.name,
                    'description': tonality.description
                }

        if user.content_tonality_id:
            tonality = db.query(PromptModule).filter(
                PromptModule.id == user.content_tonality_id
            ).first()
            if tonality:
                result['content_tonality'] = {
                    'id': tonality.id,
                    'name': tonality.name,
                    'description': tonality.description
                }

        return result

    # =========================================================================
    # PROMPT MODULE MANAGEMENT (for Admin UI)
    # =========================================================================

    @staticmethod
    def get_prompt_modules(db: Session, prompt_type: Optional[str] = None, prompt_group: Optional[str] = None) -> List[Dict]:
        """
        Get prompt modules for admin management.

        Args:
            db: Database session
            prompt_type: Optional filter by type
            prompt_group: Optional filter by group

        Returns:
            List of prompt module dicts
        """
        query = db.query(PromptModule)

        if prompt_type:
            query = query.filter(PromptModule.prompt_type == prompt_type)
        if prompt_group:
            query = query.filter(PromptModule.prompt_group == prompt_group)

        modules = query.order_by(PromptModule.prompt_type, PromptModule.sort_order).all()

        return [{
            'id': m.id,
            'name': m.name,
            'prompt_type': m.prompt_type.value if hasattr(m.prompt_type, 'value') else m.prompt_type,
            'prompt_group': m.prompt_group,
            'template_text': m.template_text,
            'description': m.description,
            'is_default': m.is_default,
            'sort_order': m.sort_order,
            'is_active': m.is_active,
            'version': m.version,
            'created_at': m.created_at.isoformat() if m.created_at else None,
            'updated_at': m.updated_at.isoformat() if m.updated_at else None
        } for m in modules]

    @staticmethod
    def update_prompt_module(
        db: Session,
        module_id: int,
        template_text: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        updated_by: Optional[int] = None
    ) -> Dict:
        """
        Update a prompt module.

        Args:
            db: Database session
            module_id: ID of module to update
            template_text: New template text
            name: Optional new name
            description: Optional new description
            is_active: Optional active status
            updated_by: User ID who made the update

        Returns:
            Updated module dict
        """
        module = db.query(PromptModule).filter(PromptModule.id == module_id).first()
        if not module:
            raise ValueError(f"Prompt module not found: {module_id}")

        module.template_text = template_text
        module.version += 1
        module.updated_by = updated_by

        if name is not None:
            module.name = name
        if description is not None:
            module.description = description
        if is_active is not None:
            module.is_active = is_active

        db.commit()
        db.refresh(module)

        # Invalidate caches
        PromptService.invalidate_cache()

        return {
            'id': module.id,
            'name': module.name,
            'prompt_type': module.prompt_type.value if hasattr(module.prompt_type, 'value') else module.prompt_type,
            'prompt_group': module.prompt_group,
            'template_text': module.template_text,
            'description': module.description,
            'is_active': module.is_active,
            'version': module.version
        }

    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================

    @staticmethod
    def invalidate_cache():
        """Invalidate all template caches."""
        with PromptService._cache_lock:
            PromptService._get_prompt_module_cached.cache_clear()
            PromptService._get_user_tonality_cached.cache_clear()

    @staticmethod
    def invalidate_user_cache(user_id: int):
        """Invalidate cache for a specific user."""
        # For now, clear all user tonality caches
        # A more sophisticated implementation could use a per-user cache
        with PromptService._cache_lock:
            PromptService._get_user_tonality_cached.cache_clear()

    # =========================================================================
    # DEFAULT FALLBACK PROMPTS
    # =========================================================================

    @staticmethod
    def _get_default_general_prompt() -> str:
        """Fallback general prompt if database is empty."""
        return """You are an Investment Research Coordinator producing objective, educational investment research.

Your role is to coordinate, consult, and synthesize research from specialized content agents and present structured research for informational purposes only.

IMPORTANT NOTICE – TECHNICAL PROTOTYPE
This system is a technical prototype provided solely for evaluation, testing, and demonstration purposes."""

    @staticmethod
    def _get_default_chat_constraint() -> str:
        """Fallback chat constraint if database is empty."""
        return """STRICT NON-ADVISORY REQUIREMENTS
- You must not provide investment advice, recommendations, forecasts, or opinions on what actions to take.
- You must not suggest buying, selling, holding, allocating, or timing any asset.

Disclaimer: This content is provided for informational and educational purposes only."""

    @staticmethod
    def _get_default_article_constraint() -> str:
        """Fallback article constraint if database is empty."""
        return """ARTICLE REQUIREMENTS
1. Write a clear, informative article (1000-2000 words)
2. Include a compelling headline
3. Use factual information from research
4. Cite sources where applicable

Format your response as:
HEADLINE: [Your headline]
KEYWORDS: [comma-separated keywords]
AUTHOR: [Author name]
CONTENT:
[Your article content]"""

    @staticmethod
    def _get_default_content_topic_prompt(topic: str) -> str:
        """Fallback content topic prompt if database is empty."""
        defaults = {
            "macro": "You are a macroeconomic content creator specializing in economic indicators, central bank policy, and global economics.",
            "equity": "You are an equity market content creator specializing in stock analysis, company fundamentals, and market trends.",
            "fixed_income": "You are a fixed income content creator specializing in bonds, yields, credit analysis, and debt markets.",
            "esg": "You are an ESG content creator specializing in environmental, social, and governance factors in investing."
        }
        return defaults.get(topic, "You are a financial content creator.")

    # =========================================================================
    # LEGACY DEFAULT TEMPLATES (Backward compatibility)
    # =========================================================================

    @staticmethod
    def get_default_main_chat_template() -> str:
        """DEPRECATED: Use get_chat_system_prompt() instead."""
        return PromptService.get_chat_system_prompt()

    @staticmethod
    def get_default_content_agent_template(agent_type: str) -> str:
        """DEPRECATED: Use get_content_system_prompt() instead."""
        return PromptService.get_content_system_prompt(agent_type)


class PromptValidator:
    """Validate prompt templates before saving."""

    @staticmethod
    def validate_template(
        template_type: str,
        template_text: str,
        prompt_group: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Validate prompt template.

        Args:
            template_type: Prompt type (general, chat_specific, content_topic, tonality, chat_constraint, article_constraint)
            template_text: Template text to validate
            prompt_group: Optional group (required for content_topic)

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check length
        if len(template_text) < 20:
            return False, "Template too short (minimum 20 characters)"

        if len(template_text) > 10000:
            return False, "Template too long (maximum 10000 characters)"

        # Validate template type
        valid_types = [t.value for t in PromptType]
        if template_type not in valid_types:
            return False, f"Invalid template_type. Must be one of: {valid_types}"

        # Validate content_topic requires prompt_group
        if template_type == PromptType.CONTENT_TOPIC.value:
            valid_groups = ["macro", "equity", "fixed_income", "esg"]
            if not prompt_group:
                return False, "prompt_group is required for content_topic templates"
            if prompt_group not in valid_groups:
                return False, f"Invalid prompt_group for content_topic. Must be one of: {valid_groups}"

        return True, None
