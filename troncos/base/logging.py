import logging
import sys

import structlog

from .tracing import tracer_injection


def get_logger():
    return structlog.get_logger()


def rename_event_key(_, __, event):
    event["message"] = event.pop("event")
    return event


def configure_logging(environment, log_level) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)

    if environment != ["dev" or "localdev"]:
        structlog.configure(
            processors=[
                structlog.threadlocal.merge_threadlocal,
                tracer_injection,
                rename_event_key,
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            context_class=structlog.threadlocal.wrap_dict(dict),
            logger_factory=structlog.stdlib.LoggerFactory(),
        )