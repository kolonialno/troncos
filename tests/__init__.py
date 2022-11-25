from troncos.traces import init_tracing_basic

init_tracing_basic(service_name="test")

import ddtrace  # noqa: E402

test_tracer = ddtrace.tracer
