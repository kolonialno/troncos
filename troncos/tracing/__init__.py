from typing import Any

import ddtrace

from ._enums import Exporter, ExporterType
from ._writer import OTELWriter

__all__ = ["Exporter", "ExporterType"]


def configure_tracer(
    *,
    enabled: bool,
    endpoint: str,
    service_name: str,
    resource_attributes: dict[str, Any] | None = None,
    exporter: Exporter = Exporter.HTTP,
) -> None:
    """Configure ddtrace to write traces to the otel tracing backend."""

    # Initialize our custom writer used to handle ddtrace spans.
    writer = OTELWriter(
        service_name=service_name,
        resource_attributes=resource_attributes,
        endpoint=endpoint,
        exporter=exporter,
    )

    ddtrace.tracer.configure(writer=writer, enabled=enabled)
