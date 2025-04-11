from typing import Any

from ddtrace.trace import Span
from ddtrace.internal.writer.writer import TraceWriter
from opentelemetry.sdk.resources import Resource

from ._exporter import Exporter
from ._otel import get_otel_span_processors
from ._span import default_ignore_attrs, translate_span


class OTELWriter(TraceWriter):
    def __init__(
        self,
        enabled: bool,
        service_name: str,
        exporter: Exporter,
        resource_attributes: dict[str, Any] | None,
    ) -> None:
        self.enabled = enabled
        self.service_name = service_name
        self.resource_attributes = resource_attributes
        self.exporter = exporter

        self.otel_span_processors = get_otel_span_processors(exporter=exporter)
        self.otel_default_resource = Resource.create(
            {"service.name": service_name, **(resource_attributes or {})}
        )
        self.otel_ignore_attrs = (
            set(self.otel_default_resource.attributes.keys()) | default_ignore_attrs()
        )

    def recreate(self) -> "OTELWriter":
        return self.__class__(
            self.enabled,
            self.service_name,
            self.exporter,
            self.resource_attributes,
        )

    def write(self, spans: list[Span] | None = None) -> None:
        if not self.enabled:
            return

        if not spans:
            return

        filtered_spans = [
            span
            for span in spans
            # ddtrace use span.sampled == False to drop spans.
            if (
                # ddtrace uses sampling_priority > 0 to indicate that we
                # want to ingest the span.
                span.context.sampling_priority is None
                or span.context.sampling_priority > 0
            )
        ]

        if not filtered_spans:
            return

        transelated_spans = [
            translate_span(
                span,
                default_resource=self.otel_default_resource,
                ignore_attrs=self.otel_ignore_attrs,
            )
            for span in filtered_spans
        ]

        for span_processor in self.otel_span_processors:
            for span in transelated_spans:
                span_processor.on_end(span)

    def stop(self, timeout: float | None = None) -> None:
        if not self.enabled:
            return

        for span_processor in self.otel_span_processors:
            span_processor.force_flush(
                timeout_millis=int(timeout * 1000) if timeout else 30000
            )
            span_processor.shutdown()

    def flush_queue(self) -> None:
        if not self.enabled:
            return

        for span_processor in self.otel_span_processors:
            span_processor.force_flush()
