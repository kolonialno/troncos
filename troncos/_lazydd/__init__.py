"""
This modules sole purpose is to lazy import ddtrace for usage in troncos
"""

from typing import Any

_dd_tracer: list[Any] = []


def dd_initialized() -> bool:
    return len(_dd_tracer) > 0


def dd_tracer() -> Any:
    if not _dd_tracer:
        import ddtrace

        _dd_tracer.append(ddtrace.tracer)
    return _dd_tracer[0]


def clean_logger(msg: str, level: str | None = None) -> None:
    level = level or "INFO"
    print(f"Troncos init {level}: {msg}")
