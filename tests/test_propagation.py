from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from troncos.traces.propagation import (
    add_context_to_dict,
    get_context_from_dict,
    get_propagation_value,
)


def setup_tracing() -> None:
    tp = TracerProvider(resource=Resource(attributes={SERVICE_NAME: "test"}))
    tp.add_span_processor(BatchSpanProcessor(InMemorySpanExporter()))
    trace.set_tracer_provider(tp)


def get_context_test_id() -> int:
    return trace.get_current_span().get_span_context().trace_id


def test_propagation_no_context() -> None:
    d: dict[str, str] = {}
    add_context_to_dict(d)
    assert len(d) == 0


def test_propagation_default() -> None:
    setup_tracing()

    d: dict[str, str] = {}
    with trace.get_tracer(__name__).start_as_current_span("test", context=Context()):
        add_context_to_dict(d)

    assert len(d) == 1
    assert d.get("traceparent", None)


def test_propagation_jaeger() -> None:
    setup_tracing()

    d: dict[str, str] = {}
    with trace.get_tracer(__name__).start_as_current_span("test", context=Context()):
        add_context_to_dict(d, fmt="jaeger")

    assert len(d) == 1
    assert d.get("uber-trace-id", None)


def test_propagation_b3() -> None:
    setup_tracing()

    d: dict[str, str] = {}
    with trace.get_tracer(__name__).start_as_current_span("test", context=Context()):
        add_context_to_dict(d, fmt="b3")

    assert len(d) == 1
    assert d.get("b3", None)


def test_propagation_all() -> None:
    setup_tracing()
    tracer = trace.get_tracer(__name__)

    d_org: dict[str, str] = {}
    with tracer.start_as_current_span("test", context=Context()):
        add_context_to_dict(d_org, fmt="w3c")
    assert len(d_org) == 1

    d1: dict[str, str] = {}
    with tracer.start_as_current_span("test", context=get_context_from_dict(d_org)):
        ctx1 = get_context_test_id()
        add_context_to_dict(d1, fmt="jaeger")
    assert len(d1) == 1

    d2: dict[str, str] = {}
    with tracer.start_as_current_span("test", context=get_context_from_dict(d1)):
        ctx2 = get_context_test_id()
        add_context_to_dict(d2, fmt="b3")
    assert len(d2) == 1

    d3: dict[str, str] = {}
    with tracer.start_as_current_span("test", context=get_context_from_dict(d2)):
        ctx3 = get_context_test_id()
        add_context_to_dict(d3)
    assert len(d3) == 1

    assert ctx1 == ctx2
    assert ctx2 == ctx3


def test_propagation_list_wc3() -> None:
    setup_tracing()
    tracer = trace.get_tracer(__name__)

    d_org: dict[str, str] = {}
    with tracer.start_as_current_span("test", context=Context()):
        add_context_to_dict(d_org)
    assert len(d_org) == 1

    with tracer.start_as_current_span("test", context=get_context_from_dict(d_org)):
        ctx1 = get_context_test_id()

    d_org_2 = {"traceparent": [d_org["traceparent"]]}

    with tracer.start_as_current_span("test", context=get_context_from_dict(d_org_2)):
        ctx2 = get_context_test_id()

    assert ctx1 == ctx2


def test_propagation_list_jaeger() -> None:
    setup_tracing()
    tracer = trace.get_tracer(__name__)

    d_org: dict[str, str] = {}
    with tracer.start_as_current_span("test", context=Context()):
        add_context_to_dict(d_org, fmt="jaeger")
    assert len(d_org) == 1

    with tracer.start_as_current_span("test", context=get_context_from_dict(d_org)):
        ctx1 = get_context_test_id()

    d_org_2 = {"uber-trace-id": [d_org["uber-trace-id"]]}

    with tracer.start_as_current_span("test", context=get_context_from_dict(d_org_2)):
        ctx2 = get_context_test_id()

    assert ctx1 == ctx2


def test_propagation_list_b3() -> None:
    setup_tracing()
    tracer = trace.get_tracer(__name__)

    d_org: dict[str, str] = {}
    with tracer.start_as_current_span("test", context=Context()):
        add_context_to_dict(d_org, fmt="b3")
    assert len(d_org) == 1

    with tracer.start_as_current_span("test", context=get_context_from_dict(d_org)):
        ctx1 = get_context_test_id()

    d_org_2 = {"b3": [d_org["b3"]]}

    with tracer.start_as_current_span("test", context=get_context_from_dict(d_org_2)):
        ctx2 = get_context_test_id()

    assert ctx1 == ctx2


def test_get_propagation_value() -> None:
    setup_tracing()
    tracer = trace.get_tracer(__name__)

    assert get_propagation_value() is None

    with tracer.start_as_current_span("test", context=Context()):
        w3c = get_propagation_value()
        w3c_2 = get_propagation_value(fmt="w3c")
        jaeger = get_propagation_value(fmt="jaeger")
        b3 = get_propagation_value(fmt="b3")

        assert w3c is not None
        assert w3c == w3c_2

        assert jaeger is not None
        assert jaeger != w3c
        assert jaeger != b3

        assert b3 is not None
        assert b3 != w3c
        assert b3 != jaeger
