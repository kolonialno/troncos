from typing import Any


class DDLazy:
    """
    This class exists to make sure that ddtrace is not imported anywhere by troncos
    before tracing has been initialized.
    """

    def __init__(self) -> None:
        self._dd_trace_export_enabled = False
        self._dd_tracer = None
        self._dd_propagator = None

    def _on_loaded(self, export_dd_traces: bool) -> None:
        self._dd_trace_export_enabled = export_dd_traces
        self.dd_tracer()
        self.dd_propagator()

    def dd_initialized(self) -> bool:
        return self._dd_tracer is not None or self._dd_propagator is not None

    def dd_trace_export_enabled(self) -> bool:
        return self._dd_trace_export_enabled

    def dd_tracer(self) -> Any:
        if not self._dd_tracer:
            import ddtrace

            self._dd_tracer = ddtrace.tracer  # type: ignore[assignment]
        return self._dd_tracer

    def dd_propagator(self) -> Any:
        if not self._dd_propagator:
            import ddtrace.propagation.http

            self._dd_propagator = ddtrace.propagation.http.HTTPPropagator()  # type: ignore[assignment] # noqa: E501
        return self._dd_propagator


ddlazy = DDLazy()

__all__ = ["ddlazy"]
