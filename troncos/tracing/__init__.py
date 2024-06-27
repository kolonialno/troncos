from typing import Any

import ddtrace

from ._exporter import Exporter, ExporterType
from ._writer import OTELWriter

__all__ = ["Exporter", "ExporterType"]


def configure_tracer(
    *,
    enabled: bool,
    service_name: str,
    exporter: Exporter | None = None,
    resource_attributes: dict[str, Any] | None = None,
) -> None:
    """Configure ddtrace to write traces to the otel tracing backend."""

    if exporter is None:
        exporter = Exporter()

    # Initialize our custom writer used to handle ddtrace spans.
    writer = OTELWriter(
        service_name=service_name,
        exporter=exporter,
        resource_attributes=resource_attributes,
    )

    ddtrace.tracer.configure(writer=writer, enabled=enabled)
