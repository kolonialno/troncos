from typing import Sequence

from opentelemetry.exporter.otlp.proto.grpc import trace_exporter
from opentelemetry.exporter.otlp.proto.grpc.exporter import get_resource_data
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import (
    InstrumentationScope as InstrumentationScopePB,
)
from opentelemetry.proto.trace.v1.trace_pb2 import (
    ResourceSpans,
    ScopeSpans,
    Span as CollectorSpan,
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
        sdk_resource_scope_spans = {}

        for sdk_span in data:
            if "dd_operation_name" in sdk_span.attributes:
                # I did not find a good way to get rid of the span kind so these dd_operation_name
                # will almost always get '.internal' appended.. I've been told it's not much of a problem.
                sdk_span._instrumentation_scope = InstrumentationScope(
                    name=sdk_span.attributes["dd_operation_name"], version="0.0.0"
                )
                sdk_span._instrumentation_info = InstrumentationInfo(
                    name=sdk_span.attributes["dd_operation_name"], version="0.0.0"
                )

            scope_spans_map = sdk_resource_scope_spans.get(sdk_span.resource, {})
            # If we haven't seen the Resource yet, add it to the map
            if not scope_spans_map:
                sdk_resource_scope_spans[sdk_span.resource] = scope_spans_map
            scope_spans = scope_spans_map.get(sdk_span.instrumentation_scope)
            # If we haven't seen the InstrumentationScope for this Resource yet, add it to the map
            if not scope_spans:
                if sdk_span.instrumentation_scope is not None:
                    scope_spans_map[sdk_span.instrumentation_scope] = ScopeSpans(
                        scope=InstrumentationScopePB(
                            name=sdk_span.instrumentation_scope.name,
                            version=sdk_span.instrumentation_scope.version,
                        )
                    )
                else:
                    # If no InstrumentationScope, store in None key
                    scope_spans_map[sdk_span.instrumentation_scope] = ScopeSpans()
            scope_spans = scope_spans_map.get(sdk_span.instrumentation_scope)
            self._collector_kwargs = {}

            self._translate_name(sdk_span)
            self._translate_start_time(sdk_span)
            self._translate_end_time(sdk_span)
            self._translate_span_id(sdk_span)
            self._translate_trace_id(sdk_span)
            self._translate_parent(sdk_span)
            self._translate_context_trace_state(sdk_span)
            self._collector_kwargs["attributes"] = self._translate_attributes(
                sdk_span.attributes
            )
            self._translate_events(sdk_span)
            self._translate_links(sdk_span)
            self._translate_status(sdk_span)
            if sdk_span.dropped_attributes:
                self._collector_kwargs[
                    "dropped_attributes_count"
                ] = sdk_span.dropped_attributes
            if sdk_span.dropped_events:
                self._collector_kwargs["dropped_events_count"] = sdk_span.dropped_events
            if sdk_span.dropped_links:
                self._collector_kwargs["dropped_links_count"] = sdk_span.dropped_links

            self._collector_kwargs["kind"] = getattr(
                CollectorSpan.SpanKind,
                f"SPAN_KIND_{sdk_span.kind.name}",
            )

            scope_spans.spans.append(CollectorSpan(**self._collector_kwargs))

        return ExportTraceServiceRequest(
            resource_spans=get_resource_data(
                sdk_resource_scope_spans,
                ResourceSpans,
                "spans",
            )
        )
