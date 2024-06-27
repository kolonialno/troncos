import time
from typing import Any

from celery import signals

try:
    from structlog import get_logger
except ImportError as exc:
    raise RuntimeError(
        "Structlog must be installed to use the celery logging signals."
    ) from exc

logger = get_logger("troncos.celery.task")


def connect_troncos_logging_celery_signals() -> None:
    """
    Log a message every time a task is complete.
    """

    signals.task_prerun.connect(_prerun, weak=True)
    signals.task_postrun.connect(_postrun, weak=True)


def _prerun(sender: Any, task_id: Any, task: Any, *args: Any, **kwargs: Any) -> None:
    task.__troncos_start_time = time.perf_counter()


def _postrun(sender: Any, task_id: Any, task: Any, *args: Any, **kwargs: Any) -> None:
    started_time = getattr(task, "__troncos_start_time", None)

    extra = {}

    if started_time:
        extra["duration"] = time.perf_counter() - started_time

    logger.info("Celery task post-run", task=task.name, state=kwargs["state"], **extra)
