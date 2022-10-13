from typing import Sequence

from opentelemetry.exporter.otlp.proto.grpc import trace_exporter as grpc_trace_exporter
from opentelemetry.exporter.otlp.proto.http import trace_exporter
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.sdk.util.instrumentation import (
    InstrumentationInfo,
    InstrumentationScope,
)


def fix_span(sdk_span: ReadableSpan) -> None:
    sdk_span._instrumentation_scope = InstrumentationScope(
        name=sdk_span.name,
        version="0.0.0",
    )
    sdk_span._instrumentation_info = InstrumentationInfo(
        name=sdk_span.name,
        version="0.0.0",
    )
    if "resource" in sdk_span.attributes:  # type: ignore[operator]
        sdk_span._name = sdk_span.attributes["resource"]  # type: ignore # noqa: E501


class OTLPGrpcSpanExporterDD(grpc_trace_exporter.OTLPSpanExporter):
    def _translate_data(
        self, data: Sequence[ReadableSpan]
    ) -> ExportTraceServiceRequest:
        for sdk_span in data:
            fix_span(sdk_span)
        return super()._translate_data(data)


class OTLPHttpSpanExporterDD(trace_exporter.OTLPSpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for sdk_span in spans:
            fix_span(sdk_span)
        return super().export(spans)
