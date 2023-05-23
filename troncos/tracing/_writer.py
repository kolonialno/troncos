from typing import Any

from ddtrace.internal.writer.writer import TraceWriter
from ddtrace.span import Span
from opentelemetry.sdk.resources import Resource

from ._otel import get_otel_span_processors
from ._span import transalate_span


class OTELWriter(TraceWriter):
    def __init__(
        self,
        service_name: str,
        service_attributes: dict[str, Any] | None,
        endpoint: str,
    ) -> None:
        self.service_name = service_name
        self.service_attributes = service_attributes
        self.endpoint = endpoint

        self.otel_span_processors = get_otel_span_processors(endpoint=endpoint)
        self.otel_default_resource = Resource.create(
            {"service.name": service_name, **(service_attributes or {})}
        )

    def recreate(self) -> "OTELWriter":
        return self.__class__(self.service_name, self.service_attributes, self.endpoint)

    def write(self, spans: list[Span] | None = None) -> None:
        transalated_spans = [
            transalate_span(span, default_resource=self.otel_default_resource)
            for span in spans or []
        ]

        for span_processor in self.otel_span_processors:
            for span in transalated_spans:
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
