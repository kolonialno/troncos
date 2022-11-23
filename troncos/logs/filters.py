import logging

import ddtrace
import opentelemetry.trace as trace


class TraceIdFilter(logging.Filter):
    """
    Simple logging filter that adds a trace_id to the log record if available.

    It sounds strange to use filters to modify records, but this is described
    in the official python docs:

    https://docs.python.org/3/howto/logging-cookbook.html#using-filters-to-impart-contextual-information
    """

    def __init__(self, name: str = "TraceIdFilter") -> None:
        super().__init__(name)

    def filter(self, record: logging.LogRecord) -> bool:
        otel_span = trace.get_current_span()
        if not isinstance(otel_span, trace.NonRecordingSpan):
            record.trace_id = f"{otel_span.get_span_context().trace_id:x}"
            record.span_id = f"{otel_span.get_span_context().span_id:x}"

        dd_context = ddtrace.tracer.current_trace_context()
        if dd_context:
            record.dd_trace_id = dd_context.trace_id
            record.dd_span_id = dd_context.span_id

        return True


class HttpPathFilter(logging.Filter):
    """
    Simple logging filter that drops any log records regarding paths in the
    list 'ignored_paths'.
    """

    def __init__(
        self, ignored_paths: list[str] | None, name: str = "HttpPathFilter"
    ) -> None:
        super().__init__(name)
        self._ignored_paths = ignored_paths if ignored_paths else []

    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "http_path"):
            return getattr(record, "http_path") not in self._ignored_paths
        return True
