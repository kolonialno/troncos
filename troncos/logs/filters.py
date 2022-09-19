import logging

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
        span = trace.get_current_span()
        if not isinstance(span, trace.NonRecordingSpan):
            record.trace_id = f"{span.get_span_context().trace_id:x}"
            record.span_id = f"{span.get_span_context().span_id:x}"
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
