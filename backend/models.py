from sqlalchemy import Column, Integer, String, DateTime, Boolean, Table, ForeignKey, UniqueConstraint, Text, Enum, Float, Index, JSON
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
import secrets
import string


def generate_hash_id(length: int = 32) -> str:
    """Generate a URL-safe unique hash ID."""
    # Use a URL-safe alphabet (letters + digits, no confusing chars like 0/O, 1/l/I)
    alphabet = string.ascii_lowercase + string.digits
    # Remove potentially confusing characters
    alphabet = alphabet.replace('0', '').replace('o', '').replace('l', '').replace('1', '')
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class Base(DeclarativeBase):
    pass


class ResourceType(str, enum.Enum):
    """Resource type enum."""
    IMAGE = "image"
    PDF = "pdf"
    TEXT = "text"
    HTML = "html"  # Standalone HTML files (e.g., sortable tables)
    EXCEL = "excel"
    ZIP = "zip"
    CSV = "csv"
    TABLE = "table"
    TIMESERIES = "timeseries"
    ARTICLE = "article"  # Parent container for published article resources


class TimeseriesFrequency(str, enum.Enum):
    """Timeseries frequency enum."""
    TICK = "tick"
    MINUTE = "minute"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class TimeseriesDataType(str, enum.Enum):
    """Timeseries data value type enum."""
    FLOAT = "float"
    INTEGER = "integer"
    STRING = "string"


class ArticleStatus(str, enum.Enum):
    """Article status enum."""
    DRAFT = "draft"
    EDITOR = "editor"
    PENDING_APPROVAL = "pending_approval"  # Awaiting human approval for publishing
    PUBLISHED = "published"


