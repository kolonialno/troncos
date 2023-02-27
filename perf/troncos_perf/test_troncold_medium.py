import troncos_perf.test_base as tb
from troncos.traces.decorate import trace_function
from troncos_perf.test_troncold_base import cleanup as base_cleanup

tb.fib_sometimes = trace_function(tb.fib_sometimes)
run = trace_function(tb.run)
cleanup = base_cleanup
