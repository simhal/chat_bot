"""
Celery application configuration for background task processing.

This module configures Celery with Redis as the message broker and result backend.
Task routing directs different agent workloads to separate queues for better
resource management and scaling.
"""

import os
from celery import Celery

# Redis configuration - reuse existing Redis instance with different databases
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

# Create Celery app
celery_app = Celery(
    "chatbot_tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["tasks.agent_tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task execution settings
    task_acks_late=True,  # Acknowledge after task completes (for reliability)
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    task_soft_time_limit=300,  # 5 minute soft limit
    task_time_limit=600,  # 10 minute hard limit

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time for long-running tasks
    worker_concurrency=2,  # Default concurrency (can override per worker)

    # Result backend settings
    result_expires=86400,  # Results expire after 24 hours
    result_extended=True,  # Store additional task metadata

    # Task routing - direct tasks to appropriate queues
    task_routes={
        "tasks.agent_tasks.analyst_research_task": {"queue": "analyst"},
        "tasks.agent_tasks.web_search_task": {"queue": "research"},
        "tasks.agent_tasks.data_download_task": {"queue": "research"},
        "tasks.agent_tasks.article_query_task": {"queue": "articles"},
        "tasks.agent_tasks.editor_publish_task": {"queue": "editor"},
    },

    # Default queue for unrouted tasks
    task_default_queue="default",

    # Queue definitions for Celery worker startup
    task_queues={
        "default": {},
        "analyst": {},
        "research": {},
        "articles": {},
        "editor": {},
    },
)


# Task base class with common error handling
class BaseTask(celery_app.Task):
    """Base task class with automatic retry and error handling."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600  # Max 10 minutes between retries
    retry_jitter = True
    max_retries = 3

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Log task failures for monitoring."""
        # TODO: Add proper logging and alerting
        print(f"Task {task_id} failed: {exc}")

    def on_success(self, retval, task_id, args, kwargs):
        """Log task successes for monitoring."""
        print(f"Task {task_id} completed successfully")


# Export for use in task definitions
celery_app.Task = BaseTask


if __name__ == "__main__":
    celery_app.start()
