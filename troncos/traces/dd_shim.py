from typing import Any

from opentelemetry.sdk.resources import Attributes, Resource
from opentelemetry.sdk.trace import Span, SpanContext, SpanProcessor
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.span import TraceFlags

from troncos import OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION

_instrumentation_scope = InstrumentationScope(OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION)
_default_trace_flags = TraceFlags(1)


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
        super().__init__(
            dd_span.name,
            _internal_span_context(dd_span),
            parent=self._create_parent_context(dd_span),
            sampler=None,
            trace_config=None,
            resource=self._create_resource(dd_span, base_resources, default_resource),
            kind=self._create_span_kind(dd_span),
            instrumentation_scope=_instrumentation_scope,
        )
        self.start(dd_span.start_ns)
        self._apply_translation(dd_span, ignore_attrs)
        if dd_traces_exported:
            self.set_attributes(
                {
                    "dd_trace_id": str(dd_span.trace_id),
                    "dd_span_id": str(dd_span.span_id),
                }
            )
        self.end(dd_span.start_ns + dd_span.duration_ns)

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
        kind = SpanKind.INTERNAL
        if dd_span.span_type:
            if dd_span.span_type in ["template"]:
                kind = SpanKind.INTERNAL
            elif dd_span.span_type in ["web"]:
                kind = SpanKind.SERVER
            elif dd_span.span_type in ["worker"]:
                kind = SpanKind.CONSUMER
            else:
                kind = SpanKind.CLIENT
        elif dd_span.name in ["celery.apply"]:
            kind = SpanKind.PRODUCER
        return kind

    def _apply_translation(self, dd_span: Any, ignore_attrs: list[str]) -> None:
        otel_error_attr_dict = {}
        otel_span_attr = {
            "resource": dd_span.resource,
        }

        if dd_span.span_type:
            otel_span_attr["dd_type"] = dd_span.span_type

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
                otel_span_attr[k] = v

        self.set_attributes(otel_span_attr)

        # Map exception attributes
        if otel_error_attr_dict:
            # self.set_attributes(otel_error_attr_dict)  # Is this needed?
            self.add_event(name="exception", attributes=otel_error_attr_dict)

            status_exp_type = otel_error_attr_dict.get("exception.type", None)
            status_exp_msg = otel_error_attr_dict.get("exception.message", None)

            self.set_status(
                Status(
                    status_code=StatusCode.ERROR,
                    description=f"{status_exp_type}: {status_exp_msg}",
                )
            )


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
