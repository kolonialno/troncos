from typing import Any, Dict, Optional, Union

from opentelemetry.attributes import BoundedAttributes  # type: ignore[attr-defined]
from opentelemetry.sdk.resources import Attributes, Resource
from opentelemetry.sdk.trace import (
    EventBase,
    ReadableSpan,
    Span,
    SpanContext,
    SpanProcessor,
    _UnsetLimits,
)
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.span import TraceFlags
from opentelemetry.util.types import AttributeValue

from troncos import OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION

_instrumentation_scope = InstrumentationScope(OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION)
_default_trace_flags = TraceFlags(1)
_span_kind_map = {
    "server": SpanKind.SERVER,
    "client": SpanKind.CLIENT,
    "producer": SpanKind.PRODUCER,
    "consumer": SpanKind.CONSUMER,
    "internal": SpanKind.INTERNAL,
}


def _internal_span_context(dd_span: Any) -> SpanContext:
    return SpanContext(
        dd_span.trace_id, dd_span.span_id, False, trace_flags=_default_trace_flags
    )


class _TranslatedSpan(Span):
    def __init__(
        self,
        dd_span: Any,
        base_resources: Attributes,
        default_resource: Resource,
        dd_traces_exported: bool,
        ignore_attrs: list[str],
    ) -> None:
        ReadableSpan.__init__(
            self,
            dd_span.name,
            _internal_span_context(dd_span),
            parent=self._create_parent_context(dd_span),
            resource=self._create_resource(dd_span, base_resources, default_resource),
            kind=self._create_span_kind(dd_span),
            instrumentation_scope=_instrumentation_scope,
        )
        self._limits = _UnsetLimits
        self._events = self._new_events()  # type: ignore[no-untyped-call]
        self._raw_attributes: Attributes = {}

        self._start_time = dd_span.start_ns
        self._apply_translation(dd_span, ignore_attrs)
        if dd_traces_exported:
            self._raw_attributes["dd_trace_id"] = str(dd_span.trace_id)
            self._raw_attributes["dd_span_id"] = str(dd_span.span_id)

        self._end_time = dd_span.start_ns + dd_span.duration_ns
        self._attributes = BoundedAttributes(
            _UnsetLimits.max_span_attributes,
            self._raw_attributes,
            immutable=True,
            max_value_len=_UnsetLimits.max_span_attribute_length,
        )

    @staticmethod
    def _create_parent_context(dd_span: Any) -> SpanContext | None:
        if dd_span.parent_id:
            if not dd_span._parent:
                # External trace parent
                return SpanContext(dd_span.trace_id, dd_span.parent_id, True)
            else:
                return _internal_span_context(dd_span._parent)
        return None

    @staticmethod
    def _create_resource(
        dd_span: Any, base_attributes: Attributes, default_resource: Resource
    ) -> Resource:
        if default_resource.attributes["service.name"] == dd_span.service:
            return default_resource
        elif dd_span.service in ["fastapi", "flask", "starlette", "django"]:
            return default_resource

        # The resource constructor copies everything, so we just
        # set the service.name temporarily
        old_service = base_attributes["service.name"]
        base_attributes["service.name"] = dd_span.service
        res = Resource(base_attributes)
        base_attributes["service.name"] = old_service
        return res

    @staticmethod
    def _create_span_kind(dd_span: Any) -> SpanKind:
        dd_kind = dd_span._meta.get("span.kind", "none")
        return _span_kind_map.get(dd_kind, SpanKind.INTERNAL)

    def _apply_translation(self, dd_span: Any, ignore_attrs: list[str]) -> None:
        otel_error_attr_dict = {}
        self._raw_attributes["resource"] = dd_span.resource

        if dd_span.span_type:
            self._raw_attributes["dd_type"] = dd_span.span_type

        # Collect all "attributes" from the dd span
        dd_span_attr: dict[str, Any] = {
            **dd_span._meta,
            **dd_span._metrics,
        }
        dd_span_err_attr_mapping = {
            "error.msg": "exception.message",
            "error.type": "exception.type",
            "error.stack": "exception.stacktrace",
        }

        # Map set OTEL attributes based on DD attributes
        for k, v in dd_span_attr.items():
            otel_err_attr = dd_span_err_attr_mapping.get(k)
            if k.startswith("_dd"):
                continue
            elif otel_err_attr:
                otel_error_attr_dict[otel_err_attr] = v
            elif k not in ignore_attrs:
                self._raw_attributes[k] = v

        # Map exception attributes
        if otel_error_attr_dict:
            self.add_event(name="exception", attributes=otel_error_attr_dict)

            status_exp_type = otel_error_attr_dict.get("exception.type", None)
            status_exp_msg = otel_error_attr_dict.get("exception.message", None)

            self._status = Status(
                status_code=StatusCode.ERROR,
                description=f"{status_exp_type}: {status_exp_msg}",
            )

    def _add_event(self, event: EventBase) -> None:
        self._events.append(event)  # type: ignore[attr-defined]

    def set_attribute(self, key: str, value: AttributeValue) -> None:
        assert False, "Use 'self._raw_attributes[key] = value' instead"

    def set_attributes(self, attributes: Dict[str, AttributeValue]) -> None:
        assert False, "Use 'self._raw_attributes[key] = value' instead"

    def set_status(
        self,
        status: Union[Status, StatusCode],
        description: Optional[str] = None,
    ) -> None:
        assert False, "Use 'self._status = status' instead"


class DDSpanProcessor:
    """
    A ddtrace span processor that translates dd spans into otel span and
    sends them to otel span processors
    """

    def __init__(
        self,
        service_name: str,
        service_attributes: dict[str, str] | None,
        otel_span_processors: list[SpanProcessor],
        dd_traces_exported: bool = False,
        flush_on_shutdown: bool = True,
    ) -> None:
        self._otel_procs = otel_span_processors
        self._base_resources = {
            **(service_attributes or {}),
            **{"service.name": service_name},
        }
        self._default_resource = Resource(self._base_resources)  # type: ignore[arg-type] # noqa: 501
        self._dd_traces_exported = dd_traces_exported
        self._flush_on_shutdown = flush_on_shutdown
        self._dd_span_ignore_attr = [
            "runtime-id",
            "_sampling_priority_v1",
            "env",
            "version",
            "span.kind",
        ]
        for k in self._base_resources:
            self._dd_span_ignore_attr.append(k)

    def on_span_start(self, dd_span: Any) -> None:
        pass

    def on_span_finish(self, dd_span: Any) -> None:
        span = _TranslatedSpan(
            dd_span,
            base_resources=self._base_resources,  # type: ignore[arg-type]
            dd_traces_exported=self._dd_traces_exported,
            default_resource=self._default_resource,
            ignore_attrs=self._dd_span_ignore_attr,
        )
        for p in self._otel_procs:
            p.on_end(span)

    def shutdown(self, timeout: int) -> None:
        if self._flush_on_shutdown:
            for p in self._otel_procs:
                p.force_flush(timeout_millis=timeout)
                p.shutdown()
