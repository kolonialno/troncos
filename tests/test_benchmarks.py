from typing import Any, Callable

import pytest
from ddtrace.span import Span

from troncos.traces.dd_shim import DDSpanProcessor


@pytest.mark.benchmark(
    min_rounds=5000, warmup=True, warmup_iterations=100, disable_gc=True
)
def test_span_processor(benchmark: Callable[..., Any]) -> None:
    span_processor = DDSpanProcessor(
        "test-service", service_attributes=None, otel_span_processors=[]
    )

    span = Span("test-span", service="test-service")
    span.finish()

    benchmark(span_processor.on_span_finish, span)
