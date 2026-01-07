"""
Celery task definitions for agent workflows.

These tasks run heavy agent workloads in background workers, allowing the
FastAPI server to remain responsive. Tasks communicate results back to
users via WebSocket notifications.
"""

from typing import Optional, Dict, Any, List
from celery import shared_task
from celery.result import AsyncResult

from celery_app import celery_app


def get_db_session():
    """Get a database session for Celery tasks."""
    from database import SessionLocal
    return SessionLocal()


def notify_user(user_id: int, message: Dict[str, Any]) -> None:
    """
    Send notification to user via Redis pub/sub.

    The WebSocket handler subscribes to user-specific channels and
    forwards messages to connected clients.
    """
    import json
    from redis_client import get_redis_client

    redis = get_redis_client()
    channel = f"user:{user_id}:notifications"
    redis.publish(channel, json.dumps(message))


@celery_app.task(bind=True, max_retries=3)
def analyst_research_task(
    self,
    user_id: int,
    topic: str,
    query: str,
    article_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Run AnalystAgent research workflow in background.

    This task:
    1. Builds user context from database
    2. Initializes AnalystAgent with sub-agents
    3. Performs research (web search, data download, resource query)
    4. Creates or updates article with findings
    5. Notifies user of completion via WebSocket

    Args:
        user_id: ID of the requesting user
        topic: Topic slug (macro, equity, fixed_income, esg)
        query: Research query from user
        article_id: Optional existing article to update

    Returns:
        Dict with status, article_id, resources_created, content_preview
    """
    db = get_db_session()

    try:
        # Import here to avoid circular imports
        from services.user_context_service import UserContextService
        from agents.analyst_agent import AnalystAgent
        from langchain_openai import ChatOpenAI
        import os

        # Build user context
        user_context = UserContextService.build_from_id(user_id, db)

        # Initialize LLM
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.7,
        )

        # Create and run agent
        agent = AnalystAgent(topic=topic, llm=llm, db=db)
        result = agent.research_and_write(
            query=query,
            article_id=article_id,
            user_context=user_context
        )

        # Notify user of completion
        notify_user(user_id, {
            "type": "task_complete",
            "task_type": "analyst_research",
            "task_id": self.request.id,
            "status": "completed",
            "result": {
                "article_id": result.get("article_id"),
                "headline": result.get("headline"),
                "resources_created": result.get("resources_created", []),
            }
        })

        return {
            "status": "completed",
            "article_id": result.get("article_id"),
            "resources_created": result.get("resources_created", []),
            "content_preview": result.get("content", "")[:500],
        }

    except Exception as e:
        # Notify user of failure
        notify_user(user_id, {
            "type": "task_failed",
            "task_type": "analyst_research",
            "task_id": self.request.id,
            "error": str(e),
        })
        raise

    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3)
def web_search_task(
    self,
    user_id: int,
    query: str,
    search_type: str = "general",
    max_results: int = 10
) -> Dict[str, Any]:
    """
    Perform web search in background.

    Args:
        user_id: ID of the requesting user
        query: Search query
        search_type: Type of search (general, news, financial_news)
        max_results: Maximum number of results

    Returns:
        Dict with search results
    """
    try:
        from agents.tools.web_search import create_web_search_tool

        search_tool = create_web_search_tool()
        results = search_tool.invoke({"query": query})

        notify_user(user_id, {
            "type": "task_complete",
            "task_type": "web_search",
            "task_id": self.request.id,
            "status": "completed",
            "result_count": len(results) if isinstance(results, list) else 1,
        })

        return {
            "status": "completed",
            "results": results,
        }

    except Exception as e:
        notify_user(user_id, {
            "type": "task_failed",
            "task_type": "web_search",
            "task_id": self.request.id,
            "error": str(e),
        })
        raise


@celery_app.task(bind=True, max_retries=3)
def data_download_task(
    self,
    user_id: int,
    data_type: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Download financial data in background.

    Args:
        user_id: ID of the requesting user
        data_type: Type of data (stock, economic, fx, treasury)
        params: Data-specific parameters (symbol, indicator, etc.)

    Returns:
        Dict with downloaded data
    """
    db = get_db_session()

    try:
        from agents.data_download_agent import DataDownloadAgent
        from langchain_openai import ChatOpenAI
        import os

        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
        )

        agent = DataDownloadAgent(llm=llm, db=db)
        result = agent.download_data(data_type=data_type, params=params)

        notify_user(user_id, {
            "type": "task_complete",
            "task_type": "data_download",
            "task_id": self.request.id,
            "status": "completed",
            "data_type": data_type,
        })

        return {
            "status": "completed",
            "data_type": data_type,
            "result": result,
        }

    except Exception as e:
        notify_user(user_id, {
            "type": "task_failed",
            "task_type": "data_download",
            "task_id": self.request.id,
            "error": str(e),
        })
        raise

    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3)
