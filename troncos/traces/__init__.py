import logging
import os
import sys
from typing import Any

import opentelemetry
from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from troncos._ddlazy import ddlazy
from troncos.traces.dd_shim import DDSpanProcessor

logger = logging.getLogger(__name__)
TRACE_HEADERS = [
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


def _create_span_processor(
    service_name: str,
    service_env: str | None = None,
    service_version: str | None = None,
    service_attributes: dict[str, str] | None = None,
    endpoint: str | SpanProcessor | None = None,
    endpoint_dd: str | None = None,
) -> DDSpanProcessor:
    """
    Creates a DD span processor that converts DD spans into OTEL spans
    """

    flush_on_shutdown = True
    otel_span_processors: list[SpanProcessor] = []
    if endpoint:
        if isinstance(endpoint, SpanProcessor):
            otel_span_processors.append(endpoint)
        else:
            # Create an exporter
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
                    BatchSpanProcessor(
                        trace_exporter.OTLPSpanExporter(endpoint=endpoint)
                    )
                )
    else:
        if _bool_from_string(os.environ.get("TRONCOS_REUSE_OTEL_PROCESSOR", "false")):
            tp = opentelemetry.trace.get_tracer_provider()
            if hasattr(tp, "_active_span_processor"):
                logger.info("Reusing OTEL span processor")
                otel_span_processors.append(tp._active_span_processor)
                flush_on_shutdown = False

    # Fallback to InMemorySpanExporter
    if len(otel_span_processors) == 0:
        logger.warning("No OTEL span processor configured")

    # Setup OTEL debug processor
    otel_trace_debug = _bool_from_string(os.environ.get("OTEL_TRACE_DEBUG", "false"))
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

    service_attributes = service_attributes or {}

    if service_env:
        service_attributes["environment"] = service_env

    if service_version:
        service_attributes["version"] = service_version

    return DDSpanProcessor(
        service_name,
        service_attributes,
        otel_span_processors,
        dd_traces_exported=endpoint_dd is not None,
        flush_on_shutdown=flush_on_shutdown,
    )


def _bool_from_string(s: str) -> bool:
    return s.lower() in ["1", "true", "yes"]


def _class_index(some_list: list[Any], k: Any) -> int | None:
    for index, thing in enumerate(some_list):
        if isinstance(thing, k):
            return index
    return None


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

    if ddlazy.dd_initialized():
        logger.warning("Function 'init_tracing_basic' called multiple times!")
        return

    if _bool_from_string(os.environ.get("TRONCOS_OMIT_ROOT_CONTEXT_DETACH", "false")):
        logger.warning("TRONCOS_OMIT_ROOT_CONTEXT_DETACH is no longer needed!")

    # Create custom span processor
    custom_dd_span_processor = _create_span_processor(
        service_name=service_name,
        service_env=service_env,
        service_version=service_version,
        service_attributes=service_attributes,
        endpoint=endpoint,
        endpoint_dd=endpoint_dd,
    )

    # Set service info
    service_env = service_env or "unset"
    service_version = service_version or "unset"
    os.environ.setdefault("DD_SERVICE", service_name)
    os.environ.setdefault("DD_ENV", service_env)
    os.environ.setdefault("DD_VERSION", service_version)

    # Set propagation info
    prop_extract_key = "DD_TRACE_PROPAGATION_STYLE_EXTRACT"
    prop_extract_val = "tracecontext,b3multi,b3 single header,datadog"
    os.environ.setdefault(prop_extract_key, prop_extract_val)

    prop_inject_key = "DD_TRACE_PROPAGATION_STYLE_INJECT"
    prop_inject_val = "tracecontext,b3 single header"
    os.environ.setdefault(prop_inject_key, prop_inject_val)

    # Disable telemetry and startup logs
    os.environ.setdefault("DD_INSTRUMENTATION_TELEMETRY_ENABLED", "false")
    os.environ.setdefault("DD_TRACE_STARTUP_LOGS", "false")

    # Setup dd endpoint
    if endpoint_dd:
        os.environ.setdefault("DD_TRACE_AGENT_URL", endpoint_dd)
        logger.info(f"DD traces exported to {endpoint_dd}")
    else:
        logger.info("DD traces not exported")

    ddtrace_already_imported = "ddtrace" in sys.modules

    # Initialize ddtrace
    import ddtrace

    # Shutdown default tracer immediately
    try:
        ddtrace.tracer.shutdown()
    except ValueError:
        pass

    class _PatchedDDTracer(ddtrace.Tracer):
        # Since we cannot patch _default_span_processors_factory,
        # we patch all functions that call it
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            super().__init__(*args, **kwargs)
            self._fix_span_processors()

        def configure(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            super().configure(*args, **kwargs)
            self._fix_span_processors()

        def _child_after_fork(self):  # type: ignore[no-untyped-def]
            super()._child_after_fork()  # type: ignore[no-untyped-call]
            self._fix_span_processors()

        def _fix_span_processors(self) -> None:
            processors = self._span_processors

            # Remove dd span aggregator if needed
            dd_span_aggregator = _class_index(
                processors, ddtrace.internal.processor.trace.SpanAggregator
            )
            if dd_span_aggregator and not endpoint_dd:
                processors.pop(dd_span_aggregator)

            # Add custom processor
            if not _class_index(processors, DDSpanProcessor):
                processors.append(custom_dd_span_processor)  # type: ignore[arg-type]

    # Patch dd tracer and create new tracer
    ddtrace.Tracer = _PatchedDDTracer  # type: ignore[misc]
    ddtrace.tracer = ddtrace.Tracer()  # type: ignore[no-untyped-call]

    # Check if someone imported ddtrace before us. We do this by checking if the
    # variables we set above were in fact used
    if ddtrace_already_imported:
        logger.warning(
            "DETECTED THAT ddtrace WAS IMPORTED BY ANOTHER MODULE BEFORE 'init_tracing_basic' WAS CALLED. THIS IS BAD!",  # noqa: E501
        )

        # Try to fix what we can in this situation

        if os.environ.get(prop_inject_key) == prop_inject_val:
            inject_set = set()
            inject_set.add(
                ddtrace.internal.constants._PROPAGATION_STYLE_W3C_TRACECONTEXT
            )
            inject_set.add(
                ddtrace.internal.constants.PROPAGATION_STYLE_B3_SINGLE_HEADER
            )
            ddtrace.config._propagation_style_inject = inject_set  # type: ignore[assignment] # noqa: E501

        if os.environ.get(prop_extract_key) == prop_extract_val:
            extract_set = ddtrace.internal.constants.PROPAGATION_STYLE_ALL
            ddtrace.config._propagation_style_extract = extract_set  # type: ignore[assignment] # noqa: E501

    # Configure what headers to trace
    ddtrace.config.trace_headers(TRACE_HEADERS)  # type: ignore[no-untyped-call]

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
