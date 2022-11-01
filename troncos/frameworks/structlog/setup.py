import logging
from typing import Iterable, Literal

from structlog.contextvars import merge_contextvars

try:
    import structlog
    from structlog.types import Processor
except ImportError:
    raise Exception("This feature is only available if 'structlog' is installed")

from troncos.frameworks.structlog.processors import (
    StaticValue,
    trace_injection_processor,
)
from troncos.logs import init_logging_basic


def init_logging_structlog(
    level: str | int,
    formatter: Literal["cli", "logfmt"],
    app_release: str | None = None,
    environment: str | None = None,
    app_name: str | None = None,
    extra_processors: Iterable[Processor] | None = None,
) -> None:
    """
    Setting up Python logging with Structlog support

    :param level: Log level for logger and handler (minimum level for entries to be
        picked up/printed)
    :param formatter: The name of the formatter to use for log entries (must be defined
        inside this function)
    :param app_release: Optional string representing release version (i.e. "v22.1" or
        "0.0.1")
    :param environment: Optional string representing the environment (i.e. "prod" or
        "dev")
    :param app_name: Optional string with the name of the app/service (i.e. "trex" or
        "interno")
    :param extra_processors: Optional list of structlog processors to add to the chain
    """
    logger = init_logging_basic(
        level=level,
        formatter="structlog",
    )
    renderer: Processor

    # The renderer is the last processor in the chain of structlog processors, acts as
    # formatter
    if formatter == "cli":
        renderer = structlog.dev.ConsoleRenderer()
    elif formatter == "logfmt":
        renderer = structlog.processors.LogfmtRenderer()
    else:
        raise Exception("Invalid renderer configured")

    configure_structlog(
        renderer=renderer,
        release=app_release,
        environment=environment,
        app_name=app_name,
        handler=logger.handlers[0],
        extra_processors=extra_processors,
    )


def configure_structlog(
    renderer: Processor,
    handler: logging.Handler,
    release: str | None = None,
    environment: str | None = None,
    app_name: str | None = None,
    extra_processors: Iterable[Processor] | None = None,
) -> None:
    """

    :param renderer: Function which will be last in processor chain, will be used as
        formatter
    :param handler: The logging.Handler object used for the root logger
    :param release: Optional string representing release version (i.e. "v22.1" or
        "0.0.1")
    :param environment: Optional string representing the environment (i.e. "prod" or
        "dev")
    :param app_name: Optional string with the name of the app/service (i.e. "trex" or
        "interno")
    :param extra_processors: Optional list of structlog processors to add to the chain
    """

    # Use ISO-format for all timestamps output by structlog
    timestamper = structlog.processors.TimeStamper(fmt="ISO")

    # The shared processors are used both for entries originating from the builtin
    # Python logger, and entries that are created through structlog (
    # `structlog.get_logger()`)
    shared_processors: list[Processor] = [
        merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        timestamper,
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
        trace_injection_processor,
    ]

    # Append release string if that has been supplied in instantiation
    if release:
        shared_processors.append(StaticValue("release", release))

    # Append environment string if that has been supplied in instantiation
    if environment:
        shared_processors.append(StaticValue("environment", environment))

    # Append app name string if that has been supplied in instantiation
    if app_name:
        shared_processors.append(StaticValue("app_name", app_name))

    if extra_processors:
        shared_processors += extra_processors

    # Processing chain for log entries originating from outside structlog
    pre_chain = shared_processors + [
        structlog.stdlib.ExtraAdder(),
    ]

    # Processing chain for entries originating from structlog (from
    # `structlog.get_logger()`)
    _processors = shared_processors + [
        structlog.processors.StackInfoRenderer(),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.format_exc_info,
    ]

    # All entries pass through structlog processors before going to the formatter
    structlog_processors = _processors + [
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter
    ]

    # The formatter needs its own set of processors, ending with the renderer
    formatter_processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        renderer,
    ]

    # The global configuration for structlog
    structlog.configure(
        processors=structlog_processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        # Caching makes this config immutable
        cache_logger_on_first_use=True,
    )

    # Setting the structlog formatter on our handler
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=pre_chain, processors=formatter_processors
        )
    )
