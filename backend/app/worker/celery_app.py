from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("miniswarm", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=45 * 60,
    task_soft_time_limit=44 * 60,
    timezone="UTC",
    task_routes={
        "miniswarm.run_task": {"queue": "control"},
        "miniswarm.plan_task": {"queue": "planner"},
        "miniswarm.supervise_message": {"queue": "supervisor"},
        "miniswarm.chat_reply": {"queue": "chat"},
        "miniswarm.execute_node": {"queue": "agent"},
        "miniswarm.analyze_archive_memory": {"queue": "memory"},
    },
)
celery_app.autodiscover_tasks(["app.worker"])
