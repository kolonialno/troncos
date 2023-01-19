"""
The processors are used by Structlog to process incoming log entries, a bit like
how the stdlib logging uses logging filters. This is currently implemented alongside
the filters to allow for parallel feature parity while we finish the current troncos
adoption.
"""
import opentelemetry.trace as trace

from troncos._ddlazy import ddlazy

try:
    from structlog.types import EventDict, WrappedLogger
except ImportError:
    raise Exception("This feature is only available if 'structlog' is installed")


class StaticValue:
    """
    Annotating log entries with values that are not subject to change after logger
    instantiation (i.e. version number or environment)

    :param key: The name of the variable
    :param value: The value of the variable

    Example:
        init_logging_structlog(
            ...,
            extra_processors=[
                StaticValue("process_start_time", str(datetime.now())),
                StaticValue("foo", "bar")
            ]
        )

        Would add the following data to the log entries,
            process_start_time=2022-10-31 14:27:11.081182 foo=bar
    """

    def __init__(self, key: str, value: str) -> None:
        self.key = key
        self.value = value

    def __call__(
        self, _logger: WrappedLogger, method: str, event_dict: EventDict
    ) -> EventDict:
        event_dict[self.key] = self.value
        return event_dict


def trace_injection_processor(
    _logger: WrappedLogger, _log_method: str, event_dict: EventDict
) -> EventDict:
    """
    Simple logging processor that adds a trace_id to the log record if available.
    """

    span = trace.get_current_span()
    if not isinstance(span, trace.NonRecordingSpan):
        event_dict["trace_id"] = f"{span.get_span_context().trace_id:x}"
        event_dict["span_id"] = f"{span.get_span_context().span_id:x}"

    if ddlazy.dd_trace_export_enabled():
        dd_context = ddlazy.dd_tracer().current_trace_context()
        if dd_context:
            event_dict["dd_trace_id"] = dd_context.trace_id
            event_dict["dd_span_id"] = dd_context.span_id

    return event_dict
