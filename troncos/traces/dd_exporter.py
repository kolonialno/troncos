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
            if "dd_operation_name" in sdk_span.attributes:  # type: ignore[operator]
                # I did not find a good way to get rid of the span kind so these
                # dd_operation_name will almost always get '.internal' appended.
                # I've been told it's not much of a problem.
                sdk_span._instrumentation_scope = InstrumentationScope(
                    name=sdk_span.attributes["dd_operation_name"],  # type: ignore # noqa: E501
                    version="0.0.0",
                )
                sdk_span._instrumentation_info = InstrumentationInfo(
                    name=sdk_span.attributes["dd_operation_name"],  # type: ignore # noqa: E501
                    version="0.0.0",
                )
        return super().export(spans)
