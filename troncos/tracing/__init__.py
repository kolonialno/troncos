from typing import Any

from ddtrace.trace import tracer

from ._exporter import Exporter, ExporterType
from ._writer import OTELWriter

__all__ = ["Exporter", "ExporterType", "configure_tracer", "create_trace_writer"]


def create_trace_writer(
    *,
    service_name: str,
    exporter: Exporter | None = None,
    resource_attributes: dict[str, Any] | None = None,
) -> OTELWriter:
    """Create a trace writer that writes traces to the otel tracing backend."""

    if exporter is None:
        exporter = Exporter()

    # Initialize our custom writer used to handle ddtrace spans.
    return OTELWriter(
        service_name=service_name,
        exporter=exporter,
        resource_attributes=resource_attributes,
    )


def configure_tracer(
    *,
    service_name: str,
    exporter: Exporter | None = None,
    resource_attributes: dict[str, Any] | None = None,
) -> None:
    """Configure ddtrace to write traces to the otel tracing backend."""

    writer = create_trace_writer(
        service_name=service_name,
        exporter=exporter,
        resource_attributes=resource_attributes,
    )

    tracer._configure(writer=writer)
