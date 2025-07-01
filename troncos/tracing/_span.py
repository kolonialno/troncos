from typing import Any

from ddtrace import constants, ext
from ddtrace.trace import Span as DDSpan
from opentelemetry.attributes import BoundedAttributes
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import (
    _DEFAULT_OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT,
    _DEFAULT_OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT,
    _DEFAULT_OTEL_SPAN_EVENT_COUNT_LIMIT,
    Event,
    ReadableSpan,
)
from opentelemetry.sdk.util import BoundedList
from opentelemetry.trace import SpanContext, SpanKind, Status, StatusCode
from opentelemetry.trace.span import TraceFlags

_dd_span_ignore_attr = {
    "runtime-id",
    "_sampling_priority_v1",
    "env",
    "version",
    "span.kind",
}

_trace_flags_sampled = TraceFlags(1)


def _span_context(span: DDSpan) -> SpanContext:
    return SpanContext(
        trace_id=span.trace_id,
        span_id=span.span_id,
        is_remote=False,
        trace_flags=_trace_flags_sampled,
    )


def _parent_span_context(dd_span: DDSpan) -> SpanContext | None:
    if dd_span.parent_id:
        if not dd_span._parent:
            # External trace parent
            return SpanContext(dd_span.trace_id, dd_span.parent_id, True)
        else:
            return _span_context(dd_span._parent)

    return None


_span_kind_map = {
    ext.SpanKind.CLIENT: SpanKind.CLIENT,
    ext.SpanKind.SERVER: SpanKind.SERVER,
    ext.SpanKind.PRODUCER: SpanKind.PRODUCER,
    ext.SpanKind.CONSUMER: SpanKind.CONSUMER,
}


def _span_kind(dd_span: DDSpan) -> SpanKind:
    dd_kind = dd_span._meta.get(constants.SPAN_KIND, "none")
    return _span_kind_map.get(dd_kind, SpanKind.INTERNAL)


_dd_span_err_attr_mapping = {
    "error.msg": "exception.message",
    "error.type": "exception.type",
    "error.stack": "exception.stacktrace",
}


def _span_status_and_attributes(
    dd_span: DDSpan, ignore_attrs: set[str]
) -> tuple[Status, list[Event], dict[str, Any]]:
    # Collect all "attributes" from the dd span
    dd_span_attr: dict[str | bytes, Any] = {
        **dd_span._meta,
        **dd_span._metrics,
        "resource": dd_span.resource,
    }

    otel_attrs = {}
    events: list[Event] = []
    otel_error_attrs = {}

    # Map set OTEL attributes based on DD attributes
    for k, v in dd_span_attr.items():
        if isinstance(k, bytes):
            continue
        if k.startswith("_dd"):
            continue
        otel_err_attr = _dd_span_err_attr_mapping.get(k)
        if otel_err_attr:
            otel_error_attrs[otel_err_attr] = v
        elif k not in ignore_attrs:
            otel_attrs[k] = v

    if otel_error_attrs:
        events.append(
            Event(
                "exception",
                BoundedAttributes(
                    _DEFAULT_OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT,
                    attributes=otel_error_attrs,
                ),
            )
        )

        status_exp_type = otel_error_attrs.get("exception.type", None)
        status_exp_msg = otel_error_attrs.get("exception.message", None)

        status = Status(
            status_code=StatusCode.ERROR,
            description=f"{status_exp_type}: {status_exp_msg}",
        )
    else:
        status = Status(StatusCode.UNSET)

    return (status, events, otel_attrs)


def _span_resource(dd_span: DDSpan, default_resource: Resource) -> Resource:
    if default_resource.attributes[SERVICE_NAME] == dd_span.service:
        return default_resource

    if not dd_span.service:
        return default_resource

    base_attributes = dict(default_resource.attributes)
    base_attributes[SERVICE_NAME] = dd_span.service

    return Resource(base_attributes)


def default_ignore_attrs() -> set[str]:
    return _dd_span_ignore_attr


def translate_span(
    dd_span: DDSpan, default_resource: Resource, ignore_attrs: set[str]
) -> ReadableSpan:
    """Transelate a ddtrace span to an OTEL span."""
    assert dd_span.duration_ns is not None, "Span not finished."

    status, events, attributes = _span_status_and_attributes(
        dd_span, ignore_attrs=ignore_attrs
    )

    otel_span = ReadableSpan(
        name=dd_span.name,
        context=_span_context(dd_span),
        parent=_parent_span_context(dd_span),
        resource=_span_resource(dd_span, default_resource),
        attributes=BoundedAttributes(
            _DEFAULT_OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT, attributes=attributes
        ),
        events=BoundedList.from_seq(_DEFAULT_OTEL_SPAN_EVENT_COUNT_LIMIT, events),
        kind=_span_kind(dd_span),
        status=status,
        start_time=dd_span.start_ns,
        end_time=dd_span.start_ns + dd_span.duration_ns,
    )

    return otel_span
