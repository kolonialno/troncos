from opentelemetry.sdk.resources import SERVICE_NAME
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from troncos.traces import _set_span_processors, init_tracing_provider

_set_span_processors([BatchSpanProcessor(InMemorySpanExporter())])
init_tracing_provider(attributes={SERVICE_NAME: "test"})
