from ddtrace import tracer
from structlog.types import EventDict, WrappedLogger


def trace_injection_processor(
    _logger: WrappedLogger, _log_method: str, event_dict: EventDict
) -> EventDict:
    """
    Simple logging processor that adds a trace_id to the log record if available.
    """

    # Try to get context from log record
    dd_context = event_dict.pop("dd_context", None)

    # Try to get context from tracer
    if not dd_context:
        dd_context = tracer.current_trace_context()

    # Add context to log record if exists
    if dd_context:
        event_dict["trace_id"] = f"{dd_context.trace_id:x}"
        event_dict["span_id"] = f"{dd_context.span_id:x}"

    return event_dict
