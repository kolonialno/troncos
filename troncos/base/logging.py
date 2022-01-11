from logging.config import dictConfig
from typing import Dict, Any

import structlog


def get_logger():
    return structlog.get_logger()


def rename_event_key(_, __, event):
    event["message"] = event.pop("event")
    return event


def add_module_and_lineno(logger: structlog.BoundLogger, name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    frame, module_str = structlog._frames._find_first_app_frame_and_name(additional_ignores=[__name__])
    # frame has filename, caller and line number
    event_dict['module'] = module_str
    event_dict['lineno'] = frame.f_lineno
    return event_dict


def add_app_info(environment, release):
    """
    Bind current environment and release info to logger
    """
    def inner(logger: structlog.BoundLogger, name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        event_dict['environment'] = environment
        event_dict['release'] = release
        return event_dict
    return inner


def configure_logging(environment, release, log_level, log_format="json", enable_tracer=True) -> None:
    """
    Configure logging globally fore use in applications.

    This function configures both structlog and the global stock Python logger in order to make sure everything is sent
    thorough structlog, and formatted there.

    We do some log enrichment as well, to give us more relevant info for debugging.

    Relevant reading on why this is solved the way it is:
        * Structlog doc, regarding standard logging lib: https://www.structlog.org/en/stable/standard-library.html

    Kwargs:
        environment: (str) name of environment (i.e. "dev", "prod", "staging" etc.)
        log_level: (str) the log level to use globally for the logger
        log_format: (str) name of logging format, must be one of "json", "text", "plaintext"
    """
    log_level = log_level.upper()
    timestamper = structlog.processors.TimeStamper(fmt="iso")
    app_info_adder = add_app_info(environment=environment, release=release)

    pre_chain = [
        # Add the log level and a timestamp to the event_dict if the log entry
        # is not from structlog.
        structlog.stdlib.add_log_level,
        # Add extra attributes of LogRecord objects to the event dictionary
        # so that values passed in the extra parameter of log methods pass
        # through to log output.
        structlog.stdlib.ExtraAdder(),
        timestamper,
        app_info_adder
    ]

    common_root_processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
    ]

    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plaintext": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    *common_root_processors,
                    structlog.dev.ConsoleRenderer(colors=False),
                ],
                "foreign_pre_chain": pre_chain,
            },
            "text": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    *common_root_processors,
                    structlog.dev.ConsoleRenderer(colors=True, exception_formatter=structlog.dev.rich_traceback),
                ],
                "foreign_pre_chain": pre_chain,
            },
            "logfmt": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    *common_root_processors,
                    structlog.processors.LogfmtRenderer(),
                ],
                "foreign_pre_chain": pre_chain,
            },
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": common_root_processors + [
                    # JSON-logs ingested by logging tools need to use another key for the message, so we reformat that
                    # here
                    rename_event_key,
                    structlog.processors.JSONRenderer()
                ],
                "foreign_pre_chain": pre_chain,
            },
        },
        "handlers": {
            "default": {
                "level": log_level,
                "class": "logging.StreamHandler",
                "formatter": log_format,
            },
        },
        "loggers": {
            "": {
                "handlers": ["default"],
                "level": log_level,
                "propagate": True,
            },
        }
    })

    processors = [
        structlog.threadlocal.merge_threadlocal,
        add_module_and_lineno,
        timestamper,
        app_info_adder,
        structlog.dev.set_exc_info,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,

    ]

    if enable_tracer:
        # If we're not enabling the tracer for logging, we'll skip its event processor as well
        from .tracing import tracer_injection
        processors.insert(1, tracer_injection)

    structlog.configure(
        processors=processors,
        context_class=structlog.threadlocal.wrap_dict(dict),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True
    )
