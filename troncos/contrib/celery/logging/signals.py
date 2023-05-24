from celery import signals
from typing import Any

try:
    from structlog import get_logger
except ImportError:
    raise RuntimeError("Structlog must be installed to use the celery logging signals.")

logger = get_logger("celery.task")


def connect_troncos_logging_celery_signals() -> None:
    """
    Log a message every time a task is complete.
    """

    signals.task_prerun.connect(_prerun, weak=True)
    signals.task_postrun.connect(_postrun, weak=True)


def _prerun(*args: Any, **kwargs: Any) -> None:
    print("pre")


def _postrun(*args: Any, **kwargs: Any) -> None:
    print("post")
