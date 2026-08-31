"""Helpers for decoding the OTLP payloads that troncos exports.

Decoding the protobuf rather than matching raw bytes means a failure names the
attribute that went missing, which is what makes these tests useful after a
ddtrace or opentelemetry bump changes the translation.
"""

import gzip
from dataclasses import dataclass, field
from typing import Any

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Span as PBSpan
from opentelemetry.proto.trace.v1.trace_pb2 import Status as PBStatus
from pytest_httpserver import HTTPServer

# The all-zero span id protobuf uses to mean "no parent".
_NO_PARENT = b""


@dataclass(frozen=True)
class ExportedEvent:
    name: str
    attributes: dict[str, Any]


@dataclass(frozen=True)
class ExportedSpan:
    """A span as it arrived at the collector, with its resource flattened in."""

    name: str
    kind: str
    trace_id: bytes
    span_id: bytes
    parent_span_id: bytes
    attributes: dict[str, Any]
    events: list[ExportedEvent]
    status_code: str
    status_message: str
    resource_attributes: dict[str, Any] = field(default_factory=dict)
    start_time_unix_nano: int = 0
    end_time_unix_nano: int = 0

    @property
    def has_parent(self) -> bool:
        return self.parent_span_id != _NO_PARENT

    @property
    def service_name(self) -> str:
        value = self.resource_attributes.get("service.name")
        assert isinstance(value, str), f"span {self.name!r} has no service.name"
        return value

    @property
    def exception_events(self) -> list[ExportedEvent]:
        return [event for event in self.events if event.name == "exception"]


def _decode_any_value(value: AnyValue) -> Any:
    which = value.WhichOneof("value")
    if which is None:
        return None
    if which == "array_value":
        return [_decode_any_value(item) for item in value.array_value.values]
    if which == "kvlist_value":
        return _decode_attributes(value.kvlist_value.values)
    return getattr(value, which)


def _decode_attributes(attributes: Any) -> dict[str, Any]:
    return {kv.key: _decode_any_value(kv.value) for kv in attributes}


def _decode_span(span: PBSpan, resource_attributes: dict[str, Any]) -> ExportedSpan:
    return ExportedSpan(
        name=span.name,
        kind=str(PBSpan.SpanKind.Name(span.kind)),
        trace_id=span.trace_id,
        span_id=span.span_id,
        parent_span_id=span.parent_span_id,
        attributes=_decode_attributes(span.attributes),
        events=[
            ExportedEvent(
                name=event.name, attributes=_decode_attributes(event.attributes)
            )
            for event in span.events
        ],
        status_code=str(PBStatus.StatusCode.Name(span.status.code)),
        status_message=span.status.message,
        resource_attributes=resource_attributes,
        start_time_unix_nano=span.start_time_unix_nano,
        end_time_unix_nano=span.end_time_unix_nano,
    )


def spans_from_message(message: ExportTraceServiceRequest) -> list[ExportedSpan]:
    """Flatten an export request into spans, resource attributes folded in.

    Shared by both transports: OTLP/HTTP hands us bytes to parse, OTLP/gRPC
    hands the servicer an already-parsed message, and both must decode to the
    same ExportedSpan so the payload assertions can be transport-agnostic.
    """
    spans: list[ExportedSpan] = []
    for resource_spans in message.resource_spans:
        resource_attributes = _decode_attributes(resource_spans.resource.attributes)
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                spans.append(_decode_span(span, resource_attributes))
    return spans


def decode_request_body(
    body: bytes, content_encoding: str | None
) -> list[ExportedSpan]:
    if content_encoding == "gzip":
        body = gzip.decompress(body)

    message = ExportTraceServiceRequest()
    message.ParseFromString(body)

    return spans_from_message(message)


def exported_spans(httpserver: HTTPServer, path: str) -> list[ExportedSpan]:
    """Decode every span posted to `path`.

    Asserts each request was accepted, so a rejected payload surfaces as a
    failure rather than an empty result.
    """
    spans: list[ExportedSpan] = []
    for request, response in httpserver.log:
        if request.path != path:
            continue
        assert response.status_code == 200, (
            f"collector rejected an export with {response.status_code}"
        )
        spans.extend(
            decode_request_body(request.data, request.headers.get("content-encoding"))
        )
    return spans


def span_named(spans: list[ExportedSpan], name: str) -> ExportedSpan:
    matches = [span for span in spans if span.name == name]
    assert len(matches) == 1, (
        f"expected exactly 1 span named {name!r}, "
        f"got {len(matches)} (exported: {sorted(s.name for s in spans)})"
    )
    return matches[0]


__all__ = [
    "ExportedEvent",
    "ExportedSpan",
    "decode_request_body",
    "exported_spans",
    "span_named",
    "spans_from_message",
]
