import contextlib
import logging
import random
import sys

from opentelemetry import trace
from opentelemetry.sdk.trace import IdGenerator
from opentelemetry.trace import Status, StatusCode

from troncos import OTEL_LIBRARY_NAME

logger = logging.getLogger(__name__)


class _OtelIdGenerator(IdGenerator):
    def __init__(self) -> None:
        self._trace_id = None
        self._span_id = None

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
    def with_ids(self, trace_id, span_id):
        self._trace_id = trace_id
        self._span_id = span_id
        yield
        self._trace_id = None
        self._span_id = None


otel_id_generator = _OtelIdGenerator()


class _DDSpanProcessor:
    _otel_spans = {}
    _otel_tracers = {}

    def _get_tracer(self, dd_span):
        return trace.get_tracer(OTEL_LIBRARY_NAME)

    def _translate_data(self, dd_span, otel_span):
        dd_span_attr = {**dd_span._meta, **dd_span._metrics}
        dd_span_ignore_attr = ['runtime-id', '_dd.agent_psr', '_dd.top_level']
        dd_span_err_attr_mapping = {
            'error.msg': 'exception.message',
            'error.type': 'exception.type',
            'error.stack': 'exception.stacktrace'
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
            otel_span.add_event(
                name="exception", attributes=otel_error_attr_dict
            )
            otel_span.set_status(
                Status(
                    status_code=StatusCode.ERROR,
                    description=f"{otel_error_attr_dict.get('exception.type', None)}: {otel_error_attr_dict.get('exception.message', None)}",
                )
            )

    def on_span_start(self, dd_span):
        otel_tracer = self._get_tracer(dd_span)
        with otel_id_generator.with_ids(dd_span.trace_id, dd_span.span_id):
            otel_ctx = otel_tracer.start_as_current_span(dd_span.name)
            otel_span = otel_ctx.__enter__()

            otel_span.set_attribute("dd_trace_id", str(dd_span.trace_id))
            otel_span.set_attribute("dd_span_id", str(dd_span.span_id))

            self._otel_spans[dd_span.span_id] = (otel_ctx, otel_span)

    def on_span_finish(self, dd_span):
        otel_ctx, otel_span = self._otel_spans.pop(dd_span.span_id)
        self._translate_data(dd_span, otel_span)
        otel_ctx.__exit__(None, None, None)


dd_span_processor = _DDSpanProcessor()
