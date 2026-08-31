"""End-to-end verification of the troncos trace pipeline.

Black box on purpose: these tests touch only troncos' public API and ddtrace's
public tracer, then assert on the decoded OTLP payload that reached a local
collector. One configure_tracer plus tracer.trace() call exercises every
third-party internal troncos depends on (Tracer._span_aggregator,
Tracer._recreate, the TraceWriter interface, Span.get_tags()/get_metrics()/
._parent, and the OTel SDK internals behind ReadableSpan), so a dependency bump
that moves any of them fails here.

Troncos exports traces only; it has no OTLP metrics pipeline. The "metrics" it
handles are ddtrace's numeric span tags, covered by
test_numeric_metrics_become_numeric_attributes.
"""

import time
from pathlib import Path
from typing import Any

import pytest
from ddtrace.ext import SpanKind as DDSpanKind
from ddtrace.trace import tracer

from troncos.tracing import Exporter, ExporterType
from troncos.tracing.decorators import (
    trace_block,
    trace_class,
    trace_function,
    trace_ignore,
)

from tests.conftest import (
    COLLECTOR_PATH,
    GrpcTraceCollector,
    HttpTraceCollector,
    TraceCollector,
)
from tests.tracing.otlp import span_named


def test_service_name_becomes_resource_service_name(any_traces: TraceCollector) -> None:
    any_traces.configure(service_name="checkout-api")

    with tracer.trace("handle-request", service="checkout-api"):
        pass

    span = span_named(any_traces.collect(), "handle-request")
    assert span.service_name == "checkout-api"


def test_resource_attributes_are_exported(any_traces: TraceCollector) -> None:
    any_traces.configure(
        service_name="checkout-api",
        resource_attributes={
            "app": "checkout",
            "component": "api",
            "role": "web",
            "tenant": "no",
        },
    )

    with tracer.trace("handle-request", service="checkout-api"):
        pass

    span = span_named(any_traces.collect(), "handle-request")
    assert span.resource_attributes["app"] == "checkout"
    assert span.resource_attributes["component"] == "api"
    assert span.resource_attributes["role"] == "web"
    assert span.resource_attributes["tenant"] == "no"


def test_per_span_service_gets_its_own_resource(any_traces: TraceCollector) -> None:
    """A span tagged with a different service must not inherit the default one."""
    any_traces.configure(
        service_name="checkout-api", resource_attributes={"app": "checkout"}
    )

    with tracer.trace("handle-request", service="checkout-api"):
        with tracer.trace("query", service="checkout-db"):
            pass

    spans = any_traces.collect()
    assert span_named(spans, "handle-request").service_name == "checkout-api"

    db_span = span_named(spans, "query")
    assert db_span.service_name == "checkout-db"
    # Non-service resource attributes are still carried over.
    assert db_span.resource_attributes["app"] == "checkout"


def test_resource_attributes_are_not_duplicated_as_span_attributes(
    traces: TraceCollector,
) -> None:
    traces.configure(
        service_name="checkout-api", resource_attributes={"app": "checkout"}
    )

    with tracer.trace("handle-request", service="checkout-api"):
        pass

    span = span_named(traces.collect(), "handle-request")
    assert "app" not in span.attributes
    assert "service.name" not in span.attributes


def test_span_name_and_resource_are_exported(traces: TraceCollector) -> None:
    traces.configure(service_name="checkout-api")

    with tracer.trace("http.request", resource="GET /orders"):
        pass

    span = span_named(traces.collect(), "http.request")
    assert span.name == "http.request"
    # ddtrace's "resource" has no OTLP equivalent, so troncos exports it as an
    # attribute. Losing it would make spans unsearchable in Tempo.
    assert span.attributes["resource"] == "GET /orders"


