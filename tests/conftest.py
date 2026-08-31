"""Shared fixtures for the tracing tests."""

from collections.abc import Iterator
from typing import Any

import pytest
from ddtrace.trace import tracer

from troncos.tracing import Exporter, ExporterType, configure_tracer

from tests.tracing.otlp import ExportedSpan, exported_spans

COLLECTOR_PATH = "/v1/traces"


@pytest.fixture(autouse=True)
def restore_tracer_writer() -> Iterator[None]:
    """Restore the tracer's writer after every test.

    Without this, a test that points the process-wide tracer at a local
    collector leaves it aimed at a stopped server, and the next flush blocks on
    a dead socket. `_span_aggregator` is the only handle ddtrace offers.
    """
    aggregator = tracer._span_aggregator
    original_writer = aggregator.writer

    yield

    if aggregator.writer is not original_writer:
        try:
            aggregator.writer.stop()
        except Exception:
            pass
        aggregator.writer = original_writer
        tracer._recreate()


def _stop_installed_writer() -> None:
    """Shut the tracer's current writer down, ignoring an already-stopped one.

    Called before a collector goes away. On OTLP/gRPC the exporter holds a
    channel that reconnects on its own, so a writer outliving its server keeps
    retrying and logging into whichever test runs next; on HTTP a dead socket
    just fails quietly. Order matters, so the collector fixtures do this
    themselves rather than leaving it to `restore_tracer_writer`, which
    finalises after them.
    """
    try:
        tracer._span_aggregator.writer.stop()
    except Exception:
        pass


class TraceCollector:
    """Drives troncos' public API and reads back what reached the collector.

    Subclassed per transport. Projects point troncos at an OTLP endpoint over
    either HTTP (4318) or gRPC (4317) — Alloy's receiver commonly offers both —
    and a translation or export bug that only shows on one of them is invisible
    to a suite that exercises the other, so the payload assertions run against
    this interface rather than against one transport's plumbing.
    """

    transport: str

    def __init__(self) -> None:
        self._configured = False

    # --- implemented per transport -------------------------------------

    def exporter(self, *, headers: dict[str, str] | None = None) -> Exporter:
        raise NotImplementedError

    def _received_spans(self) -> list[ExportedSpan]:
        raise NotImplementedError

    def requests(self) -> list[Any]:
        raise NotImplementedError

    # --- shared --------------------------------------------------------

    def _configure(
        self,
        *,
        service_name: str,
        exporter: Exporter,
        resource_attributes: dict[str, Any] | None,
        enabled: bool,
    ) -> None:
        assert tracer.current_span() is None, "a previous test leaked an active span"

        configure_tracer(
            service_name=service_name,
            exporter=exporter,
            resource_attributes=resource_attributes,
            enabled=enabled,
        )
        self._configured = True

    def configure(
        self,
        *,
        service_name: str,
        resource_attributes: dict[str, Any] | None = None,
        enabled: bool = True,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._configure(
            service_name=service_name,
            exporter=self.exporter(headers=headers),
            resource_attributes=resource_attributes,
            enabled=enabled,
        )

    def collect(self) -> list[ExportedSpan]:
        assert self._configured, "call configure() before collect()"
        tracer.flush()  # type: ignore[no-untyped-call]
        return self._received_spans()


class HttpTraceCollector(TraceCollector):
    """OTLP over HTTP/protobuf, the default troncos exports to (port 4318)."""

    transport = "http"

    def __init__(self, httpserver: Any) -> None:
        super().__init__()
        self._httpserver = httpserver

    @property
    def host(self) -> str:
        return str(self._httpserver.host)

    @property
    def port(self) -> str:
        return str(self._httpserver.port)

    def exporter(
        self,
        *,
        path: str = COLLECTOR_PATH,
        headers: dict[str, str] | None = None,
    ) -> Exporter:
        return Exporter(
            host=self.host,
            port=self.port,
            path=path,
            exporter_type=ExporterType.HTTP,
            headers=headers,
        )

    def configure(
        self,
        *,
        service_name: str,
        resource_attributes: dict[str, Any] | None = None,
        enabled: bool = True,
        path: str = COLLECTOR_PATH,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._configure(
            service_name=service_name,
            exporter=self.exporter(path=path, headers=headers),
            resource_attributes=resource_attributes,
            enabled=enabled,
        )

    def _received_spans(self, *, path: str = COLLECTOR_PATH) -> list[ExportedSpan]:
        return exported_spans(self._httpserver, path)

    def collect(self, *, path: str = COLLECTOR_PATH) -> list[ExportedSpan]:
        assert self._configured, "call configure() before collect()"
        tracer.flush()  # type: ignore[no-untyped-call]
        return self._received_spans(path=path)

    def requests(self, *, path: str = COLLECTOR_PATH) -> list[Any]:
        return [request for request, _ in self._httpserver.log if request.path == path]


class GrpcTraceCollector(TraceCollector):
    """OTLP over gRPC, the transport Alloy's receiver listens on at 4317."""

    transport = "grpc"

    def __init__(self, server: Any) -> None:
        super().__init__()
        self._server = server

    @property
    def host(self) -> str:
        return str(self._server.host)

    @property
    def port(self) -> str:
        return str(self._server.port)

    def exporter(self, *, headers: dict[str, str] | None = None) -> Exporter:
        return Exporter(
            host=self.host,
            port=self.port,
            # Both are what troncos derives from port 4317 on its own, spelled
            # out because the test server is on an ephemeral port.
            path="/",
            exporter_type=ExporterType.GRPC,
            headers=headers,
        )

    def _received_spans(self) -> list[ExportedSpan]:
        return list(self._server.exported_spans())

    def requests(self) -> list[Any]:
        return list(self._server.requests)


@pytest.fixture
def traces(httpserver: Any) -> Iterator[HttpTraceCollector]:
    httpserver.expect_request(COLLECTOR_PATH).respond_with_data("OK")
    collector = HttpTraceCollector(httpserver)
    try:
        yield collector
    finally:
        _stop_installed_writer()


@pytest.fixture
def grpc_traces() -> Iterator[GrpcTraceCollector]:
    pytest.importorskip(
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
        reason="needs the 'grpc' extra",
    )
    pytest.importorskip("grpc", reason="needs grpcio to run a local gRPC collector")

    from tests.tracing.otlp_grpc import GrpcSpanCollector

    server = GrpcSpanCollector().start()
    try:
        yield GrpcTraceCollector(server)
    finally:
        _stop_installed_writer()
        server.stop()


@pytest.fixture(params=["http", "grpc"])
def any_traces(request: pytest.FixtureRequest) -> TraceCollector:
    """The same test, run over both OTLP transports.

    Used by the tests that assert on payload content, which must not depend on
    how the payload got there. Transport-specific plumbing (the HTTP path,
    content-type, gRPC call metadata) keeps its own tests.
    """
    collector = request.getfixturevalue(
        {"http": "traces", "grpc": "grpc_traces"}[str(request.param)]
    )
    assert isinstance(collector, TraceCollector)
    return collector
