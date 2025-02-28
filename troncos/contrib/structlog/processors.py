from ddtrace.trace import tracer

from structlog.processors import LogfmtRenderer as LogFmt
from structlog.types import EventDict, WrappedLogger


def trace_injection_processor(
    _logger: WrappedLogger, _log_method: str, event_dict: EventDict
) -> EventDict:
    """
    Simple logging processor that adds a trace_id to the log record if available.
    """

    # Try to get context from tracer
    dd_context = tracer.current_trace_context()

    # Add context to log record if exists
    if dd_context:
        event_dict["trace_id"] = f"{dd_context.trace_id:x}"
        event_dict["span_id"] = f"{dd_context.span_id:x}"

    return event_dict


class LogfmtRenderer(LogFmt):
    """
    A structlog Logfmt renderer that does not produce new lines
    """

    def __call__(self, _: WrappedLogger, __: str, event_dict: EventDict) -> str:
        return super().__call__(_, __, event_dict).replace("\n", " ")
