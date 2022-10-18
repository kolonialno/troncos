from typing import Sequence

try:
    from opentelemetry.exporter.otlp.proto.grpc import (  # type: ignore
        trace_exporter as grpc_trace_exporter,
    )
except ImportError:  # pragma: no cover
    grpc_trace_exporter = None

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

    attr: dict[str, str] = sdk_span._attributes  # type: ignore

    # This is a server request span, set resource to something useful
    if "http.method" in attr:
        if "http.route" in attr:
            attr["resource"] = f"{attr['http.method']} {attr['http.route']}"
        elif "http.target" in attr:
            attr["resource"] = f"{attr['http.method']} {attr['http.target']}"
        else:
            attr["resource"] = f"{attr['http.method']}"

    # Set span name to resource if available
    if "resource" in attr:
        sdk_span._name = attr["resource"]


class OTLPGrpcSpanExporterDD(grpc_trace_exporter.OTLPSpanExporter if grpc_trace_exporter else object):  # type: ignore  # noqa: E501
    def _translate_data(
        self, data: Sequence[ReadableSpan]
    ) -> ExportTraceServiceRequest:
        for sdk_span in data:
            fix_span(sdk_span)
        return super()._translate_data(data)  # type: ignore


class OTLPHttpSpanExporterDD(trace_exporter.OTLPSpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for sdk_span in spans:
            fix_span(sdk_span)
        return super().export(spans)