def test_span_timing_is_exported(traces: TraceCollector) -> None:
    traces.configure(service_name="checkout-api")

    before = time.time_ns()
    with tracer.trace("slow-thing"):
        time.sleep(0.01)
    after = time.time_ns()

    span = span_named(traces.collect(), "slow-thing")
    assert span.start_time_unix_nano >= before
    assert span.end_time_unix_nano <= after
    assert span.end_time_unix_nano > span.start_time_unix_nano
    # Nanosecond units, not microseconds or seconds.
    assert span.end_time_unix_nano - span.start_time_unix_nano >= 10_000_000


def test_parent_child_linkage_is_preserved(any_traces: TraceCollector) -> None:
    any_traces.configure(service_name="checkout-api")

    with tracer.trace("root"):
        with tracer.trace("child"):
            with tracer.trace("grandchild"):
                pass

    spans = any_traces.collect()
    root = span_named(spans, "root")
    child = span_named(spans, "child")
    grandchild = span_named(spans, "grandchild")

    assert not root.has_parent, "root span should have no parent"
    assert child.parent_span_id == root.span_id
    assert grandchild.parent_span_id == child.span_id

    # A single ddtrace trace must stay a single OTLP trace.
    assert root.trace_id == child.trace_id == grandchild.trace_id
    assert len({root.span_id, child.span_id, grandchild.span_id}) == 3


def test_sibling_spans_share_a_parent(traces: TraceCollector) -> None:
    traces.configure(service_name="checkout-api")

    with tracer.trace("root"):
        with tracer.trace("first"):
            pass
        with tracer.trace("second"):
            pass

    spans = traces.collect()
    root = span_named(spans, "root")
    assert span_named(spans, "first").parent_span_id == root.span_id
    assert span_named(spans, "second").parent_span_id == root.span_id


def test_remote_parent_context_is_preserved(traces: TraceCollector) -> None:
    """Covers the branch that builds a parent context for an out-of-process parent."""
    from ddtrace.trace import Context

    traces.configure(service_name="checkout-api")

    remote_trace_id = 0x1234567890ABCDEF1234567890ABCDEF
    remote_span_id = 0x1122334455667788

    tracer.context_provider.activate(
        Context(trace_id=remote_trace_id, span_id=remote_span_id)
    )
    with tracer.trace("continued"):
        pass

    span = span_named(traces.collect(), "continued")
    assert span.has_parent
    assert int.from_bytes(span.parent_span_id, "big") == remote_span_id
    assert int.from_bytes(span.trace_id, "big") == remote_trace_id


@pytest.mark.parametrize(
    ("dd_kind", "expected_otel_kind"),
    [
        (DDSpanKind.SERVER, "SPAN_KIND_SERVER"),
        (DDSpanKind.CLIENT, "SPAN_KIND_CLIENT"),
        (DDSpanKind.PRODUCER, "SPAN_KIND_PRODUCER"),
        (DDSpanKind.CONSUMER, "SPAN_KIND_CONSUMER"),
    ],
)
def test_span_kind_is_mapped(
    traces: TraceCollector, dd_kind: str, expected_otel_kind: str
) -> None:
    traces.configure(service_name="checkout-api")

    with tracer.trace("op") as span:
        span.set_tag("span.kind", dd_kind)

    exported = span_named(traces.collect(), "op")
    assert exported.kind == expected_otel_kind
    # The kind is a first-class OTLP field, so it must not also be an attribute.
    assert "span.kind" not in exported.attributes


def test_untagged_span_defaults_to_internal_kind(traces: TraceCollector) -> None:
    traces.configure(service_name="checkout-api")

    with tracer.trace("op"):
        pass

    assert span_named(traces.collect(), "op").kind == "SPAN_KIND_INTERNAL"


def test_string_tags_become_span_attributes(any_traces: TraceCollector) -> None:
    any_traces.configure(service_name="checkout-api")

    with tracer.trace("op") as span:
        span.set_tag("http.method", "GET")
        span.set_tags({"http.route": "/orders", "customer.segment": "b2b"})

    exported = span_named(any_traces.collect(), "op")
    assert exported.attributes["http.method"] == "GET"
    assert exported.attributes["http.route"] == "/orders"
    assert exported.attributes["customer.segment"] == "b2b"


