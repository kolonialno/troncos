import os
import sys

from opentelemetry.exporter.otlp.proto.http import trace_exporter
from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from structlog import get_logger

logger = get_logger()


def _bool_from_string(s: str) -> bool:
    return s.lower() in ["1", "true", "yes"]


def get_otel_span_processors(endpoint: str) -> list[SpanProcessor]:
    """
    Build a list of span processors to use to process otel spans.
    """

    span_processors: list[SpanProcessor] = []

    # Exporter
    exporter = trace_exporter.OTLPSpanExporter(endpoint=endpoint)
    span_processors.append(BatchSpanProcessor(exporter))

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
