import troncos_perf.test_base as tb
from troncos_perf.test_otel_base import cleanup as base_cleanup
from troncos_perf.test_otel_base import tracer

tb.fib_sometimes = tracer.start_as_current_span("fib_sometimes")(tb.fib_sometimes)
tb.fib_moretimes = tracer.start_as_current_span("fib_moretimes")(tb.fib_moretimes)
run = tracer.start_as_current_span("run")(tb.run)
cleanup = base_cleanup