def test_numeric_metrics_become_numeric_attributes(any_traces: TraceCollector) -> None:
    """The only "metrics" surface troncos has.

    Span.set_metric writes into ddtrace's numeric attribute store, which
    troncos folds into span attributes. Arriving as strings would break
    numeric queries in the backend.

    Uses non-reserved key names: ddtrace stores some well-known semantic
    keys (e.g. "http.status_code") as string tags regardless of which
    setter is called, which would defeat this test.
    """
    any_traces.configure(service_name="checkout-api")

    with tracer.trace("op") as span:
        span.set_metric("queue.depth", 200)
        span.set_metric("db.rows_returned", 42)
        span.set_metric("cache.hit_ratio", 0.75)

    exported = span_named(any_traces.collect(), "op")

    assert exported.attributes["queue.depth"] == 200
    assert isinstance(exported.attributes["queue.depth"], int)

    assert exported.attributes["db.rows_returned"] == 42
    assert isinstance(exported.attributes["db.rows_returned"], int)

    assert exported.attributes["cache.hit_ratio"] == pytest.approx(0.75)
    assert isinstance(exported.attributes["cache.hit_ratio"], float)


def test_tracer_wide_tags_are_exported(traces: TraceCollector) -> None:
    """tracer.set_tags is the README's recommended way to tag every span."""
    traces.configure(service_name="checkout-api")
    tracer.set_tags({"deployment.colour": "green"})
    try:
        with tracer.trace("op"):
            pass

        exported = span_named(traces.collect(), "op")
        assert exported.attributes["deployment.colour"] == "green"
    finally:
        # tracer tags are process-wide; don't leak into other tests.
        tracer._tags.pop("deployment.colour", None)


def test_internal_ddtrace_attributes_are_not_exported(
    any_traces: TraceCollector,
) -> None:
    """Datadog bookkeeping must not leak into OTLP spans."""
    any_traces.configure(service_name="checkout-api")

    with tracer.trace("op"):
        pass

    exported = span_named(any_traces.collect(), "op")
    assert "runtime-id" not in exported.attributes
    assert "_sampling_priority_v1" not in exported.attributes
    assert not [key for key in exported.attributes if key.startswith("_dd")]


def test_exception_is_exported_as_error_status_and_event(
    any_traces: TraceCollector,
) -> None:
    any_traces.configure(service_name="checkout-api")

    with pytest.raises(ValueError):
        with tracer.trace("op"):
            raise ValueError("payment declined")

    exported = span_named(any_traces.collect(), "op")

    assert exported.status_code == "STATUS_CODE_ERROR"

    events = exported.exception_events
    assert len(events) == 1, "expected exactly one 'exception' event"
    attributes = events[0].attributes

    assert attributes["exception.type"] == "builtins.ValueError"
    assert attributes["exception.message"] == "payment declined"
    assert "ValueError: payment declined" in attributes["exception.stacktrace"]

    # The status description should name both, so it is useful on its own.
    assert "builtins.ValueError" in exported.status_message
    assert "payment declined" in exported.status_message


def test_error_details_are_not_left_as_raw_ddtrace_attributes(
    traces: TraceCollector,
) -> None:
    traces.configure(service_name="checkout-api")

    with pytest.raises(ValueError):
        with tracer.trace("op"):
            raise ValueError("payment declined")

    exported = span_named(traces.collect(), "op")
    leaked = [key for key in exported.attributes if key.startswith("error.")]
    assert not leaked, f"ddtrace error tags leaked as span attributes: {leaked}"


