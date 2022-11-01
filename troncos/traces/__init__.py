import logging
import os
import sys
from typing import IO, Iterable, List, Literal

import opentelemetry.trace

try:
    from opentelemetry.exporter.otlp.proto.grpc import (  # type: ignore
        trace_exporter as grpc_trace_exporter,
    )
except ImportError:  # pragma: no cover
    grpc_trace_exporter = None

from opentelemetry.exporter.otlp.proto.http import trace_exporter
from opentelemetry.sdk.resources import Attributes, Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)

# noinspection PyProtectedMember
from opentelemetry.util._once import Once

from troncos.traces.dd_exporter import OTLPGrpcSpanExporterDD, OTLPHttpSpanExporterDD

_GLOBAL_SPAN_PROCESSORS: list[SpanProcessor] | None = None
_GLOBAL_SPAN_PROCESSORS_SET_ONCE = Once()

if out_file := os.environ.get("TRACING_DEBUGGING_FILE", None):
    traces_out: IO[str] = open("traces.json", "w")
else:
    traces_out = sys.stdout
_DEBUG_SPAN_PROCESSOR: SpanProcessor = SimpleSpanProcessor(
    ConsoleSpanExporter(out=traces_out)
)

GRPC_ERROR_MESSAGE = (
    "Cannot use 'exporter_type==grpc' without "
    "installing 'opentelemetry-exporter-otlp-proto-grpc'"
)

logger = logging.getLogger(__name__)


def http_endpoint_from_env(host_var: str, port_var: str, path: str = "") -> str | None:
    host = os.environ.get(host_var)
    if not host:
        return None
    port = os.environ.get(port_var)
    if not port:
        return None
    return f"http://{host}:{port}{path}"


def _set_span_processors(span_processors: list[SpanProcessor]) -> None:
    def set_sp() -> None:
        global _GLOBAL_SPAN_PROCESSORS
        _GLOBAL_SPAN_PROCESSORS = span_processors

    did_set = _GLOBAL_SPAN_PROCESSORS_SET_ONCE.do_once(set_sp)
    if not did_set:
        logging.getLogger(__name__).warning(
            "Global span processors already set, not doing that again!"
        )


def init_tracing_endpoints(
    endpoint: str | None,
    endpoint_dd: str | None = None,
    exporter_type: Literal["http", "grpc"] = "http",
) -> list[SpanProcessor]:
    """
    Initialize the global span processor.
    """
    assert exporter_type in ["http", "grpc"]
    exporters = []

    if endpoint:
        if exporter_type == "http":
            otel_exp: SpanExporter = trace_exporter.OTLPSpanExporter(endpoint=endpoint)
        elif exporter_type == "grpc":
            if not grpc_trace_exporter:
                raise ValueError(GRPC_ERROR_MESSAGE)
            otel_exp = grpc_trace_exporter.OTLPSpanExporter(endpoint=endpoint)
        logging.getLogger(__name__).info(
            "Reporting OTEL traces with %s(endpoint=%s)",
            type(otel_exp).__name__,
            endpoint,
        )
        exporters.append(BatchSpanProcessor(otel_exp))

    if endpoint_dd:
        if exporter_type == "http":
            dd_exp: SpanExporter = OTLPHttpSpanExporterDD(endpoint=endpoint_dd)
        elif exporter_type == "grpc":
            if not grpc_trace_exporter:
                raise ValueError(GRPC_ERROR_MESSAGE)
            dd_exp = OTLPGrpcSpanExporterDD(endpoint=endpoint_dd)
        logging.getLogger(__name__).info(
            "Reporting DD traces with %s(endpoint=%s)",
            type(dd_exp).__name__,
            endpoint_dd,
        )
        exporters.append(BatchSpanProcessor(dd_exp))

    _set_span_processors(exporters)  # type: ignore[arg-type]
    return _GLOBAL_SPAN_PROCESSORS  # type: ignore[return-value]


def init_tracing_provider(
    attributes: Attributes, global_provider: bool = False
) -> TracerProvider:
    """
    Initialize a tracing provider. By default, this function will make the new tracer
    provider the global one. If that is not desired, pass in global_provider=False.
    """

    if _GLOBAL_SPAN_PROCESSORS is None:
        logger.warning(
            "Span processors have not been initialized with 'init_tracing_endpoint'. "
            "Your tracing spans will not be exported!"
        )

    if not attributes.get("service.name"):
        raise ValueError("Tracer must have 'service.name' in attributes")

    if global_provider and not attributes.get("environment"):
        raise ValueError("Global tracer must have 'environment' in attributes")

    resource = Resource.create(attributes)
    provider = TracerProvider(resource=resource)
    for span_processor in _GLOBAL_SPAN_PROCESSORS or []:
        provider.add_span_processor(span_processor)

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
    endpoint: str | None = None,
    endpoint_dd: str | None = None,
    exporter_type: Literal["http", "grpc"] = "http",
    attributes: Attributes | None = None,
    debug: bool = False,
) -> TracerProvider:
    """
    Setup rudimentary tracing.
    """

    init_tracing_endpoints(endpoint, endpoint_dd, exporter_type=exporter_type)
    global_tracer = init_tracing_provider(attributes or {}, global_provider=True)
    if debug:
        init_tracing_debug(global_tracer)
    return global_tracer