def article_query_task(
    self,
    user_id: int,
    topic: str,
    query: str,
    include_drafts: bool = False,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Search articles in background.

    Args:
        user_id: ID of the requesting user
        topic: Topic slug to search within
        query: Search query
        include_drafts: Whether to include draft articles
        limit: Maximum number of results

    Returns:
        Dict with article search results
    """
    db = get_db_session()

    try:
        from services.content_service import ContentService

        articles = ContentService.search_articles(
            db=db,
            topic=topic,
            query=query,
            limit=limit,
        )

        notify_user(user_id, {
            "type": "task_complete",
            "task_type": "article_query",
            "task_id": self.request.id,
            "status": "completed",
            "result_count": len(articles),
        })

        return {
            "status": "completed",
            "articles": [
                {
                    "id": a.get("id"),
                    "headline": a.get("headline"),
                    "status": a.get("status"),
                    "created_at": a.get("created_at"),
                }
                for a in articles
            ],
        }

    except Exception as e:
        notify_user(user_id, {
            "type": "task_failed",
            "task_type": "article_query",
            "task_id": self.request.id,
            "error": str(e),
        })
        raise

    finally:
        db.close()


@celery_app.task(bind=True, max_retries=1)
def editor_publish_task(
    self,
    user_id: int,
    article_id: int,
    editor_notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run EditorSubAgent publish workflow with HITL.

    This task initiates the human-in-the-loop publishing workflow:
    1. Validates article is in EDITOR status
    2. Creates approval request
    3. Transitions article to PENDING_APPROVAL
    4. Pauses workflow via LangGraph interrupt_before
    5. Waits for human approval via /api/approvals endpoint

    Args:
        user_id: ID of the requesting editor
        article_id: ID of the article to publish
        editor_notes: Optional notes from the editor

    Returns:
        Dict with approval request status and thread_id for resumption
    """
    db = get_db_session()

    try:
        from services.user_context_service import UserContextService
        from agents.editor_sub_agent import EditorSubAgent
        from langchain_openai import ChatOpenAI
        import os

        user_context = UserContextService.build_from_id(user_id, db)

        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
        )

        agent = EditorSubAgent(llm=llm, db=db)
        result = agent.submit_for_approval(
            article_id=article_id,
            user_context=user_context,
            editor_notes=editor_notes,
        )

        if result.get("status") == "awaiting_approval":
            # Notify user that approval is needed
            notify_user(user_id, {
                "type": "approval_required",
                "task_type": "editor_publish",
                "task_id": self.request.id,
                "article_id": article_id,
                "thread_id": result.get("thread_id"),
            })

            return {
                "status": "awaiting_approval",
                "article_id": article_id,
                "thread_id": result.get("thread_id"),
                "approval_request_id": result.get("approval_request_id"),
            }

        # Article was published (auto-approved case)
        notify_user(user_id, {
            "type": "task_complete",
            "task_type": "editor_publish",
            "task_id": self.request.id,
            "status": "published",
            "article_id": article_id,
        })

        return {
            "status": "published",
            "article_id": article_id,
        }

    except Exception as e:
        notify_user(user_id, {
            "type": "task_failed",
            "task_type": "editor_publish",
            "task_id": self.request.id,
            "error": str(e),
        })
        raise

    finally:
        db.close()


def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get the status of a Celery task.

    Args:
        task_id: The Celery task ID

    Returns:
        Dict with task status and result (if completed)
    """
    result = AsyncResult(task_id)

    status_info = {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
    }

    if result.ready():
        if result.successful():
            status_info["result"] = result.result
        else:
            status_info["error"] = str(result.result)

    return status_info
