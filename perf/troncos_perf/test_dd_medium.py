import troncos_perf.test_base as tb
from troncos_perf.test_dd_base import cleanup as base_cleanup
from troncos_perf.test_dd_base import tracer

tb.fib_sometimes = tracer.wrap("fib_sometimes")(tb.fib_sometimes)
run = tracer.wrap("run")(tb.run)
cleanup = base_cleanup
