from opentelemetry import trace

from troncos import OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION

try:
    from django.utils.module_loading import import_string  # type: ignore[import]
except ImportError:
    raise Exception("This feature is only available if 'django' is installed")


def trace_django_middleware(
    middlewares: list[str], tracer_provider: trace.TracerProvider | None = None
) -> None:
    """
    Pass in a list of middlewares to trace
    """

    for m in middlewares:
        klass = import_string(m)
        if klass:
            tp = tracer_provider or trace.get_tracer_provider()
            tr = tp.get_tracer(OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION)
            # noinspection PyCallingNonCallable
            klass.__call__ = tr.start_as_current_span(m)(klass.__call__)
