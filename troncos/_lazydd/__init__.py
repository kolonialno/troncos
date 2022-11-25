"""
This modules sole purpose is to lazy import ddtrace for usage in troncos
"""

_dd_tracer = []


def dd_initialized():
    return len(_dd_tracer) > 0


def dd_tracer():
    if not _dd_tracer:
        import ddtrace
        _dd_tracer.append(ddtrace.tracer)
    return _dd_tracer[0]


def clean_logger(msg, level=None):
    level = level or "INFO"
    print(f"Troncos init {level}: {msg}")
