import logging

import opentelemetry.trace as trace

from troncos._ddlazy import ddlazy

logger = logging.getLogger(__name__)


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

        if ddlazy.dd_trace_export_enabled():
            dd_context = ddlazy.dd_tracer().current_trace_context()
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


class ContextDetachExceptionDropFilter(logging.Filter):
    """
    There is a problem with OTEL where sometimes detaching context fails with an
    error. This issue is tracked here:

        https://github.com/open-telemetry/opentelemetry-python/issues/2606

    We have observed this in some services. In those cases the first (or root)
    span of an incoming starlette request fails to detach the context when it
    finishes. This does not seem to affect tracing, nor to cause any memory leaks.
    It just floods the logs with exceptions. So a "solution" can be to suppress
    those exceptions in the logs using this filter.

    So if you see this exception in your logs, you can consider using this filter:

    Traceback (most recent call last):
      File "opentelemetry/context/__init__.py", line 157, in detach
        _RUNTIME_CONTEXT.detach(token)  # type: ignore
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
      File "opentelemetry/context/contextvars_context.py", line 50, in detach
        self._current_context.reset(token)  # type: ignore
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ValueError: <Token> was created in a different Context
    """

    def __init__(self, name: str = "ContextDetachExceptionDropFilter") -> None:
        super().__init__(name)
        self._count = 0

    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.name == "opentelemetry.context"
            and record.msg == "Failed to detach context"
        ):
            if self._count == 0:
                logger.warning("Suppressing context detach exceptions")
            self._count += 1
            if self._count > 100:
                self._count = 0
            return False
        return True
