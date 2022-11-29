"""
This modules sole purpose is to lazy import ddtrace for usage in troncos
"""

from typing import Any

_dd_enabled = [False]
_dd_tracer: list[Any] = []
_dd_propagator: list[Any] = []


def dd_initialized() -> bool:
    return len(_dd_tracer) > 0


def _dd_set_enabled(v: bool):
    _dd_enabled[0] = v

def dd_enabled() -> bool:
    return _dd_enabled[0]


def dd_tracer() -> Any:
    if not _dd_tracer:
        import ddtrace

        _dd_tracer.append(ddtrace.tracer)
    return _dd_tracer[0]


def dd_propagator() -> Any:
    if not _dd_propagator:
        import ddtrace.propagation.http
        _dd_propagator.append(ddtrace.propagation.http.HTTPPropagator())

    return _dd_propagator[0]


def clean_logger(msg: str, level: str | None = None) -> None:
    level = level or "INFO"
    print(f"Troncos init {level}: {msg}")