def test_successful_span_has_unset_status(traces: TraceCollector) -> None:
    traces.configure(service_name="checkout-api")

    with tracer.trace("op"):
        pass

    exported = span_named(traces.collect(), "op")
    assert exported.status_code == "STATUS_CODE_UNSET"
    assert exported.exception_events == []


def test_trace_block_exports_a_span(traces: TraceCollector) -> None:
    traces.configure(service_name="checkout-api")

    with trace_block("cool.block", resource="data!", attributes={"some": "attribute"}):
        pass

    exported = span_named(traces.collect(), "cool.block")
    assert exported.attributes["some"] == "attribute"
    assert exported.attributes["resource"] == "data!"


def test_trace_function_exports_a_span(traces: TraceCollector) -> None:
    traces.configure(service_name="checkout-api")

    @trace_function(name="decorated.sync", attributes={"kind": "sync"})
    def work() -> int:
        return 7

    assert work() == 7

    exported = span_named(traces.collect(), "decorated.sync")
    assert exported.attributes["kind"] == "sync"


@pytest.mark.asyncio
async def test_trace_function_exports_a_span_for_coroutines(
    traces: TraceCollector,
) -> None:
    traces.configure(service_name="checkout-api")

    @trace_function(name="decorated.async")
    async def work() -> int:
        return 7

    assert await work() == 7

    span_named(traces.collect(), "decorated.async")


def test_trace_class_exports_spans_and_honours_trace_ignore(
    traces: TraceCollector,
) -> None:
    traces.configure(service_name="checkout-api")

    @trace_class
    class Service:
        def traced(self) -> None:
            pass

        @trace_ignore
        def untraced(self) -> None:
            pass

    service = Service()
    service.traced()
    service.untraced()

    spans = traces.collect()
    names = [span.name for span in spans]
    assert any(name.endswith("Service.traced") for name in names), names
    assert not any(name.endswith("Service.untraced") for name in names), names


def test_nested_decorated_calls_keep_their_hierarchy(traces: TraceCollector) -> None:
    traces.configure(service_name="checkout-api")

    @trace_function(name="outer")
    def outer() -> None:
        inner()

    @trace_function(name="inner")
    def inner() -> None:
        pass

    outer()

    spans = traces.collect()
    assert (
        span_named(spans, "inner").parent_span_id == span_named(spans, "outer").span_id
    )


def test_exporter_headers_are_sent_to_the_collector(traces: TraceCollector) -> None:
    traces.configure(
        service_name="checkout-api", headers={"authorization": "Bearer token"}
    )

    with tracer.trace("op"):
        pass

    traces.collect()

    requests = traces.requests()
    assert requests, "expected at least one export request"
    for request in requests:
        assert request.headers.get("authorization") == "Bearer token"


def test_payload_is_sent_as_protobuf(traces: TraceCollector) -> None:
    traces.configure(service_name="checkout-api")

    with tracer.trace("op"):
        pass

    traces.collect()

    requests = traces.requests()
    assert requests
    assert requests[0].headers.get("content-type") == "application/x-protobuf"


def test_disabled_writer_exports_nothing(any_traces: TraceCollector) -> None:
    any_traces.configure(service_name="checkout-api", enabled=False)

    with tracer.trace("op"):
        pass

    assert any_traces.collect() == []
    assert any_traces.requests() == []


def test_disabled_writer_does_not_even_queue_spans(traces: TraceCollector) -> None:
    """A disabled writer must drop spans, not just refuse to flush them.

    flush_queue() is disabled too, so the test above stays green even if spans
    are still queued on the batch processor, where the processor's own timer
    would eventually ship them. Flush the processors directly to prove
    otherwise.
    """
    traces.configure(service_name="checkout-api", enabled=False)

    with tracer.trace("op"):
        pass

    # Test-only introspection: reach the installed writer and flush its
    # processors directly, bypassing the disabled flush_queue().
    writer: Any = tracer._span_aggregator.writer
    for span_processor in writer.otel_span_processors:
        span_processor.force_flush()

    assert traces.requests() == [], "a disabled writer queued spans for export"


