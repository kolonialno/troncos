"""
This modules sole purpose is to lazy import ddtrace for usage in troncos
"""

from typing import Any


class DDLazy:
    def __init__(self) -> None:
        self._dd_trace_export_enabled = False
        self._dd_tracer = None
        self._dd_propagator = None

    def _set_dd_trace_export_enabled(self, v: bool) -> None:
        self._dd_trace_export_enabled = v

    def _load_dd_lazy(self) -> None:
        self.dd_tracer()
        self.dd_propagator()

    def dd_initialized(self) -> bool:
        return self._dd_tracer is not None or self._dd_propagator is not None

    def dd_trace_export_enabled(self) -> bool:
        return self._dd_trace_export_enabled

    def dd_tracer(self) -> Any:
        if not self._dd_tracer:
            import ddtrace

            self._dd_tracer = ddtrace.tracer
        return self._dd_tracer

    def dd_propagator(self) -> Any:
        if not self._dd_propagator:
            import ddtrace.propagation.http
            self._dd_propagator = ddtrace.propagation.http.HTTPPropagator()
        return self._dd_propagator


ddlazy = DDLazy()

__all__ = [
    "ddlazy"
]
