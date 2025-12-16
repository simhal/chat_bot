from sqlalchemy import Column, Integer, String, DateTime, Boolean, Table, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func
from datetime import datetime


class Base(DeclarativeBase):
    pass


# Association table for many-to-many relationship between User and Group
user_groups = Table(
    'user_groups',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('group_id', Integer, ForeignKey('groups.id', ondelete='CASCADE'), primary_key=True),
    Column('assigned_at', DateTime(timezone=True), server_default=func.now(), nullable=False)
)


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    surname = Column(String(255), nullable=True)
    linkedin_sub = Column(String(255), unique=True, index=True, nullable=False)
    picture = Column(String(512), nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Access tracking
    last_access_at = Column(DateTime(timezone=True), nullable=True)
    access_count = Column(Integer, default=0, nullable=False)

    # Custom user prompt for multi-agent system
    custom_prompt = Column(Text, nullable=True)

    # Relationship to groups
    groups = relationship('Group', secondary=user_groups, back_populates='users')

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', name='{self.name}')>"


class Group(Base):
    __tablename__ = 'groups'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationship to users
    users = relationship('User', secondary=user_groups, back_populates='groups')

    def __repr__(self):
        return f"<Group(id={self.id}, name='{self.name}')>"


class PromptTemplate(Base):
    """
    Prompt templates for multi-agent system.
    Supports two types:
    - 'main_chat': Main chat agent templates (can be global or user-specific)
    - 'content_agent': Content agent templates (macro, equity, fixed_income, esg) - admin only
    """
    __tablename__ = 'prompt_templates'

    id = Column(Integer, primary_key=True, index=True)

    # Template type: 'main_chat' or 'content_agent'
    template_type = Column(String(50), nullable=False, index=True)

    # Agent type: For content_agent type: macro, equity, fixed_income, esg
    # For main_chat type: this can be null or 'main'
    agent_type = Column(String(50), nullable=True, index=True)

    # Template name (e.g., "default", "global", "aggressive", "conservative")
    template_name = Column(String(100), nullable=False, default="default")

    # The actual prompt template text
    template_text = Column(Text, nullable=False)

    # Scope: 'global' or 'user'
    # For content_agent: always 'global' (admin-editable)
    # For main_chat: can be 'global' or 'user'
    scope = Column(String(20), nullable=False, default='global', index=True)

    # User ID for user-specific templates (only for main_chat with scope='user')
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)

    # Version tracking
    version = Column(Integer, nullable=False, default=1)

    # Active status
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Description/notes
    description = Column(String(500), nullable=True)

    # Relationships
    creator = relationship('User', foreign_keys=[created_by])
    user = relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f"<PromptTemplate(id={self.id}, type='{self.template_type}', agent='{self.agent_type}', scope='{self.scope}')>"


class AgentInteraction(Base):
    """Track agent interactions for analytics."""
    __tablename__ = 'agent_interactions'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    agent_type = Column(String(50), nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    routing_reason = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationship
    user = relationship('User')

    def __repr__(self):
        return f"<AgentInteraction(id={self.id}, user_id={self.user_id}, agent_type='{self.agent_type}')>"


class ContentArticle(Base):
    """
    Reusable content articles created by content agents.
    Each article is topic-specific and available to all users.
    """
    __tablename__ = 'content_articles'

    id = Column(Integer, primary_key=True, index=True)

    # Topic type: macro, equity, fixed_income, esg
    topic = Column(String(50), nullable=False, index=True)

    # Article headline/title
    headline = Column(String(500), nullable=False, index=True)

    # Article content (max 1000 words as per requirements)
    content = Column(Text, nullable=False)

    # Readership counter - incremented each time article is accessed
    readership_count = Column(Integer, default=0, nullable=False, index=True)

    # Content rating (average rating from users, 1-5 scale)
    rating = Column(Integer, nullable=True, index=True)

    # Number of ratings received
    rating_count = Column(Integer, default=0, nullable=False)

    # Keywords for searchability (comma-separated)
    keywords = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Creator tracking (which agent created this)
    created_by_agent = Column(String(50), nullable=False)

    # Active status (can be deactivated by admin)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    def __repr__(self):
        return f"<ContentArticle(id={self.id}, topic='{self.topic}', headline='{self.headline[:50]}...')>"


class ContentRating(Base):
    """
    User ratings for content articles.
    Prevents duplicate ratings from same user.
    """
    __tablename__ = 'content_ratings'

    id = Column(Integer, primary_key=True, index=True)

    article_id = Column(Integer, ForeignKey('content_articles.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)

    # Rating value (1-5)
    rating = Column(Integer, nullable=False)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    article = relationship('ContentArticle')
    user = relationship('User')

    # Unique constraint: one rating per user per article
    __table_args__ = (
        UniqueConstraint('article_id', 'user_id', name='uix_article_user_rating'),
    )

    def __repr__(self):
        return f"<ContentRating(id={self.id}, article_id={self.article_id}, user_id={self.user_id}, rating={self.rating})>"