def test_many_spans_are_all_exported(any_traces: TraceCollector) -> None:
    any_traces.configure(service_name="checkout-api")

    span_count = 200
    for index in range(span_count):
        with tracer.trace(f"op-{index}"):
            pass

    spans = any_traces.collect()
    exported_names = {span.name for span in spans}
    missing = {f"op-{index}" for index in range(span_count)} - exported_names
    assert not missing, f"{len(missing)} spans were never exported"


def test_default_exporter_targets_the_otlp_http_endpoint() -> None:
    exporter = Exporter(host="collector.example.com")

    assert exporter.endpoint == "http://collector.example.com:4318/v1/traces"
    assert exporter.exporter_type == ExporterType.HTTP


def test_grpc_exporter_can_be_constructed(traces: TraceCollector) -> None:
    """Construction-only smoke test for the optional grpc extra.

    What breaks on an upgrade is the import path or the constructor signature,
    and building the writer exercises both without a collector. Everything
    past construction is covered by the tests that run against a real gRPC
    collector, below.
    """
    pytest.importorskip("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")

    from troncos.tracing import create_trace_writer

    writer = create_trace_writer(
        enabled=True,
        service_name="checkout-api",
        exporter=Exporter(host="127.0.0.1", port="4317"),
    )
    try:
        assert writer.exporter.exporter_type == ExporterType.GRPC
        assert writer.exporter.endpoint == "http://127.0.0.1:4317/"
        assert writer.otel_span_processors
    finally:
        writer.stop()


