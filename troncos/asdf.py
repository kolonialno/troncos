import logging
import os

from troncos.logs import init_logging_basic
from troncos.traces import init_tracing_basic
import troncos.traces
from troncos.traces.dd_shim import otel_id_generator, dd_span_processor

init_logging_basic(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    formatter=os.environ.get("LOG_FORMATTER", "cli")  # Use "logfmt" or "json" in k8s
)

otel_tracer = init_tracing_basic(
    endpoint="http://localhost:4318/v1/traces",
    exporter_type="http",
    attributes={
        "environment": os.environ.get("ENVIRONMENT", "localdev"),
        "service.name": "myservice",
    }
)

os.environ['DD_INSTRUMENTATION_TELEMETRY_ENABLED'] = "false"
os.environ['DD_TRACE_AGENT_URL'] = "http://localhost:8083"

import ddtrace

otel_tracer.id_generator = otel_id_generator

ddtrace.tracer._span_processors.pop(1)  # Disable DD trace shipping
ddtrace.tracer._span_processors.append(dd_span_processor)  # Enable OTEL tracing

ddtrace.patch_all()

if __name__ == '__main__':
    with ddtrace.tracer.trace("hello") as span:
        span.set_tag("gummier", "bestur")
        try:
            with ddtrace.tracer.trace("hello2"):
                context = ddtrace.tracer.current_trace_context()
                logging.getLogger("ahaha").info("TÖFF")
                raise ValueError("OMG")
        except:
            pass

# Flush
ddtrace.tracer.flush()
troncos.traces._GLOBAL_SPAN_PROCESSORS[0].force_flush(5000)
