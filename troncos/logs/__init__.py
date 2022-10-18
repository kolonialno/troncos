import logging
import sys
from typing import Literal, Tuple, Any

import structlog

from troncos.logs.filters import TraceIdFilter
from troncos.logs.formatters import JsonFormatter, LogfmtFormatter, PrettyFormatter
from troncos.logs.processors import StaticValue

__all__ = ["JsonFormatter", "LogfmtFormatter", "PrettyFormatter"]


def print_loggers(verbose: bool = True) -> None:
    """
    Function that prints out initialized loggers. This is helpful for you to visualize
    exactly how loggers have been set up in your project (and your dependencies). By
    default, all loggers will be printed. If you want to filter out logging
    placeholders, loggers with NullHandlers, and loggers that only propagate to parent,
    set the verbose parameter to False.

    This flowchart helps to debug logging issues:
    https://docs.python.org/3/howto/logging.html#logging-flow

    The output from this function will look something like this:

        Loggers:
        [ root                 ] logs.RootLogger LEVEL:0 PROPAGATE:True
          └ HANDLER logs.StreamHandler  LVL  20
            └ FILTER velodrome.observability.logs.TraceIdFilter
            └ FORMATTER velodrome.observability.logs.LogfmtFormatter
        [ uvicorn.access       ] logs.Logger LEVEL:20 PROPAGATE:False
        [ uvicorn.error        ] logs.Logger LEVEL:20 PROPAGATE:True
          └ FILTER velodrome.utils.obs._UvicornErrorFilter
        [ velodrome.access     ] logs.Logger LEVEL:20 PROPAGATE:True
          └ FILTER velodrome.observability.logs.HttpPathFilter
    """

    def internal(
        curr: Tuple[str, logging.Logger],
        rest: list[Tuple[str, logging.Logger]],
    ) -> None:
        i_name, i_log = curr

        print(
            f"[ {i_name.ljust(20)[:20]} ]"
            f" {str(i_log.__class__)[8:-2]}"
            f" LEVEL: {i_log.level if hasattr(i_log, 'level') else '?'}"
            f" PROPAGATE: {i_log.propagate if hasattr(i_log, 'propagate') else '?'}"
        )

        if hasattr(i_log, "filters"):
            for f in i_log.filters:
                print("  └ FILTER", str(f.__class__)[8:-2])

        if hasattr(i_log, "handlers"):
            for h in i_log.handlers:
                print(
                    "  └ HANDLER",
                    str(h.__class__)[8:-2],
                    " LEVEL:",
                    h.level if hasattr(h, "level") else "?",
                )
                if hasattr(h, "filters"):
                    for f in h.filters:
                        print("    └ FILTER", str(f.__class__)[8:-2])
                if hasattr(h, "formatter"):
                    print("    └ FORMATTER", str(h.formatter.__class__)[8:-2])

        if len(rest) > 0:
            curr = rest[0]
            rest = rest[1:]
            internal(curr, rest)

    all_but_root = []
    for (name, logger) in logging.Logger.manager.loggerDict.items():

        if not verbose:
            # Ignore placeholders
            if isinstance(logger, logging.PlaceHolder):
                continue

            # If it is a logger that does nothing but propagate to the parent, ignore
            if (
                len(logger.filters) == 0
                and len(logger.handlers) == 0
                and logger.propagate
            ):
                continue

            # If this logger only has the Null handler
            if (
                len(logger.filters) == 0
                and len(logger.handlers) == 1
                and isinstance(logger.handlers[0], logging.NullHandler)
            ):
                continue

        all_but_root.append((name, logger))

    all_but_root.sort()

    print("Loggers:")
    internal(("root", logging.getLogger()), all_but_root)  # type: ignore[arg-type]
    print("")


def init_logging_basic(
    *,
    level: str | int,
    formatter: Literal["cli", "logfmt", "json", "structlog-cli"] | logging.Formatter,
    app_release: str | None = None,
    environment: str | None = None,
    app_name: str | None = None,
) -> None:
    """
    Setup root logger to handle trace_id in records.

    Loggers:
    [ root                 ] logging.RootLogger LEVEL: 20 PROPAGATE: True
      └ HANDLER logging.StreamHandler  LEVEL: 20
        └ FILTER troncos.logs.filters.TraceIdFilter
        └ FORMATTER troncos.logs.formatters.PrettyFormatter

    """
    _structlog = False

    # Create handler
    root_handler = logging.StreamHandler()
    root_handler.setLevel(level)
    root_handler.addFilter(TraceIdFilter())

    if formatter in ["structlog-cli", "structlog-logfmt"]:
        if formatter == "structlog-cli":
            renderer = structlog.dev.ConsoleRenderer()
        elif formatter == "structlog-logfmt":
            renderer = structlog.processors.LogfmtRenderer()
        else:
            raise Exception("Invalid renderer configured")

        configure_structlog(
            renderer=renderer,
            release=app_release,
            environment=environment,
            app_name=app_name,
            handler=root_handler,
        )
        _structlog = True
    else:
        configure_structlog(
            renderer=structlog.stdlib.render_to_log_kwargs,
            release=app_release,
            environment=environment,
            app_name=app_name,
            handler=root_handler,
        )

    # Set formatter
    if formatter == "cli":
        root_handler.setFormatter(PrettyFormatter())
    elif formatter == "logfmt":
        root_handler.setFormatter(LogfmtFormatter())
    elif formatter == "json":
        root_handler.setFormatter(JsonFormatter())
    elif _structlog:
        # Formatter handled by structlog
        pass
    else:
        root_handler.setFormatter(formatter)

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [root_handler]


def configure_structlog(
    renderer,
    release: str | None = None,
    environment: str | None = None,
    app_name: str | None = None,
    handler=None,
):

    # Use ISO-format for all timestamps output by structlog
    timestamper = structlog.processors.TimeStamper(fmt="ISO")

    # The shared processors are used both for entries originating from the builtin Python logger,
    # and entries that are created through structlog (`structlog.get_logger()`)
    shared_processors = [
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

    # Processing chain for log entries originating from outside structlog
    pre_chain = shared_processors + [
        structlog.stdlib.ExtraAdder(),
    ]

    # Processing chain for entries originating from structlog (from `structlog.get_logger()`)
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
        wrapper_class=structlog.stdlib.BoundLogger,
        # Caching makes this config immutable
        cache_logger_on_first_use=True,
    )

    # Setting the structlog formatter on our handler
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=pre_chain, processors=formatter_processors
        )
    )
