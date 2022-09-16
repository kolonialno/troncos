import logging
from typing import Iterable, List

import opentelemetry.trace
from opentelemetry.exporter.otlp.proto.grpc import trace_exporter
from opentelemetry.sdk.resources import Attributes, Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.util._once import Once

_GLOBAL_SPAN_PROCESSOR: SpanProcessor | None = None
_GLOBAL_SPAN_PROCESSOR_SET_ONCE = Once()

_DEBUG_SPAN_PROCESSOR: SpanProcessor = SimpleSpanProcessor(ConsoleSpanExporter())


def _set_span_processor(span_processor: SpanProcessor) -> None:
    def set_sp() -> None:
        global _GLOBAL_SPAN_PROCESSOR
        _GLOBAL_SPAN_PROCESSOR = span_processor

    did_set = _GLOBAL_SPAN_PROCESSOR_SET_ONCE.do_once(set_sp)
    if not did_set:
        logging.getLogger(__name__).warning(
            "Global span processor already set, not doing that again!"
        )


def init_tracing_endpoint(endpoint: str) -> SpanProcessor:
    """
    Initialize the global span processor.
    """

    exporter_class = trace_exporter.OTLPSpanExporter
    exporter = exporter_class(endpoint=endpoint)
    logging.getLogger(__name__).info(
        "Reporting traces with %s(endpoint=%s)",
        exporter_class.__name__,
        endpoint,
    )
    _set_span_processor(BatchSpanProcessor(exporter))
    return _GLOBAL_SPAN_PROCESSOR  # type: ignore[return-value]


def init_tracing_provider(
    attributes: Attributes, global_provider: bool = True
) -> TracerProvider:
    """
    Initialize a tracing provider. By default, this function will make the new tracer
    provider the global one. If that is not desired, pass in global_provider=False.
    """

    if not _GLOBAL_SPAN_PROCESSOR:
        raise RuntimeError("Call 'init_tracing_endpoint' before calling this function")

    if not attributes.get("service.name"):
        raise ValueError("Tracer must have 'service.name' in attributes")

    if global_provider and not attributes.get("environment"):
        raise ValueError("Global tracer must have 'environment' in attributes")

    resource = Resource.create(attributes)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(_GLOBAL_SPAN_PROCESSOR)

    if global_provider:
        opentelemetry.trace.set_tracer_provider(provider)

    return provider


def init_tracing_debug(
    trace_provider: TracerProvider | List[TracerProvider],
) -> None:
    """
    Add debug processor to tracing providers.
    """

    if isinstance(trace_provider, Iterable):
        for p in trace_provider:
            p.add_span_processor(_DEBUG_SPAN_PROCESSOR)
    else:
        trace_provider.add_span_processor(_DEBUG_SPAN_PROCESSOR)


def init_tracing_basic(
    *, endpoint: str, attributes: Attributes, debug: bool = False
) -> TracerProvider:
    """
    Setup rudimentary tracing.
    """

    init_tracing_endpoint(endpoint)
    global_tracer = init_tracing_provider(attributes, True)
    if debug:
        init_tracing_debug(global_tracer)
    return global_tracer