class ApprovalStatus(str, enum.Enum):
    """Approval request status enum."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PromptType(str, enum.Enum):
    """Prompt module type enum."""
    GENERAL = "general"                    # Shared base prompt (global:admin only)
    CHAT_SPECIFIC = "chat_specific"        # Chat-specific additions (global:admin only)
    CONTENT_TOPIC = "content_topic"        # Topic-specific for content agents ({topic}:admin can edit)
    TONALITY = "tonality"                  # User-selectable tonality options (global:admin creates)
    CHAT_CONSTRAINT = "chat_constraint"    # Constraints for chat responses (global:admin only)
    ARTICLE_CONSTRAINT = "article_constraint"  # Constraints for article generation (global:admin only)


# Association table for many-to-many relationship between User and Group
user_groups = Table(
    'user_groups',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('group_id', Integer, ForeignKey('groups.id', ondelete='CASCADE'), primary_key=True),
    Column('assigned_at', DateTime(timezone=True), server_default=func.now(), nullable=False)
)


class Topic(Base):
    """
    Dynamic topic configuration for research domains.

    Topics define research categories (e.g., Macro, Equity, Fixed Income, ESG).
    Each topic automatically creates 4 groups: admin, analyst, editor, reader.
    """
    __tablename__ = 'topics'

    id = Column(Integer, primary_key=True, index=True)

    # URL-safe identifier (e.g., 'fixed_income', 'macro')
    slug = Column(String(50), unique=True, nullable=False, index=True)

    # Display title (e.g., 'Fixed Income Research', 'Macroeconomic Analysis')
    title = Column(String(200), nullable=False)

    # Description for the topic
    description = Column(Text, nullable=True)

    # Visibility settings
    visible = Column(Boolean, default=True, nullable=False, index=True)  # Show in navigation
    searchable = Column(Boolean, default=True, nullable=False)  # Include in search
    active = Column(Boolean, default=True, nullable=False, index=True)  # Main on/off switch

    # Aggregate statistics (updated periodically or on-demand)
    reader_count = Column(Integer, default=0, nullable=False)  # Total reads across articles
    rating_average = Column(Float, nullable=True)  # Average rating across articles
    article_count = Column(Integer, default=0, nullable=False)  # Number of articles

    # Agent configuration for multi-agent routing
    agent_type = Column(String(50), nullable=True)  # e.g., 'equity', 'economist', 'fixed_income', or custom
    agent_config = Column(JSON, nullable=True)  # Custom agent configuration (tools, prompts, etc.)

    # Main chat integration - if True, main chat agent can query this topic's content agent
    access_mainchat = Column(Boolean, default=True, nullable=False)

    # UI customization
    icon = Column(String(50), nullable=True)  # Icon name or emoji
    color = Column(String(20), nullable=True)  # Hex color code
    sort_order = Column(Integer, default=0, nullable=False, index=True)  # Display order

    # Article ordering: 'date' (newest first), 'priority' (highest first), 'title' (alphabetical)
    article_order = Column(String(20), default='date', nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    groups = relationship('Group', back_populates='topic', cascade='all, delete-orphan')
    articles = relationship('ContentArticle', back_populates='topic_ref')

    def __repr__(self):
        return f"<Topic(id={self.id}, slug='{self.slug}', title='{self.title}')>"


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

    # Custom user prompt for multi-agent system (DEPRECATED - use tonality selection)
    custom_prompt = Column(Text, nullable=True)

    # User-selected tonality for chat responses (FK to PromptModule with type=tonality)
    chat_tonality_id = Column(Integer, ForeignKey('prompt_modules.id', ondelete='SET NULL', name='fk_users_chat_tonality'), nullable=True)

    # User-selected tonality for content/article generation (FK to PromptModule with type=tonality)
    content_tonality_id = Column(Integer, ForeignKey('prompt_modules.id', ondelete='SET NULL', name='fk_users_content_tonality'), nullable=True)

    # Relationship to groups
    groups = relationship('Group', secondary=user_groups, back_populates='users')

    # Relationships to tonality prompts
    chat_tonality = relationship('PromptModule', foreign_keys=[chat_tonality_id])
    content_tonality = relationship('PromptModule', foreign_keys=[content_tonality_id])

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', name='{self.name}')>"


class Group(Base):
    __tablename__ = 'groups'
    __table_args__ = (
        UniqueConstraint('groupname', 'role', name='uq_groups_groupname_role'),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)  # Format: "groupname:role"
    groupname = Column(String(100), index=True, nullable=False)  # macro, equity, fixed_income, esg, global
    role = Column(String(50), index=True, nullable=False)  # analyst, admin, reader, editor
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Foreign key to Topic (nullable for global groups)
    topic_id = Column(Integer, ForeignKey('topics.id', ondelete='CASCADE'), nullable=True, index=True)

    # Relationships
    users = relationship('User', secondary=user_groups, back_populates='groups')
    topic = relationship('Topic', back_populates='groups')

    def __repr__(self):
        return f"<Group(id={self.id}, name='{self.name}', groupname='{self.groupname}', role='{self.role}')>"


class PromptModule(Base):
    """
    Modular prompt templates for composable agent system prompts.

    Prompt composition:
    - Chat Agent: general + chat_specific + tonality (user selected) + chat_constraint
    - Content Agent: general + content_topic (per topic) + tonality (user selected) + article_constraint

    Permission model:
    - general, chat_specific, chat_constraint, article_constraint, tonality: global:admin only
    - content_topic: {topic}:admin can edit their topic's prompts
    - Users can only SELECT which tonality to use (not edit)
    """
    __tablename__ = 'prompt_modules'

    id = Column(Integer, primary_key=True, index=True)

    # Display name (e.g., "Professional Tone", "Base Investment Research Prompt")
    name = Column(String(200), nullable=False, index=True)

    # Prompt type - determines how this module is used
    prompt_type = Column(
        Enum(PromptType, values_callable=lambda x: [e.value for e in x], name='prompt_type_enum', create_type=False),
        nullable=False,
        index=True
    )

    # Prompt group - for content_topic type: macro, equity, fixed_income, esg
    # For tonality: can be used for categorization (e.g., "formal", "casual")
    # For others: typically null
    prompt_group = Column(String(50), nullable=True, index=True)

    # The actual prompt text
    template_text = Column(Text, nullable=False)

    # Description for admin UI
    description = Column(String(500), nullable=True)

    # Is this the default option (for tonality selection)
    is_default = Column(Boolean, default=False, nullable=False, index=True)

    # Sort order for UI display (especially for tonality options)
    sort_order = Column(Integer, default=0, nullable=False)

    # Active status
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Version tracking for audit
    version = Column(Integer, nullable=False, default=1)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL', name='fk_prompt_modules_created_by'), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    updated_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL', name='fk_prompt_modules_updated_by'), nullable=True)

    # Relationships
    creator = relationship('User', foreign_keys=[created_by])
    updater = relationship('User', foreign_keys=[updated_by])

    def __repr__(self):
        return f"<PromptModule(id={self.id}, name='{self.name}', type='{self.prompt_type}', group='{self.prompt_group}')>"


class PromptTemplate(Base):
    """
    DEPRECATED: Legacy prompt templates table.
    Kept for backwards compatibility during migration.
    Use PromptModule for new implementations.
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

    NOTE: Article content (1000-2000 words) is stored in ChromaDB vector database.
    This table only contains metadata for linking with users and tracking stats.
    """
    __tablename__ = 'content_articles'

    id = Column(Integer, primary_key=True, index=True)

    # Topic - foreign key to topics table
    topic_id = Column(Integer, ForeignKey('topics.id', ondelete='SET NULL'), nullable=True, index=True)

    # Legacy topic string (kept for backwards compatibility, will be deprecated)
    topic = Column(String(50), nullable=True, index=True)

    # Article headline/title
    headline = Column(String(500), nullable=False, index=True)

    # Author name
    author = Column(String(255), nullable=True, index=True)

    # Editor name
    editor = Column(String(255), nullable=True, index=True)

    # Article status: draft, editor, or published
    status = Column(
        Enum(ArticleStatus, values_callable=lambda x: [e.value for e in x], name='article_status', create_type=False),
        nullable=False,
        default=ArticleStatus.DRAFT,
        index=True
    )

    # Article content is stored in ChromaDB (not in PostgreSQL)

    # Readership counter - incremented each time article is accessed
    readership_count = Column(Integer, default=0, nullable=False, index=True)

    # Content rating (average rating from users, 1-5 scale)
    rating = Column(Integer, nullable=True, index=True)

    # Number of ratings received
    rating_count = Column(Integer, default=0, nullable=False)

    # Keywords for searchability (comma-separated)
    keywords = Column(Text, nullable=True)

    # Priority for manual ordering (higher = more important)
    priority = Column(Integer, default=0, nullable=False, index=True)

    # Sticky flag - sticky articles always appear first, sorted by priority
    is_sticky = Column(Boolean, default=False, nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Creator tracking (which agent created this)
    created_by_agent = Column(String(50), nullable=False)

    # Active status (can be deactivated by admin)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Relationship to Topic
    topic_ref = relationship('Topic', back_populates='articles')

    @property
    def topic_slug(self) -> str:
        """Get topic slug from relationship or legacy field."""
        if self.topic_ref:
            return self.topic_ref.slug
        return self.topic or ""

    def __repr__(self):
        return f"<ContentArticle(id={self.id}, topic='{self.topic_slug}', headline='{self.headline[:50]}...')>"


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


class ApprovalRequest(Base):
    """
    Human-in-the-loop approval requests for article publishing.

    When an editor submits an article for publishing, an approval request is
    created. The article enters PENDING_APPROVAL status until a human reviewer
    approves or rejects the request.
    """
    __tablename__ = 'approval_requests'

    id = Column(Integer, primary_key=True, index=True)

    # Article being approved
    article_id = Column(Integer, ForeignKey('content_articles.id', ondelete='CASCADE'), nullable=False, index=True)

    # Request details
    requested_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    editor_notes = Column(Text, nullable=True)

    # Status tracking
    status = Column(
        Enum(ApprovalStatus, values_callable=lambda x: [e.value for e in x], name='approval_status', create_type=False),
        default=ApprovalStatus.PENDING,
        nullable=False,
        index=True
    )

    # Review details (populated when reviewed)
    reviewed_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)

    # Expiration (optional - requests can expire after 24 hours)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # LangGraph workflow tracking
    thread_id = Column(String(255), nullable=True, index=True)  # For resuming interrupted workflows

    # Relationships
    article = relationship('ContentArticle', backref='approval_requests')
    requester = relationship('User', foreign_keys=[requested_by])
    reviewer = relationship('User', foreign_keys=[reviewed_by])

    def __repr__(self):
        return f"<ApprovalRequest(id={self.id}, article_id={self.article_id}, status={self.status.value})>"


# =============================================================================
# RESOURCE MANAGEMENT TABLES
# =============================================================================

# Association table for many-to-many relationship between Article and Resource
article_resources = Table(
    'article_resources',
    Base.metadata,
    Column('id', Integer, primary_key=True),
    Column('article_id', Integer, ForeignKey('content_articles.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('resource_id', Integer, ForeignKey('resources.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    UniqueConstraint('article_id', 'resource_id', name='uix_article_resource')
)


class ResourceStatus(str, enum.Enum):
    """Resource status enum (mirrors ArticleStatus for editorial workflow)."""
    DRAFT = "draft"
    EDITOR = "editor"
    PUBLISHED = "published"


class Resource(Base):
    """
    Base resource table with global ID and common metadata.

    Resource types and their storage:
    - IMAGE, PDF, EXCEL, ZIP, CSV: Metadata in Postgres, file on filesystem (S3/mounted share)
    - TEXT: Metadata in Postgres, content embedded in ChromaDB
    - TABLE: Metadata in Postgres, JSON content embedded in ChromaDB
    - TIMESERIES: All data in Postgres (metadata + time-indexed data)

    Relationships:
    - Can be linked to multiple articles (many-to-many)
    - Can optionally belong to one group (1:n for sharing)
    - Tracks created_by and modified_by users

    Editorial Workflow:
    - Resources follow same workflow as articles: draft -> editor -> published
    - Resources without article or group links are automatically purged
    """
    __tablename__ = 'resources'

    id = Column(Integer, primary_key=True, index=True)

    # URL-safe hash ID for public-facing links (e.g., /resource/{hash_id})
    hash_id = Column(String(64), unique=True, index=True, nullable=False, default=generate_hash_id)

    # Resource type determines which specialized table holds additional data
    resource_type = Column(
        Enum(ResourceType, values_callable=lambda x: [e.value for e in x], name='resource_type_enum', create_type=False),
        nullable=False,
        index=True
    )

    # Editorial workflow status (same as articles)
    status = Column(
        Enum(ResourceStatus, values_callable=lambda x: [e.value for e in x], name='resource_status_enum', create_type=False),
        nullable=False,
        default=ResourceStatus.DRAFT,
        index=True
    )

    # Display name
    name = Column(String(255), nullable=False, index=True)

    # Optional description
    description = Column(Text, nullable=True)

    # Optional group association for sharing (1:n - one group can have many resources)
    group_id = Column(Integer, ForeignKey('groups.id', ondelete='SET NULL'), nullable=True, index=True)

    # Parent resource (for parsed/derived resources, e.g., PDF -> text, images, tables)
    parent_id = Column(Integer, ForeignKey('resources.id', ondelete='CASCADE'), nullable=True, index=True)

    # User tracking
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    modified_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Active status
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    group = relationship('Group', backref='resources')
    creator = relationship('User', foreign_keys=[created_by], backref='created_resources')
    modifier = relationship('User', foreign_keys=[modified_by])
    articles = relationship('ContentArticle', secondary=article_resources, backref='resources')

    # Parent/children relationship (self-referential for derived resources)
    parent = relationship('Resource', remote_side=[id], backref='children', foreign_keys=[parent_id])

    # One-to-one relationships with specialized tables
    file_resource = relationship('FileResource', back_populates='resource', uselist=False, cascade='all, delete-orphan')
    text_resource = relationship('TextResource', back_populates='resource', uselist=False, cascade='all, delete-orphan')
    table_resource = relationship('TableResource', back_populates='resource', uselist=False, cascade='all, delete-orphan')
    timeseries_metadata = relationship('TimeseriesMetadata', back_populates='resource', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Resource(id={self.id}, type='{self.resource_type}', name='{self.name}')>"


class FileResource(Base):
    """
    File-based resources: images, PDFs, Excel files, ZIP files, CSV files.

    Actual files are stored on filesystem (S3 bucket or mounted share).
    This table stores metadata only.
    """
    __tablename__ = 'file_resources'

    id = Column(Integer, primary_key=True, index=True)

    # Link to base resource
    resource_id = Column(Integer, ForeignKey('resources.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)

    # Original filename
    filename = Column(String(500), nullable=False)

    # Relative path on filesystem (relative to configured base path)
    # e.g., "uploads/2024/01/uuid-filename.pdf"
    file_path = Column(String(1000), nullable=False, unique=True)

    # File size in bytes
    file_size = Column(Integer, nullable=False)

    # MIME type (e.g., "image/png", "application/pdf")
    mime_type = Column(String(100), nullable=False, index=True)

    # SHA-256 checksum for integrity verification
    checksum = Column(String(64), nullable=True, index=True)

    # Relationship
    resource = relationship('Resource', back_populates='file_resource')

    def __repr__(self):
        return f"<FileResource(id={self.id}, filename='{self.filename}', mime='{self.mime_type}')>"


class TextResource(Base):
    """
    Text file resources.

    Metadata stored in Postgres, content embedded in ChromaDB for semantic search.
    """
    __tablename__ = 'text_resources'

    id = Column(Integer, primary_key=True, index=True)

    # Link to base resource
    resource_id = Column(Integer, ForeignKey('resources.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)

    # Text content (stored here for backup, but also embedded in ChromaDB)
    content = Column(Text, nullable=False)

    # Text encoding
    encoding = Column(String(50), nullable=False, default='utf-8')

    # Character count
    char_count = Column(Integer, nullable=True)

    # Word count
    word_count = Column(Integer, nullable=True)

    # ChromaDB collection/document ID for vector embeddings
    chromadb_id = Column(String(100), nullable=True, index=True)

    # Relationship
    resource = relationship('Resource', back_populates='text_resource')

    def __repr__(self):
        return f"<TextResource(id={self.id}, chars={self.char_count}, words={self.word_count})>"


class TableResource(Base):
    """
    Table resources stored as JSON.

    For small tables where content can be embedded.
    Metadata in Postgres, content embedded in ChromaDB for semantic search.
    """
    __tablename__ = 'table_resources'

    id = Column(Integer, primary_key=True, index=True)

    # Link to base resource
    resource_id = Column(Integer, ForeignKey('resources.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)

    # Table data as JSON string
    # Format: {"columns": ["col1", "col2"], "data": [[val1, val2], [val3, val4]]}
    table_data = Column(Text, nullable=False)

    # Table dimensions
    row_count = Column(Integer, nullable=False)
    column_count = Column(Integer, nullable=False)

    # Column names as JSON array
    column_names = Column(Text, nullable=False)  # JSON array: ["col1", "col2", ...]

    # Column types as JSON object (optional)
    column_types = Column(Text, nullable=True)  # JSON object: {"col1": "string", "col2": "number"}

    # ChromaDB collection/document ID for vector embeddings
    chromadb_id = Column(String(100), nullable=True, index=True)

    # Relationship
    resource = relationship('Resource', back_populates='table_resource')

    @property
    def columns(self) -> list:
        """Get column names as a list."""
        import json
        if self.column_names:
            try:
                return json.loads(self.column_names)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @columns.setter
    def columns(self, value: list):
        """Set column names from a list."""
        import json
        self.column_names = json.dumps(value) if value else "[]"

    @property
    def data(self) -> list:
        """Get table data rows as a list."""
        import json
        if self.table_data:
            try:
                parsed = json.loads(self.table_data)
                if isinstance(parsed, dict):
                    return parsed.get("data", [])
                return parsed
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @data.setter
    def data(self, value: list):
        """Set table data rows from a list."""
        import json
        # Store as {"data": [...]} format for compatibility
        self.table_data = json.dumps({"data": value}) if value else '{"data": []}'

    def __repr__(self):
        return f"<TableResource(id={self.id}, rows={self.row_count}, cols={self.column_count})>"


class TimeseriesMetadata(Base):
    """
    Timeseries metadata.

    Describes a timeseries dataset with multiple columns/variables.
    Like a DataFrame with a time index.
    """
    __tablename__ = 'timeseries_metadata'

    id = Column(Integer, primary_key=True, index=True)  # tsid

    # Link to base resource
    resource_id = Column(Integer, ForeignKey('resources.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)

    # Timeseries name (e.g., "AAPL Stock Prices", "US GDP Growth")
    name = Column(String(255), nullable=False, index=True)

    # Data source (e.g., "Bloomberg", "FRED", "Yahoo Finance")
    source = Column(String(255), nullable=True, index=True)

    # Detailed description
    description = Column(Text, nullable=True)

    # Frequency
    frequency = Column(
        Enum(TimeseriesFrequency, values_callable=lambda x: [e.value for e in x], name='timeseries_freq_enum', create_type=False),
        nullable=False,
        index=True
    )

    # Data type of values
    data_type = Column(
        Enum(TimeseriesDataType, values_callable=lambda x: [e.value for e in x], name='timeseries_dtype_enum', create_type=False),
        nullable=False,
        default=TimeseriesDataType.FLOAT
    )

    # Column names as JSON array (e.g., ["open", "high", "low", "close", "volume"])
    columns = Column(Text, nullable=False)  # JSON array

    # Time range
    start_date = Column(DateTime(timezone=True), nullable=True, index=True)
    end_date = Column(DateTime(timezone=True), nullable=True, index=True)

    # Data point count
    data_point_count = Column(Integer, default=0, nullable=False)

    # Unit of measurement (e.g., "USD", "percent", "units")
    unit = Column(String(50), nullable=True)

    # Relationships
    resource = relationship('Resource', back_populates='timeseries_metadata')
    data_points = relationship('TimeseriesData', back_populates='timeseries', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<TimeseriesMetadata(id={self.id}, name='{self.name}', freq='{self.frequency}')>"


class TimeseriesData(Base):
    """
    Timeseries data points.

    Stores actual data values with revision tracking.
    Structure: tsid, date, column, value, revision_time

    This allows for:
    - Multiple columns per timestamp (like OHLCV data)
    - Revision tracking (when was this data point recorded/updated)
    """
    __tablename__ = 'timeseries_data'
    __table_args__ = (
        # Unique constraint: one value per timeseries, date, column, revision
        UniqueConstraint('tsid', 'date', 'column_name', 'revision_time', name='uix_ts_date_col_rev'),
        # Composite index for common queries
        Index('ix_tsdata_tsid_date', 'tsid', 'date'),
        Index('ix_tsdata_tsid_col', 'tsid', 'column_name'),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Link to timeseries metadata
    tsid = Column(Integer, ForeignKey('timeseries_metadata.id', ondelete='CASCADE'), nullable=False, index=True)

    # Timestamp of the data point
    date = Column(DateTime(timezone=True), nullable=False, index=True)

    # Column/variable name (e.g., "open", "close", "volume")
    column_name = Column(String(100), nullable=False, index=True)

    # Value (stored as float for flexibility; can represent integers too)
    # For string values, store in a separate column or use a different approach
    value = Column(Float, nullable=True)

    # String value (for timeseries with string data type)
    value_str = Column(String(500), nullable=True)

    # Revision timestamp (when this data point was recorded/revised)
    # Allows tracking historical revisions of data
    revision_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationship
    timeseries = relationship('TimeseriesMetadata', back_populates='data_points')

    def __repr__(self):
        return f"<TimeseriesData(tsid={self.tsid}, date={self.date}, col='{self.column_name}', val={self.value})>"
