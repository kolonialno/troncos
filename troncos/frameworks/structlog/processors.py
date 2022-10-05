import opentelemetry.trace as trace

try:
    from structlog.types import EventDict, WrappedLogger
except ImportError:
    raise Exception("This feature is only available if 'structlog' is installed")


def trace_injection_processor(
    _logger: WrappedLogger, _log_method: str, event_dict: EventDict
) -> EventDict:
    span = trace.get_current_span()
    if not isinstance(span, trace.NonRecordingSpan):
        event_dict["trace_id"] = f"{span.get_span_context().trace_id:x}"
        event_dict["span_id"] = f"{span.get_span_context().span_id:x}"
    return event_dict
