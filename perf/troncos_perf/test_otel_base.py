from typing import Optional

from opentelemetry import trace, context as context_api
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import SpanProcessor
from troncos_perf.test_base import run as run_base


def cleanup():
    provider.force_flush()
    provider.shutdown()


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


# Initialize tracer
resource = Resource(attributes={
    SERVICE_NAME: "test_service"
})
provider = TracerProvider(resource=resource)
provider.add_span_processor(TestProcessor())
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

# Setup runner
run = tracer.start_as_current_span("run")(run_base)
