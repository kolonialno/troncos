from typing import Any

from ddtrace.trace import tracer, Tracer
from ddtrace.internal.service import ServiceStatusError
from ._exporter import Exporter, ExporterType
from ._writer import OTELWriter

__all__ = ["Exporter", "ExporterType", "configure_tracer", "create_trace_writer"]


def create_trace_writer(
    *,
    enabled: bool,
    service_name: str,
    exporter: Exporter | None = None,
    resource_attributes: dict[str, Any] | None = None,
) -> OTELWriter:
    """Create a trace writer that writes traces to the otel tracing backend."""

    if exporter is None:
        exporter = Exporter()

    # Initialize our custom writer used to handle ddtrace spans.
    return OTELWriter(
        enabled=enabled,
        service_name=service_name,
        exporter=exporter,
        resource_attributes=resource_attributes,
    )


def _replace_writer(_tracer: Tracer, writer: OTELWriter) -> None:
    """Replace the writer used by the tracer."""
    try:
        _tracer._span_aggregator.writer.stop()
    except ServiceStatusError:
        pass

    _tracer._span_aggregator.writer = writer
    _tracer._recreate()  # type: ignore

    # Make sure the new writer is used
    assert isinstance(_tracer._span_aggregator.writer, OTELWriter)


def configure_tracer(
    *,
    service_name: str,
    exporter: Exporter | None = None,
    resource_attributes: dict[str, Any] | None = None,
    enabled: bool = True,
) -> None:
    """Configure ddtrace to write traces to the otel tracing backend."""

    writer = create_trace_writer(
        service_name=service_name,
        exporter=exporter,
        resource_attributes=resource_attributes,
        enabled=enabled,
    )

    _replace_writer(tracer, writer)
