import logging
import os
import sys

from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from troncos._ddlazy import ddlazy

logger = logging.getLogger(__name__)


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
    patch_modules: list[str] | None = None,
    ignored_paths: list[str] | None = None,  # TODO: FIX
) -> None:
    service_version = service_version or "unset"
    # Set variables
    os.environ.setdefault("DD_SERVICE", service_name)
    os.environ.setdefault("DD_ENV", service_env or "unset")
    os.environ.setdefault("DD_VERSION", service_version or "unset")

    # Setup OTEL exporter
    otel_span_processors: list[SpanProcessor] = []
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc import (  # isort: skip # noqa: 501
                trace_exporter,
            )

            logger.info("OTEL using GRPC exporter")
        except ImportError:  # pragma: no cover
            try:
                from opentelemetry.exporter.otlp.proto.http import trace_exporter  # type: ignore # isort: skip # noqa: 501

                logger.info("OTEL using HTTP exporter")
            except ImportError:  # pragma: no cover
                trace_exporter = None  # type: ignore

        if trace_exporter:
            logger.info(f"OTEL traces exported to {endpoint}")
            otel_span_processors.append(
                BatchSpanProcessor(trace_exporter.OTLPSpanExporter(endpoint=endpoint))
            )

    if len(otel_span_processors) == 0:
        logger.warning("No OTEL span processor configured")
        otel_span_processors.append(SimpleSpanProcessor(InMemorySpanExporter()))  # type: ignore # noqa: E501

    # Setup OTEL debug processor
    otel_trace_debug = os.environ.get("OTEL_TRACE_DEBUG")
    otel_trace_debug_file = os.environ.get("OTEL_TRACE_DEBUG_FILE")
    if otel_trace_debug:
        logger.info(f"OTEL debug processor to {otel_trace_debug_file or 'stdout'}")
        debug_out = (
            sys.stdout
            if not otel_trace_debug_file
            else open(otel_trace_debug_file, "w")
        )
        otel_span_processors.append(
            SimpleSpanProcessor(ConsoleSpanExporter(out=debug_out))
        )

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
        os.environ.setdefault("DD_TRACE_AGENT_URL", endpoint_dd)

    os.environ.setdefault("DD_TRACE_PROPAGATION_STYLE_EXTRACT", "datadog,b3,b3 single header")
    os.environ.setdefault("DD_TRACE_PROPAGATION_STYLE_INJECT", "b3 single header")
    os.environ.setdefault("DD_INSTRUMENTATION_TELEMETRY_ENABLED", "false")

    import ddtrace

    if len(ddtrace.config._propagation_style_extract) != 3:
        logger.warning(
            "DETECTED THAT ddtrace WAS IMPORTED BY ANOTHER MODULE BEFORE 'init_tracing_basic' WAS CALLED. THIS IS BAD!",  # noqa: E501
        )
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
        logger.info("DD traces not exported")
    else:
        logger.info(f"DD traces exported to {endpoint_dd}")
        ddlazy._set_dd_trace_export_enabled(True)

    ddtrace.tracer._span_processors.append(dd_span_processor)  # type: ignore

    if patch_modules is None:
        ddtrace.patch_all()
    elif len(patch_modules) > 0:
        kwargs = {m: True for m in patch_modules}
        ddtrace.patch(**kwargs)



    ddlazy._load_dd_lazy()
