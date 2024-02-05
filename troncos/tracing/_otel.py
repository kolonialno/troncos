import os
import sys

from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HTTPSpanExporter,
)
from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)
from structlog import get_logger

from ._exporter import Exporter, ExporterType

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as GRPCSpanExporter,
    )
except ImportError:
    GRPCSpanExporter = None  # type: ignore


logger = get_logger()


def _bool_from_string(s: str) -> bool:
    return s.lower() in ["1", "true", "yes"]


def get_otel_span_processors(*, exporter: Exporter) -> list[SpanProcessor]:
    """
    Build a list of span processors to use to process otel spans.
    """

    span_processors: list[SpanProcessor] = []
    span_exporter: SpanExporter

    # Exporter
    if exporter.exporter_type == ExporterType.HTTP:
        span_exporter = HTTPSpanExporter(
            endpoint=exporter.endpoint, headers=exporter.headers
        )
    elif exporter.exporter_type == ExporterType.GRPC:
        if GRPCSpanExporter is None:
            raise RuntimeError(
                "opentelemetry-exporter-otlp-proto-grpc needs to be installed "
                "to use the GRPC exporter."
            )

        span_exporter = GRPCSpanExporter(
            endpoint=exporter.endpoint, headers=exporter.headers
        )
    else:
        raise RuntimeError("Unsupported span exporter.")

    span_processors.append(BatchSpanProcessor(span_exporter))

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
        span_processors.append(SimpleSpanProcessor(ConsoleSpanExporter(out=debug_out)))

    return span_processors
