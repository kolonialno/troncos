import logging
import os
import sys

from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from troncos.traces.dd_shim import DDSpanProcessor, OtelTracerProvider

logger = logging.getLogger(__name__)


def init_tracing_basic(
    service_name: str,
    service_env: str | None = None,
    service_version: str | None = None,
    endpoint: str | None = None,
    endpoint_dd: str | None = None,
    ignored_paths: list[str] | None = None,  # TODO: FIX
):
    service_version = service_version or "unset"
    # Set variables
    os.environ["DD_SERVICE"] = service_name
    os.environ["DD_ENV"] = service_env
    os.environ["DD_VERSION"] = service_version

    # Setup OTEL exporter
    otel_span_processors = []
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc import trace_exporter

            logger.info("OTEL using GRPC exporter")
        except ImportError:  # pragma: no cover
            try:
                from opentelemetry.exporter.otlp.proto.http import trace_exporter

                logger.info("OTEL using HTTP exporter")
            except ImportError:  # pragma: no cover
                trace_exporter = None
                logger.warning("OTEL exporter not setup")

        if trace_exporter:
            logger.info(f"OTEL traces exported to {endpoint}")
            otel_span_processors.append(
                BatchSpanProcessor(trace_exporter.OTLPSpanExporter(endpoint=endpoint))
            )
        else:
            logger.info("OTEL traces not exported")
    else:
        logger.info("OTEL traces not exported")

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

    os.environ["DD_INSTRUMENTATION_TELEMETRY_ENABLED"] = "false"
    if endpoint_dd:
        os.environ["DD_TRACE_AGENT_URL"] = endpoint_dd

    # Setup propagation
    os.environ["DD_TRACE_PROPAGATION_STYLE_INJECT"] = "datadog,b3,b3 single header"
    os.environ["DD_TRACE_PROPAGATION_STYLE_EXTRACT"] = "datadog,b3,b3 single header"

    import ddtrace

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

    ddtrace.tracer._span_processors.append(dd_span_processor)
    ddtrace.patch_all()  # TODO: Allow people to do what they want here!
