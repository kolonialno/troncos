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
from troncos.traces.dd_shim import DDSpanProcessor, OtelTracerProvider

logger = logging.getLogger(__name__)


def http_endpoint_from_env(host_var: str, port_var: str, path: str = "") -> str | None:
    """
    Simple helper function construct http endpoint from environment variables
    """

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
    service_attributes: dict[str, str] | None = None,
    endpoint: str | None = None,
    endpoint_dd: str | None = None,
    patch_modules: list[str] | None = None,
) -> None:
    """
    This function initializes tracing. It is important that it is call as early as
    possible in the execution of the program. It should be called before ddtrace
    is imported anywhere else.

    :param service_name:    Name of service ("myapi")
    :param service_env:     Optional service environment ("staging")
    :param service_version: Optional service version ("1.2.3")
    :param service_attributes: Optional service attributes
    :param endpoint:    Set this endpoint if you want to ship to Tempo
    :param endpoint_dd: Set this endpoint if you want to ship to DD
    :param patch_modules:   Optional list of modules that you want DD to patch, it
                            defaults to all modules
    """

    service_env = service_env or "unset"
    service_version = service_version or "unset"

    os.environ.setdefault("DD_SERVICE", service_name)
    os.environ.setdefault("DD_ENV", service_env)
    os.environ.setdefault("DD_VERSION", service_version)

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
                from opentelemetry.exporter.otlp.proto.http import trace_exporter  # type: ignore[no-redef] # isort: skip # noqa: 501

                logger.info("OTEL using HTTP exporter")
            except ImportError:  # pragma: no cover
                trace_exporter = None  # type: ignore[assignment]

        if trace_exporter:
            logger.info(f"OTEL traces exported to {endpoint}")
            otel_span_processors.append(
                BatchSpanProcessor(trace_exporter.OTLPSpanExporter(endpoint=endpoint))
            )

    # Fallback to InMemorySpanExporter
    if len(otel_span_processors) == 0:
        logger.warning("No OTEL span processor configured")
        otel_span_processors.append(SimpleSpanProcessor(InMemorySpanExporter()))  # type: ignore[no-untyped-call] # noqa: E501

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

    # Prepare to initialize ddtrace by initializing the DD shim
    otel_trace_provider = OtelTracerProvider(
        span_processors=otel_span_processors,
        service=service_name,
        attributes=service_attributes,
        env=service_env,
        version=service_version,
    )
    dd_span_processor = DDSpanProcessor(
        otel_tracer_provider=otel_trace_provider,
        tracer_attributes=service_attributes,
        dd_traces_exported=endpoint_dd is not None,
    )

    # Set some config variables before loading ddtrace
    os.environ.setdefault(
        "DD_TRACE_PROPAGATION_STYLE_EXTRACT",
        "tracecontext,b3multi,b3 single header,datadog",
    )
    os.environ.setdefault(
        "DD_TRACE_PROPAGATION_STYLE_INJECT", "tracecontext,b3 single header"
    )
    os.environ.setdefault("DD_INSTRUMENTATION_TELEMETRY_ENABLED", "false")
    if endpoint_dd:
        os.environ.setdefault("DD_TRACE_AGENT_URL", endpoint_dd)

    os.environ.setdefault("DD_TRACE_STARTUP_LOGS", "false")

    # Initialize ddtrace
    import ddtrace

    # Check if someone imported ddtrace before us. We do this by checking if the
    # variables we set above were in fact used
    if (
        not ddtrace.config._propagation_style_extract
        or len(ddtrace.config._propagation_style_extract) != 4
    ):
        logger.warning(
            "DETECTED THAT ddtrace WAS IMPORTED BY ANOTHER MODULE BEFORE 'init_tracing_basic' WAS CALLED. THIS IS BAD!",  # noqa: E501
        )
        # Try to fix what we can in this situation
        inject_set = set()
        inject_set.add(ddtrace.internal.constants._PROPAGATION_STYLE_W3C_TRACECONTEXT)
        inject_set.add(ddtrace.internal.constants.PROPAGATION_STYLE_B3_SINGLE_HEADER)
        extract_set = ddtrace.internal.constants.PROPAGATION_STYLE_ALL
        ddtrace.config._propagation_style_extract = extract_set  # type: ignore[assignment] # noqa: E501
        ddtrace.config._propagation_style_inject = inject_set  # type: ignore[assignment] # noqa: E501
        ddtrace.config.analytics_enabled = False

    # Configure what headers to trace
    ddtrace.config.trace_headers(  # type: ignore[no-untyped-call]
        [
            "accept",
            "cache-control",
            "content-security-policy",
            "content-type",
            "content-length",
            "expires",
            "location",
            "origin",
            "range",
            "referer",
            "retry-after",
            "server",
            "traceparent",
            "tracestate",
            "uber-trace-id",
            "x-b3-traceid",
            "x-country",
            "x-language",
            "x-xss-protection",
        ]
    )

    # Patch ddtrace span processors
    if not endpoint_dd:
        # Here we do not want to ship traces to DD, so we have to remove the
        # span processor that handles that operation.
        to_pop = None
        for i, s in enumerate(ddtrace.tracer._span_processors):
            if isinstance(s, ddtrace.internal.processor.trace.SpanAggregator):
                to_pop = i
        if to_pop:
            ddtrace.tracer._span_processors.pop(to_pop)
        logger.info("DD traces not exported")
    else:
        logger.info(f"DD traces exported to {endpoint_dd}")

    # Add out custom DD span processor
    ddtrace.tracer._span_processors.append(dd_span_processor)  # type: ignore[arg-type]

    # Set dd tracer tags if attributes are set
    if service_attributes:
        ddtrace.tracer.set_tags(service_attributes)

    # Patch either all modules, or the ones specified by the user
    if patch_modules is None:
        ddtrace.patch_all()
    elif len(patch_modules) > 0:
        kwargs = {m: True for m in patch_modules}
        ddtrace.patch(**kwargs)  # type: ignore[arg-type]

    # Mark ddtrace as initialized in ddlazy
    ddlazy._on_loaded(endpoint_dd is not None)
