import contextlib
import logging
import random
import sys
from contextlib import _GeneratorContextManager
from typing import Any, Iterator, Tuple

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import IdGenerator, SpanProcessor, TracerProvider
from opentelemetry.trace import Span, Status, StatusCode, Tracer, set_tracer_provider
from opentelemetry.trace.propagation import tracecontext

from troncos import OTEL_LIBRARY_NAME

logger = logging.getLogger(__name__)


class _OtelIdGenerator(IdGenerator):
    def __init__(self) -> None:
        self._trace_id: int | None = None
        self._span_id: int | None = None

    def generate_span_id(self) -> int:
        if not self._span_id:
            logger.warning("No span_id set in generator")
            return random.randint(0, sys.maxsize)
        return self._span_id

    def generate_trace_id(self) -> int:
        if not self._trace_id:
            logger.warning("No trace_id set in generator")
            return random.randint(0, sys.maxsize)
        return self._trace_id

    @contextlib.contextmanager
    def with_ids(self, trace_id: int, span_id: int) -> Iterator[None]:
        self._trace_id = trace_id
        self._span_id = span_id
        yield
        self._trace_id = None
        self._span_id = None


class OtelTracerProvider:
    def __init__(
        self,
        span_processors: list[SpanProcessor],
        service: str,
        env: str | None,
        version: str | None,
    ) -> None:
        self._span_processors = span_processors
        self._id_gen = _OtelIdGenerator()
        self._trace_providers: dict[str, TracerProvider] = {}
        self._info_service = service
        self._info_env = env
        self._info_version = version
        attributes: dict[str, str] = {}
        if env:
            attributes["environment"] = env
        if version:
            attributes["version"] = version
        set_tracer_provider(self._get_tracer_provider(attributes=attributes))

    def get_id_generator(self) -> _OtelIdGenerator:
        return self._id_gen

    def _get_tracer_provider(
        self, name: str | None = None, attributes: dict[str, str] | None = None
    ) -> TracerProvider:
        p_name = name or self._info_service
        p_prov = self._trace_providers.get(p_name)
        if not p_prov:
            attributes = attributes or {}
            attributes["service.name"] = p_name
            resource = Resource.create(attributes)  # type: ignore
            p_prov = TracerProvider(resource=resource)
            p_prov.id_generator = self.get_id_generator()  # type: ignore
            for span_processor in self._span_processors:
                p_prov.add_span_processor(span_processor)
            self._trace_providers[p_name] = p_prov
        return p_prov

    def get_tracer(self, name: str | None = None) -> Tracer:
        return self._get_tracer_provider(name).get_tracer(OTEL_LIBRARY_NAME)


class DDSpanProcessor:
    def __init__(
        self, otel_tracer_provider: OtelTracerProvider, dd_traces_exported: bool
    ) -> None:
        self._otel = otel_tracer_provider
        self._propagator = tracecontext.TraceContextTextMapPropagator()
        self._otel_spans: dict[int, Tuple[_GeneratorContextManager[Span], Span]] = {}
        self._dd_traces_exported = dd_traces_exported

    @staticmethod
    def _translate_data(dd_span: Any, otel_span: Span) -> None:
        dd_span_attr: dict[str, Any] = {
            **dd_span._meta,
            **dd_span._metrics,
        }
        dd_span_ignore_attr = [
            "runtime-id",
            "_dd.agent_psr",
            "_dd.top_level",
            "_dd.measured",
            "env",
            "version",
        ]
        dd_span_err_attr_mapping = {
            "error.msg": "exception.message",
            "error.type": "exception.type",
            "error.stack": "exception.stacktrace",
        }
        otel_error_attr_dict = {}
        for k, v in dd_span_attr.items():
            otel_err_attr = dd_span_err_attr_mapping.get(k)
            if otel_err_attr:
                otel_error_attr_dict[otel_err_attr] = v
            elif k not in dd_span_ignore_attr:
                otel_span.set_attribute(k, v)

        if otel_error_attr_dict:
            otel_span.set_attributes(otel_error_attr_dict)
            otel_span.add_event(name="exception", attributes=otel_error_attr_dict)

            status_exp_type = otel_error_attr_dict.get("exception.type", None)
            status_exp_msg = otel_error_attr_dict.get("exception.message", None)

            otel_span.set_status(
                Status(
                    status_code=StatusCode.ERROR,
                    description=f"{status_exp_type}: {status_exp_msg}",
                )
            )

    @staticmethod
    def _get_service_name(service: str | None) -> str | None:
        if service in ["fastapi", "flask", "starlette", "django"]:
            return None
        return service

    def on_span_start(self, dd_span: Any) -> None:
        otel_tracer = self._otel.get_tracer(self._get_service_name(dd_span.service))

        context = None
        if dd_span.parent_id and not dd_span._parent:
            # This span has an external parent, extract that
            parent_trace_id = f"{dd_span.trace_id:x}".zfill(32)
            parent_span_id = f"{dd_span.parent_id:x}".zfill(16)
            trace_ctx = {
                "traceparent": f"00-{parent_trace_id}-{parent_span_id}-01",
            }
            context = self._propagator.extract(carrier=trace_ctx)

        with self._otel.get_id_generator().with_ids(dd_span.trace_id, dd_span.span_id):
            otel_ctx = otel_tracer.start_as_current_span(dd_span.name, context=context)
            otel_span = otel_ctx.__enter__()

            if self._dd_traces_exported:
                otel_span.set_attribute("dd_trace_id", str(dd_span.trace_id))
                otel_span.set_attribute("dd_span_id", str(dd_span.span_id))
            if dd_span.name != dd_span.resource:
                otel_span.set_attribute("resource", dd_span.resource)

            self._otel_spans[dd_span.span_id] = (otel_ctx, otel_span)

    def on_span_finish(self, dd_span: Any) -> None:
        otel_ctx, otel_span = self._otel_spans.pop(dd_span.span_id)
        self._translate_data(dd_span, otel_span)
        otel_ctx.__exit__(None, None, None)
