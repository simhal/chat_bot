"""
Factory Boy factories for generating test data.

Usage:
    from tests.fixtures.factories import UserFactory, TopicFactory

    # Create a user
    user = UserFactory()

    # Create with specific attributes
    user = UserFactory(email="custom@test.com", name="Custom")

    # Create multiple
    users = UserFactory.create_batch(5)
"""
import factory
from factory import Faker, LazyAttribute, SubFactory, post_generation
from datetime import datetime, timezone
import json

from models import (
    User, Group, Topic, ContentArticle, ContentRating,
    PromptModule, PromptTemplate, Resource, FileResource,
    TextResource, TableResource, ApprovalRequest,
    ArticleStatus, ResourceType, ResourceStatus,
    PromptType, ApprovalStatus,
)


class BaseFactory(factory.Factory):
    """Base factory with common configuration."""

    class Meta:
        abstract = True


# =============================================================================
# USER AND GROUP FACTORIES
# =============================================================================

class UserFactory(BaseFactory):
    """Factory for creating User instances."""

    class Meta:
        model = User

    email = Faker("email")
    name = Faker("first_name")
    surname = Faker("last_name")
    linkedin_sub = LazyAttribute(lambda o: f"linkedin_{o.email.replace('@', '_').replace('.', '_')}")
    picture = Faker("image_url")
    active = True
    access_count = 0


class GroupFactory(BaseFactory):
    """Factory for creating Group instances."""

    class Meta:
        model = Group

    name = LazyAttribute(lambda o: f"{o.groupname}:{o.role}")
    groupname = Faker("word")
    role = factory.Iterator(["reader", "analyst", "editor", "admin"])
    description = Faker("sentence")


# =============================================================================
# TOPIC FACTORIES
# =============================================================================

class TopicFactory(BaseFactory):
    """Factory for creating Topic instances."""

    class Meta:
        model = Topic

    slug = Faker("slug")
    title = Faker("catch_phrase")
    description = Faker("paragraph")
    visible = True
    searchable = True
    active = True
    reader_count = 0
    article_count = 0
    agent_type = None
    access_mainchat = True
    icon = None
    color = None
    sort_order = factory.Sequence(lambda n: n)
    article_order = "date"


# =============================================================================
# CONTENT FACTORIES
# =============================================================================

class ContentArticleFactory(BaseFactory):
    """Factory for creating ContentArticle instances."""

    class Meta:
        model = ContentArticle

    headline = Faker("sentence", nb_words=8)
    author = Faker("name")
    editor = None
    status = ArticleStatus.DRAFT
    keywords = LazyAttribute(lambda o: ", ".join(Faker._get_faker().words(nb=5)))
    readership_count = 0
    rating = None
    rating_count = 0
    priority = 0
    is_sticky = False
    created_by_agent = "test_factory"
    is_active = True

    # Topic relationship - set topic_id and topic string
    topic_id = None
    topic = None


class ContentRatingFactory(BaseFactory):
    """Factory for creating ContentRating instances."""

    class Meta:
        model = ContentRating

    rating = factory.Iterator([1, 2, 3, 4, 5])


class ApprovalRequestFactory(BaseFactory):
    """Factory for creating ApprovalRequest instances."""

    class Meta:
        model = ApprovalRequest

    status = ApprovalStatus.PENDING
    editor_notes = Faker("sentence")
    review_notes = None


# =============================================================================
# PROMPT FACTORIES
# =============================================================================

class PromptModuleFactory(BaseFactory):
    """Factory for creating PromptModule instances."""

    class Meta:
        model = PromptModule

    name = Faker("catch_phrase")
    prompt_type = PromptType.GENERAL
    prompt_group = None
    template_text = Faker("paragraph", nb_sentences=5)
    description = Faker("sentence")
    is_default = False
    sort_order = factory.Sequence(lambda n: n)
    is_active = True
    version = 1


class TonalityFactory(PromptModuleFactory):
    """Factory for creating tonality PromptModule instances."""

    prompt_type = PromptType.TONALITY
    name = factory.Iterator([
        "Professional",
        "Casual",
        "Technical",
        "Educational",
        "Formal",
    ])
    template_text = factory.Iterator([
        "Respond in a professional, business-like manner.",
        "Respond in a casual, friendly manner.",
        "Respond with technical precision and detail.",
        "Respond in an educational, instructive manner.",
        "Respond in a formal, academic manner.",
    ])


# =============================================================================
# RESOURCE FACTORIES
# =============================================================================

class ResourceFactory(BaseFactory):
    """Factory for creating Resource instances."""

    class Meta:
        model = Resource

    resource_type = ResourceType.TEXT
    status = ResourceStatus.DRAFT
    name = Faker("file_name")
    description = Faker("sentence")
    is_active = True


class TextResourceFactory(BaseFactory):
    """Factory for creating TextResource instances."""

    class Meta:
        model = TextResource

    content = Faker("paragraph", nb_sentences=10)
    encoding = "utf-8"
    char_count = LazyAttribute(lambda o: len(o.content))
    word_count = LazyAttribute(lambda o: len(o.content.split()))


class TableResourceFactory(BaseFactory):
    """Factory for creating TableResource instances."""

    class Meta:
        model = TableResource

    table_data = LazyAttribute(lambda o: json.dumps({
        "data": [
            ["A1", "B1", "C1"],
            ["A2", "B2", "C2"],
            ["A3", "B3", "C3"],
        ]
    }))
    row_count = 3
    column_count = 3
    column_names = '["Column A", "Column B", "Column C"]'


class FileResourceFactory(BaseFactory):
    """Factory for creating FileResource instances."""

    class Meta:
        model = FileResource

    filename = Faker("file_name", extension="pdf")
    file_path = LazyAttribute(lambda o: f"uploads/test/{o.filename}")
    file_size = factory.Faker("random_int", min=1000, max=1000000)
    mime_type = "application/pdf"
    checksum = Faker("sha256")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_user_with_role(db_session, role: str, topic_slug: str = None) -> User:
    """
    Create a user with a specific role.

    Args:
        db_session: Database session
        role: One of 'reader', 'analyst', 'editor', 'admin'
        topic_slug: Topic slug for topic-specific roles (not needed for global:admin)

    Returns:
        User instance with the specified role
    """
    user = UserFactory.build()
    db_session.add(user)
    db_session.flush()

    if role == "admin" and topic_slug is None:
        # Global admin
        group = GroupFactory.build(
            name="global:admin",
            groupname="global",
            role="admin"
        )
    else:
        group = GroupFactory.build(
            name=f"{topic_slug}:{role}",
            groupname=topic_slug,
            role=role
        )

    db_session.add(group)
    db_session.flush()

    user.groups.append(group)
    db_session.flush()

    return user


def create_article_with_status(
    db_session,
    topic: Topic,
    status: ArticleStatus,
    author: User = None,
    editor: User = None,
) -> ContentArticle:
    """
    Create an article with a specific status.

    Args:
        db_session: Database session
        topic: Topic for the article
        status: Article status
        author: Optional author user
        editor: Optional editor user

    Returns:
        ContentArticle instance
    """
    article = ContentArticleFactory.build(
        topic_id=topic.id,
        topic=topic.slug,
        status=status,
        author=f"{author.name} {author.surname}" if author else "Test Author",
        editor=f"{editor.name} {editor.surname}" if editor and status in [ArticleStatus.PUBLISHED, ArticleStatus.EDITOR] else None,
    )
    db_session.add(article)
    db_session.flush()
    return article
