from typing import Optional

from opentelemetry import context as context_api
from troncos.traces.decorate import trace_function
from troncos_perf.test_base import run as run_base

import troncos.traces as tt
from troncos.traces.dd_shim import DDSpanProcessor, OtelTracerProvider
from opentelemetry.sdk.trace.export import SpanProcessor


class TestProcessor(SpanProcessor):
    def __init__(self) -> None:
        self.total_spans = 0

    def on_start(self, span: "Span", parent_context: Optional[context_api.Context] = None) -> None:
        pass

    def on_end(self, span: "ReadableSpan") -> None:
        self.total_spans += 1

    def shutdown(self) -> None:
        print(f"Total spans exported: {self.total_spans}")

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        pass


def new(*args, **kwargs):
    otel_trace_provider = OtelTracerProvider(
        span_processors=[TestProcessor()],
        service="test",
        attributes={},
        env="test",
        version="test",
    )

    return DDSpanProcessor(
        otel_tracer_provider=otel_trace_provider,
        tracer_attributes={},
        dd_traces_exported=False,
        omit_root_context_detach=False,
    )

tt._create_span_processor = new
tt.init_tracing_basic(service_name="test_service")


import ddtrace
tracer = ddtrace.tracer

def cleanup():
    ddtrace.tracer.shutdown()

# Setup runner
run = trace_function(run_base)