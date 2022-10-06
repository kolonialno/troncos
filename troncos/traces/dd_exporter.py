from typing import Sequence

from opentelemetry.exporter.otlp.proto.http import trace_exporter
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.sdk.util.instrumentation import (
    InstrumentationInfo,
    InstrumentationScope,
)


class OTLPSpanExporterDD(trace_exporter.OTLPSpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for sdk_span in spans:
            sdk_span._instrumentation_scope = InstrumentationScope(
                name=sdk_span.name,  # type: ignore # noqa: E501
                version="0.0.0",
            )
            sdk_span._instrumentation_info = InstrumentationInfo(
                name=sdk_span.name,  # type: ignore # noqa: E501
                version="0.0.0",
            )
            if "resource" in sdk_span.attributes:
                sdk_span._name = sdk_span.attributes["resource"]
        return super().export(spans)
