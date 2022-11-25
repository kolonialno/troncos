import os
import sys

from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from troncos._lazydd import clean_logger


def http_endpoint_from_env(host_var: str, port_var: str, path: str = "") -> str | None:
    host = os.environ.get(host_var)
    if not host:
        return None
    port = os.environ.get(port_var)
    if not port:
        return None
    return f"http://{host}:{port}{path}"


def init_tracing_basic(
    service_name: str,
    service_env: str | None = None,
    service_version: str | None = None,
    endpoint: str | None = None,
    endpoint_dd: str | None = None,
    ignored_paths: list[str] | None = None,  # TODO: FIX
) -> None:
    service_version = service_version or "unset"
    # Set variables
    os.environ["DD_SERVICE"] = service_name
    os.environ["DD_ENV"] = service_env or "unset"
    os.environ["DD_VERSION"] = service_version or "unset"

    # Setup OTEL exporter
    otel_span_processors: list[SpanProcessor] = []
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc import (
                trace_exporter,
            )  # isort: skip # noqa: 501

            clean_logger("OTEL using GRPC exporter")
        except ImportError:  # pragma: no cover
            try:
                from opentelemetry.exporter.otlp.proto.http import trace_exporter  # type: ignore # isort: skip # noqa: 501

                clean_logger("OTEL using HTTP exporter")
            except ImportError:  # pragma: no cover
                trace_exporter = None  # type: ignore

        if trace_exporter:
            clean_logger(f"OTEL traces exported to {endpoint}")
            otel_span_processors.append(
                BatchSpanProcessor(trace_exporter.OTLPSpanExporter(endpoint=endpoint))
            )

    if len(otel_span_processors) == 0:
        clean_logger("No OTEL span processor configured", "WARNING")
        otel_span_processors.append(SimpleSpanProcessor(InMemorySpanExporter()))  # type: ignore # noqa: E501

    # Setup OTEL debug processor
    otel_trace_debug = os.environ.get("OTEL_TRACE_DEBUG")
    otel_trace_debug_file = os.environ.get("OTEL_TRACE_DEBUG_FILE")
    if otel_trace_debug:
        clean_logger(f"OTEL debug processor to {otel_trace_debug_file or 'stdout'}")
        debug_out = (
            sys.stdout
            if not otel_trace_debug_file
            else open(otel_trace_debug_file, "w")
        )
        otel_span_processors.append(
            SimpleSpanProcessor(ConsoleSpanExporter(out=debug_out))
        )

    if endpoint_dd:
        os.environ["DD_TRACE_AGENT_URL"] = endpoint_dd

    from troncos.traces.dd_shim import DDSpanProcessor, OtelTracerProvider

    # Setup OTEL trace provider
    otel_trace_provider = OtelTracerProvider(
        span_processors=otel_span_processors,
        service=service_name,
        env=service_env,
        version=service_version,
    )

    dd_span_processor = DDSpanProcessor(
        otel_tracer_provider=otel_trace_provider,
        dd_traces_exported=endpoint_dd is not None,
    )

    if endpoint_dd:
        os.environ["DD_TRACE_AGENT_URL"] = endpoint_dd

    import ddtrace

    # Setup propagation
    inject_set = set()
    inject_set.add(ddtrace.internal.constants.PROPAGATION_STYLE_B3_SINGLE_HEADER)
    extract_set = ddtrace.internal.constants.PROPAGATION_STYLE_ALL
    ddtrace.config._propagation_style_extract = extract_set  # type: ignore
    ddtrace.config._propagation_style_inject = inject_set
    ddtrace.config.analytics_enabled = False

    if not endpoint_dd:
        to_pop = None
        for i, s in enumerate(ddtrace.tracer._span_processors):
            if isinstance(s, ddtrace.internal.processor.trace.SpanAggregator):
                to_pop = i
        if to_pop:
            ddtrace.tracer._span_processors.pop(to_pop)
        clean_logger("DD traces not exported")
    else:
        clean_logger(f"DD traces exported to {endpoint_dd}")

    ddtrace.tracer._span_processors.append(dd_span_processor)  # type: ignore

    if len(ddtrace.config._propagation_style_extract) != 3:
        clean_logger(
            "ddtrace WAS IMPORTED BY ANOTHER MODULE BEFORE troncos INITIALIZED IT. THIS IS BAD!",  # noqa: E501
            "WARNING",
        )

    ddtrace.patch_all()  # TODO: Allow people to do what they want here!
