import contextlib
import logging
import random
import sys
from contextvars import Token
from typing import Any, Iterator, Tuple

from opentelemetry import context as context_api
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import IdGenerator, SpanProcessor, TracerProvider
from opentelemetry.trace import (
    Span,
    SpanKind,
    Status,
    StatusCode,
    Tracer,
    set_tracer_provider,
)
from opentelemetry.trace.propagation import _SPAN_KEY, tracecontext

from troncos import OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION

logger = logging.getLogger(__name__)


class _OtelIdGenerator(IdGenerator):
    """
    Handles generation of trace and span ids for OTEL. It expects that you provide
    the IDs your self before attempting to create the span. It falls back to random
    IDs.
    """

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
    """
    Handles dynamic creation of OTEL tracer providers based on names.
    """

    def __init__(
        self,
        span_processors: list[SpanProcessor],
        service: str,
        env: str | None,
        version: str | None,
        attributes: dict[str, str] | None,
    ) -> None:
        self._span_processors = span_processors
        self._id_gen = _OtelIdGenerator()
        self._trace_providers: dict[str, TracerProvider] = {}
        self._info_service = service
        self._info_env = env
        self._info_version = version
        self._attributes: dict[str, str] = attributes or {}
        extra_attributes = {}
        if env:
            extra_attributes["environment"] = env
        if version:
            extra_attributes["version"] = version
        set_tracer_provider(
            self._get_tracer_provider(extra_attributes=extra_attributes)
        )

    def get_id_generator(self) -> _OtelIdGenerator:
        return self._id_gen

    def _get_tracer_provider(
        self, name: str | None = None, extra_attributes: dict[str, str] | None = None
    ) -> TracerProvider:
        p_name = name or self._info_service
        p_prov = self._trace_providers.get(p_name)
        if not p_prov:
            attributes = self._attributes.copy()
            if extra_attributes:
                attributes = {**attributes, **extra_attributes}
            attributes["service.name"] = p_name
            resource = Resource.create(attributes)  # type: ignore[arg-type]
            p_prov = TracerProvider(resource=resource)
            p_prov.id_generator = self.get_id_generator()  # type: ignore[has-type]
            for span_processor in self._span_processors:
                p_prov.add_span_processor(span_processor)
            self._trace_providers[p_name] = p_prov
        return p_prov

    def get_tracer(self, name: str | None = None) -> Tracer:
        return self._get_tracer_provider(name).get_tracer(
            OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION
        )


class DDSpanProcessor:
    """
    This is a DD span processor that creates OTEL spans. It maps the DD spans to OTEL
    spans as closely as possible.
    """

    def __init__(
        self,
        otel_tracer_provider: OtelTracerProvider,
        tracer_attributes: dict[str, str] | None,
        dd_traces_exported: bool,
        omit_root_context_detach: bool,
    ) -> None:
        self._otel = otel_tracer_provider
        self._propagator = tracecontext.TraceContextTextMapPropagator()
        self._otel_spans: dict[int, Tuple[object, Span]] = {}
        self._dd_traces_exported = dd_traces_exported
        self._dd_span_ignore_attr = [
            "runtime-id",
            "_dd.agent_psr",
            "_dd.top_level",
            "_dd.measured",
            "_dd.p.dm",
            "_dd.tracer_kr",
            "_sampling_priority_v1",
            "env",
            "version",
        ]
        self._omit_root_context_detach = omit_root_context_detach
        if tracer_attributes:
            for k in tracer_attributes:
                self._dd_span_ignore_attr.append(k)

    def _translate_data(self, dd_span: Any, otel_span: Span) -> None:
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
        otel_error_attr_dict = {}

        # Map set OTEL attributes based on DD attributes
        otel_span.set_attribute("resource", dd_span.resource)
        for k, v in dd_span_attr.items():
            otel_err_attr = dd_span_err_attr_mapping.get(k)
            if otel_err_attr:
                otel_error_attr_dict[otel_err_attr] = v
            elif k not in self._dd_span_ignore_attr:
                otel_span.set_attribute(k, v)

        # Map exception attributes
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
            # In these cases, we want to use the default OTEL tracer, so
            # we just return None
            return None
        return service

    def on_span_start(self, dd_span: Any) -> None:
        otel_tracer = self._otel.get_tracer(self._get_service_name(dd_span.service))

        # Set up context
        context = None
        if dd_span.parent_id and not dd_span._parent:
            # This span has an external parent, extract that
            parent_trace_id = f"{dd_span.trace_id:x}".zfill(32)
            parent_span_id = f"{dd_span.parent_id:x}".zfill(16)
            trace_ctx = {
                "traceparent": f"00-{parent_trace_id}-{parent_span_id}-01",
            }
            context = self._propagator.extract(carrier=trace_ctx)

        # Setup span kind
        kind = SpanKind.INTERNAL
        if dd_span.span_type:
            # This has to be adjusted if we want to use the CONSUMER/PRODUCER
            # span kinds
            if dd_span.span_type in ["web"]:
                kind = SpanKind.SERVER
            else:
                kind = SpanKind.CLIENT

        # Set up the trace and span ids, and create span
        with self._otel.get_id_generator().with_ids(dd_span.trace_id, dd_span.span_id):
            otel_span = otel_tracer.start_span(
                name=dd_span.name,
                context=context,
                kind=kind,
                start_time=dd_span.start_ns,
            )
            otel_token = context_api.attach(context_api.set_value(_SPAN_KEY, otel_span))

            # Set some attributes, mainly for debugging
            if self._dd_traces_exported:
                otel_span.set_attribute("dd_trace_id", str(dd_span.trace_id))
                otel_span.set_attribute("dd_span_id", str(dd_span.span_id))
            if dd_span.span_type:
                otel_span.set_attribute("dd_type", dd_span.span_type)

            self._otel_spans[dd_span.span_id] = (otel_token, otel_span)

    def on_span_finish(self, dd_span: Any) -> None:
        # Get span and translate DD data to OTEL data
        otel_token, otel_span = self._otel_spans.pop(dd_span.span_id)
        self._translate_data(dd_span, otel_span)

        # Detach context and end span
        t_missing = otel_token.old_value == Token.MISSING  # type: ignore[attr-defined]
        if self._omit_root_context_detach and t_missing:
            logger.debug(
                "Skipping detaching token for "
                f"trace:{otel_span.context.trace_id:x} "  # type: ignore[attr-defined]
                f"span:{otel_span.context.span_id:x}"  # type: ignore[attr-defined]
            )
        else:
            context_api.detach(otel_token)
        otel_span.end(dd_span.start_ns + dd_span.duration_ns)