@pytest.mark.filterwarnings("ignore::ResourceWarning")
@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_debug_processor_writes_spans_to_a_file(
    traces: TraceCollector, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exercises ConsoleSpanExporter and SimpleSpanProcessor, two more OTel symbols.

    The filters are not incidental: troncos opens the debug file in
    get_otel_span_processors and nothing closes it, because
    ConsoleSpanExporter.shutdown() leaves its `out` stream alone. Drop the
    filters once the handle is closed on writer shutdown.
    """
    debug_file = tmp_path / "spans.log"
    monkeypatch.setenv("OTEL_TRACE_DEBUG", "true")
    monkeypatch.setenv("OTEL_TRACE_DEBUG_FILE", str(debug_file))

    traces.configure(service_name="checkout-api")

    with tracer.trace("debugged", service="checkout-api"):
        pass

    # The debug processor exports on span end, so the file is written before
    # the OTLP flush; collect() still confirms the normal path kept working.
    span_named(traces.collect(), "debugged")

    assert debug_file.exists(), "OTEL_TRACE_DEBUG_FILE was never created"
    contents = debug_file.read_text()
    assert "debugged" in contents, contents[:500]
    assert "checkout-api" in contents, contents[:500]


def test_debug_processor_is_off_by_default(traces: TraceCollector) -> None:
    traces.configure(service_name="checkout-api")

    writer: Any = tracer._span_aggregator.writer
    assert len(writer.otel_span_processors) == 1, (
        "expected only the OTLP batch processor when OTEL_TRACE_DEBUG is unset"
    )


def test_collector_path_is_configurable(traces: HttpTraceCollector) -> None:
    custom_path = "/custom/otlp/v1/traces"
    traces._httpserver.expect_request(custom_path).respond_with_data("OK")
    traces.configure(service_name="checkout-api", path=custom_path)

    with tracer.trace("op", service="checkout-api"):
        pass

    spans = traces.collect(path=custom_path)
    assert span_named(spans, "op").service_name == "checkout-api"
    assert traces.requests(path=COLLECTOR_PATH) == []


def test_grpc_export_reaches_a_real_grpc_collector(
    grpc_traces: GrpcTraceCollector,
) -> None:
    """The gRPC path end to end, which construction alone cannot show.

    Alloy's OTLP receiver listens on gRPC at 4317, so this is the transport a
    large share of deployments actually use. Between troncos and the collector
    sit the gRPC exporter's endpoint parsing, its insecure-channel decision and
    the protobuf service definition -- none of which the HTTP tests touch.
    """
    grpc_traces.configure(
        service_name="checkout-api", resource_attributes={"app": "checkout"}
    )

    with tracer.trace("handle-request", service="checkout-api") as span:
        span.set_tag("http.method", "GET")

    exported = span_named(grpc_traces.collect(), "handle-request")
    assert exported.service_name == "checkout-api"
    assert exported.resource_attributes["app"] == "checkout"
    assert exported.attributes["http.method"] == "GET"

    assert grpc_traces.requests(), "nothing reached the gRPC collector"


def test_grpc_and_http_transports_export_the_same_payload(
    traces: HttpTraceCollector, grpc_traces: GrpcTraceCollector
) -> None:
    """Same workload, both transports, identical spans.

    The two exporters share troncos' translation but not their own encoding, so
    a divergence here means one transport is losing or reshaping data. Ids and
    timestamps differ between the two runs by definition and are compared
    structurally instead.
    """

    def workload() -> None:
        with tracer.trace("root", service="checkout-api") as root:
            root.set_tag("http.method", "GET")
            root.set_metric("http.status_code", 200)
            with tracer.trace("child", service="checkout-db"):
                pass

    def comparable(collector: TraceCollector) -> list[tuple[Any, ...]]:
        spans = collector.collect()
        return sorted(
            (
                span.name,
                span.kind,
                span.status_code,
                span.has_parent,
                tuple(sorted(span.attributes.items())),
                tuple(sorted(span.resource_attributes.items())),
            )
            for span in spans
        )

    resource_attributes = {"app": "checkout"}

    traces.configure(
        service_name="checkout-api", resource_attributes=resource_attributes
    )
    workload()
    over_http = comparable(traces)

    grpc_traces.configure(
        service_name="checkout-api", resource_attributes=resource_attributes
    )
    workload()
    over_grpc = comparable(grpc_traces)

    assert over_http, "the HTTP run exported nothing to compare against"
    assert over_grpc == over_http


def test_grpc_exporter_headers_arrive_as_call_metadata(
    grpc_traces: GrpcTraceCollector,
) -> None:
    """Exporter headers become gRPC call metadata.

    This is how a project authenticates to Grafana Cloud or names a tenant, and
    gRPC carries them as metadata rather than HTTP headers, so the HTTP header
    test says nothing about this path.
    """
    grpc_traces.configure(
        service_name="checkout-api",
        headers={"authorization": "Bearer token", "x-scope-orgid": "tenant-7"},
    )

    with tracer.trace("op"):
        pass

    grpc_traces.collect()

    requests = grpc_traces.requests()
    assert requests, "expected at least one export request"
    for request in requests:
        assert request.metadata["authorization"] == "Bearer token"
        assert request.metadata["x-scope-orgid"] == "tenant-7"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "troncos passes exporter headers to the gRPC exporter verbatim, and gRPC "
        "rejects any metadata key containing an uppercase character, failing the "
        "whole export. Header names are case-insensitive over HTTP, so the same "
        "configuration works there. Remove this marker once troncos lowercases "
        "header keys."
    ),
)
def test_grpc_export_survives_a_header_key_that_is_not_lowercase(
    grpc_traces: GrpcTraceCollector,
) -> None:
    """`X-Scope-OrgID` is the spelling Grafana's own docs use.

    Configured against gRPC it currently drops every span, silently as far as
    the application is concerned: gRPC logs to stderr and the exporter reports
    a failed export, but nothing raises.
    """
    grpc_traces.configure(
        service_name="checkout-api", headers={"X-Scope-OrgID": "tenant-7"}
    )

    with tracer.trace("op"):
        pass

    span_named(grpc_traces.collect(), "op")
