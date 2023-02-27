import typing
import os

from troncos.traces import init_tracing_basic
from troncos.traces.decorate import trace_function
from troncos_perf.test_base import run as run_base
from troncos_perf.test_otel_base import cleanup as base_clean


os.environ.setdefault("TRONCOS_REUSE_OTEL_PROCESSOR", "true")
init_tracing_basic(service_name="test_service")

# Setup runner
run = trace_function(run_base)
cleanup = base_clean