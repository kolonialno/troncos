import logging
import logging.config
from typing import Any, Iterable, Optional

import structlog

from troncos.contrib.structlog.processors import (
    LogfmtRenderer,
    trace_injection_processor,
)

try:
    from structlog_sentry import SentryProcessor
except ImportError:
    SentryProcessor = None  # type: ignore

shared_processors: list[structlog.types.Processor] = [
    # Add the name of the logger to event dict.
    structlog.stdlib.add_logger_name,
    # Add log level to event dict.
    structlog.stdlib.add_log_level,
    # Add a timestamp in ISO 8601 format.
    structlog.processors.TimeStamper(fmt="iso"),
    # If the "exc_info" key in the event dict is either true or a
    # sys.exc_info() tuple, remove "exc_info" and render the exception
    # with traceback into the "exception" key.
    structlog.processors.format_exc_info,
    trace_injection_processor,
]

if SentryProcessor is not None:
    format_exc_info_index = shared_processors.index(
        structlog.processors.format_exc_info
    )
    shared_processors.insert(
        format_exc_info_index,
        SentryProcessor(level=logging.INFO, event_level=logging.ERROR),
    )


def configure_structlog(
    *,
    configure_logging: bool = True,
    format: str | structlog.types.Processor = "text",
    level: str = "INFO",
    extra_processors: Optional[Iterable[structlog.typing.Processor]] = None,
    extra_loggers: Optional[dict[str, dict[str, Any]]] = None,
    disable_existing_loggers: bool = True,
) -> None:
    """
    Helper method to configure Structlog.

    Using this is not required, you can configure Structlog
    manually in your application.

    configure_logging=True lets you use structlog to render logs from
    logging.getLogger, this is used to get an unified log output.

    If `extra_processors` is set, these will be inserted to the list of processors
    just before `format_exc_info`.

    If `extra_loggers` is set, it will be unpacked into the `loggers` directive of
    the dictconfig dict. The `handler` value for these loggers must be `"default"`

    The `disable_existing_loggers` lets you control the `disable_existing_loggers`
    flag to the standard library logger config.
    """

    extra_loggers = extra_loggers or {}
    extra_processors = extra_processors or []

    if extra_processors:
        _format_exc_info_index = shared_processors.index(
            structlog.processors.format_exc_info
        )
        for index, proc in enumerate(extra_processors):
            shared_processors.insert(_format_exc_info_index + index, proc)

    processor: structlog.types.Processor

    if isinstance(format, str):
        if format == "text":
            processor = structlog.dev.ConsoleRenderer(colors=True)
        elif format == "json":
            processor = structlog.processors.JSONRenderer()
        elif format == "logfmt":
            processor = LogfmtRenderer()
        else:
            raise RuntimeError(f"Invalid log format {format}")
    else:
        processor = format

    if configure_logging:
        config = {
            "version": 1,
            "disable_existing_loggers": disable_existing_loggers,
            "formatters": {
                "default": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": processor,
                    "foreign_pre_chain": shared_processors,
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                },
            },
            "loggers": {
                "": {
                    "handlers": ["default"],
                    "level": level,
                    "propagate": True,
                },
                **extra_loggers,
            },
        }

        logging.config.dictConfig(config)

    structlog_processors: list[structlog.types.Processor] = [
        # Merge contextvars into the event dict.
        structlog.contextvars.merge_contextvars,
        # If log level is too low, abort pipeline and throw away log entry.
        structlog.stdlib.filter_by_level,
        # Add shared processors to the processor chain.
        *shared_processors,
        # Perform %-style formatting.
        structlog.stdlib.PositionalArgumentsFormatter(),
        # If the "stack_info" key in the event dict is true, remove it and
        # render the current stack trace in the "stack" key.
        structlog.processors.StackInfoRenderer(),
        # If some value is in bytes, decode it to a unicode str.
        structlog.processors.UnicodeDecoder(),
        # Add callsite parameters.
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
    ]

    if configure_logging:
        # Prepare event dict for `ProcessorFormatter`.
        structlog_processors.append(
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter
        )
    else:
        structlog_processors.append(processor)

    structlog.configure(
        processors=structlog_processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
