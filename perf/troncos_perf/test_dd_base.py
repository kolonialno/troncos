import ddtrace
from ddtrace.internal.processor import SpanProcessor
from troncos_perf.test_base import run as run_base


def cleanup():
    tracer.flush()
    tracer.shutdown()


class TestProcessor(SpanProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.total_spans = 0

    def on_span_start(self, span):
        pass

    def on_span_finish(self, span):
        self.total_spans += 1

    def shutdown(self, timeout):
        super().shutdown(timeout)
        print(f"Total spans exported: {self.total_spans}")


tracer = ddtrace.tracer
tracer._span_processors.pop(1)
tracer._span_processors.append(TestProcessor())

# Setup runner
run = ddtrace.tracer.wrap("run")(run_base)
