from typing import Any

from ddtrace.internal.writer.writer import TraceWriter
from ddtrace.span import Span
from opentelemetry.sdk.resources import Resource

from ._enums import Exporter
from ._otel import get_otel_span_processors
from ._span import default_ignore_attrs, translate_span


class OTELWriter(TraceWriter):
    def __init__(
        self,
        service_name: str,
        service_attributes: dict[str, Any] | None,
        endpoint: str,
        exporter: Exporter,
    ) -> None:
        self.service_name = service_name
        self.service_attributes = service_attributes
        self.endpoint = endpoint
        self.exporter = exporter

        self.otel_span_processors = get_otel_span_processors(
            endpoint=endpoint, exporter=exporter
        )
        self.otel_default_resource = Resource.create(
            {"service.name": service_name, **(service_attributes or {})}
        )
        self.otel_ignore_attrs = (
            set(self.otel_default_resource.attributes.keys()) | default_ignore_attrs()
        )

    def recreate(self) -> "OTELWriter":
        return self.__class__(
            self.service_name,
            self.service_attributes,
            self.endpoint,
            exporter=self.exporter,
        )

    def write(self, spans: list[Span] | None = None) -> None:
        if not spans:
            return

        filtered_spans = [
            span
            for span in spans
            # ddtrace use span.sampled == False to drop spans.
            if span.sampled
            # ddtrace uses sampling_priority > 0 to indicate that we
            # want to ingest the span.
            and (
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
        for span_processor in self.otel_span_processors:
            span_processor.force_flush(
                timeout_millis=int(timeout * 1000) if timeout else 30000
            )
            span_processor.shutdown()

    def flush_queue(self) -> None:
        for span_processor in self.otel_span_processors:
            span_processor.force_flush()
