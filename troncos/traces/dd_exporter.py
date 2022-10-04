from typing import Sequence

from opentelemetry.exporter.otlp.proto.grpc import trace_exporter
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.util.instrumentation import (
    InstrumentationInfo,
    InstrumentationScope,
)


class OTLPSpanExporterDD(trace_exporter.OTLPSpanExporter):
    def _translate_data(
        self, data: Sequence[ReadableSpan]
    ) -> ExportTraceServiceRequest:
        for sdk_span in data:
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
        return super()._translate_data(data)
