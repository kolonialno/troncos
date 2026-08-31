"""Benchmark harness comparing troncos against raw ddtrace and raw OpenTelemetry.

Every arm runs the same span workload and exports it to a local endpoint, so
their timings are comparable: ddtrace ships msgpack to a fake Datadog agent, the
others ship OTLP protobuf to a fake collector.

The flush is part of the measured work on purpose. Troncos translates spans in
OTELWriter.write(), which ddtrace only calls on flush, so a benchmark that
creates spans without flushing reports the bridge as free.

Arm names carry the OTLP transport as a suffix, so `troncos-http` and
`troncos-grpc` are the same implementation over HTTP (4318) and gRPC (4317).
Each `-grpc` arm is compared against the `-grpc` arm of the other
implementation rather than against an HTTP one, so the ratio measures troncos'
translation cost instead of the difference between the two transports. The
`-grpc` arms need the optional `grpc` extra and drop out of the default arm
list when it is missing.

`ddtrace` has no suffix: it speaks the Datadog agent protocol rather than OTLP,
so it has no transport to choose.
"""

import json
import os
import threading
from collections.abc import Callable
from concurrent import futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol

from ddtrace.trace import tracer

from troncos.tracing import Exporter, ExporterType, create_trace_writer

try:
    import grpc

    # The arms need the exporter from the optional 'grpc' extra, and the local
    # collector needs grpcio, which that package depends on. Probing the
    # exporter therefore covers both; probing only grpcio would not, since it
    # arrives as a dev dependency on its own.
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # noqa: F401
        OTLPSpanExporter as _GrpcSpanExporter,
    )
    from opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceResponse,
    )

    GRPC_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the installed extras
    GRPC_AVAILABLE = False

SERVICE_NAME = "perf-service"
RESOURCE_ATTRIBUTES = {"app": "perf", "component": "benchmark"}

OTLP_PATH = "/v1/traces"

CHILDREN_PER_ROOT = 8

HTTP_ARMS = ("opentelemetry-http", "troncos-http")
GRPC_ARMS = ("opentelemetry-grpc", "troncos-grpc")

ALL_ARMS = ("ddtrace", *HTTP_ARMS, *GRPC_ARMS)

_AGENT_RESPONSE = json.dumps({"rate_by_service": {}}).encode()


def selected_arms() -> tuple[str, ...]:
    """Arms to benchmark, from TRONCOS_PERF_ARMS (comma separated)."""
    raw = os.environ.get("TRONCOS_PERF_ARMS")
    if not raw:
        # Without the 'grpc' extra the gRPC arms cannot run. Dropping them from
        # the default list keeps the HTTP gates working and lets the gRPC gate
        # skip itself, instead of failing a run that never asked for gRPC.
        return tuple(
            name for name in ALL_ARMS if GRPC_AVAILABLE or name not in GRPC_ARMS
        )

    names = tuple(name.strip() for name in raw.split(",") if name.strip())
    unknown = [name for name in names if name not in ALL_ARMS]
    if unknown:
        raise ValueError(
            f"unknown arm(s) {unknown} in TRONCOS_PERF_ARMS; "
            f"valid arms are {list(ALL_ARMS)}"
        )
    if not GRPC_AVAILABLE:
        unavailable = [name for name in names if name in GRPC_ARMS]
        if unavailable:
            raise ValueError(
                f"arm(s) {unavailable} need the optional 'grpc' extra installed"
            )
    return names


class _CollectorHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)

        self.server.record_request()  # type: ignore[attr-defined]

        # Only the Datadog agent protocol expects a JSON body back; sending one
        # on the OTLP path makes the OTLP exporter log about it.
        body = b"" if self.path == OTLP_PATH else _AGENT_RESPONSE
        self.send_response(200)
        if body:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    # ddtrace PUTs to /v0.5/traces, the OTLP exporter POSTs.
    do_POST = _handle
    do_PUT = _handle

    def log_message(self, format: str, *args: Any) -> None:
        """Silence per-request logging; it would dominate the benchmark."""


class _CountingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lock = threading.Lock()
        self.request_count = 0

    def record_request(self) -> None:
        with self._lock:
            self.request_count += 1


if GRPC_AVAILABLE:

    class _CountingTraceServicer(trace_service_pb2_grpc.TraceServiceServicer):
        """Counts exports and drops the payload; decoding it would be measured."""

        def __init__(self) -> None:
            self._lock = threading.Lock()
            self.request_count = 0

        def Export(  # the name comes from the OTLP service definition
            self, request: Any, context: Any
        ) -> "ExportTraceServiceResponse":
            with self._lock:
                self.request_count += 1
            return ExportTraceServiceResponse()


class NullCollector:
    """Local endpoint accepting OTLP over HTTP and gRPC, plus Datadog agent exports.

    Deliberately not pytest-httpserver: its unbounded request log and
    per-request bookkeeping show up in the timings.

    Both transports are served at once so an arm can pick the one it needs
    without the fixture having to know which arms were selected.
    """

    def __init__(self) -> None:
        self._server = _CountingHTTPServer(("127.0.0.1", 0), _CollectorHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

        self._grpc_server: Any = None
        self._grpc_servicer: Any = None
        self._grpc_port = 0
        if GRPC_AVAILABLE:
            self._grpc_servicer = _CountingTraceServicer()
            # No compression and no interceptors, so this stays as close to raw
            # transport cost as the gRPC stack allows.
            self._grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
            trace_service_pb2_grpc.add_TraceServiceServicer_to_server(  # type: ignore[no-untyped-call]
                self._grpc_servicer, self._grpc_server
            )
            self._grpc_port = self._grpc_server.add_insecure_port("127.0.0.1:0")

    def start(self) -> "NullCollector":
        self._thread.start()
        if self._grpc_server is not None:
            self._grpc_server.start()
        return self

    def stop(self) -> None:
        if self._grpc_server is not None:
            self._grpc_server.stop(None)
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    @property
    def host(self) -> str:
        return str(self._server.server_address[0])

    @property
    def port(self) -> str:
        return str(self._server.server_address[1])

    @property
    def grpc_port(self) -> str:
        assert self._grpc_port, "the gRPC collector needs the 'grpc' extra"
        return str(self._grpc_port)

    @property
    def request_count(self) -> int:
        """Exports received over either transport.

        Summed rather than kept per transport because the only caller asks
        whether the arm it just timed reached the collector at all.
        """
        count = int(self._server.request_count)
        if self._grpc_servicer is not None:
            count += int(self._grpc_servicer.request_count)
        return count

    @property
    def agent_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def exporter(self) -> Exporter:
        return Exporter(
            host=self.host,
            port=self.port,
            path=OTLP_PATH,
            exporter_type=ExporterType.HTTP,
        )

    def grpc_exporter(self) -> Exporter:
        return Exporter(
            host=self.host,
            port=self.grpc_port,
            path="/",
            exporter_type=ExporterType.GRPC,
        )


class Arm(Protocol):
    """One tracing implementation, driven through a common interface."""

    name: str

    def setup(self, collector: NullCollector) -> None: ...

    def run(self, iterations: int) -> None: ...

    def teardown(self) -> None: ...


class _DDTraceArmBase:
    """Shared ddtrace workload and writer swapping."""

    name = "ddtrace"

    def __init__(self) -> None:
        self._original_writer: Any = None
        self._writers: list[Any] = []

    def _install_writer(self, writer: Any) -> None:
        aggregator = tracer._span_aggregator
        self._original_writer = aggregator.writer
        aggregator.writer = writer
        tracer._recreate()
        # _recreate() swaps in writer.recreate(), so the live writer is not the
        # one built above; both need stopping. On gRPC the orphan holds a
        # channel that keeps reconnecting to a collector later tests have
        # already shut down.
        self._writers = [writer, aggregator.writer]

    def run(self, iterations: int) -> None:
        for iteration in range(iterations):
            with tracer.trace("perf.root", service=SERVICE_NAME) as root:
                root.set_tag("workload", "perf")
                root.set_tag("http.method", "GET")
                root.set_metric("iteration", iteration)
                for index in range(CHILDREN_PER_ROOT):
                    with tracer.trace("perf.child", service=SERVICE_NAME) as child:
                        child.set_tag("child.name", f"child-{index}")
                        child.set_metric("child.index", index)
        tracer.flush()  # type: ignore[no-untyped-call]

    def teardown(self) -> None:
        if self._original_writer is None:
            return
        aggregator = tracer._span_aggregator
        for writer in self._writers:
            try:
                writer.stop()
            except Exception:
                pass
        self._writers = []
        aggregator.writer = self._original_writer
        tracer._recreate()
        self._original_writer = None


class DDTraceArm(_DDTraceArmBase):
    """ddtrace instrumentation exporting through its own NativeWriter."""

    name = "ddtrace"

    def setup(self, collector: NullCollector) -> None:
        from ddtrace.internal.writer.writer import NativeWriter

        # report_metrics=False because troncos' writer reports no statsd
        # metrics either; leaving it on would charge this arm for work the
        # other two never do.
        self._install_writer(
            NativeWriter(intake_url=collector.agent_url, report_metrics=False)
        )


class TroncosHttpArm(_DDTraceArmBase):
    """ddtrace instrumentation translated and exported by troncos over HTTP."""

    name = "troncos-http"

    def setup(self, collector: NullCollector) -> None:
        self._install_writer(
            create_trace_writer(
                enabled=True,
                service_name=SERVICE_NAME,
                exporter=collector.exporter(),
                resource_attributes=RESOURCE_ATTRIBUTES,
            )
        )


class TroncosGrpcArm(_DDTraceArmBase):
    """The same as TroncosHttpArm, exporting over OTLP/gRPC."""

    name = "troncos-grpc"

    def setup(self, collector: NullCollector) -> None:
        self._install_writer(
            create_trace_writer(
                enabled=True,
                service_name=SERVICE_NAME,
                exporter=collector.grpc_exporter(),
                resource_attributes=RESOURCE_ATTRIBUTES,
            )
        )


class _OpenTelemetryArmBase:
    """Shared OpenTelemetry SDK workload, with no ddtrace involved.

    Subclassed per transport; the subclass supplies the span exporter.
    """

    name: str

    def __init__(self) -> None:
        self._provider: Any = None
        self._tracer: Any = None

    def _span_exporter(self, collector: NullCollector) -> Any:
        raise NotImplementedError

    def setup(self, collector: NullCollector) -> None:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        self._provider = TracerProvider(
            resource=Resource.create(
                {"service.name": SERVICE_NAME, **RESOURCE_ATTRIBUTES}
            )
        )
        self._provider.add_span_processor(
            BatchSpanProcessor(self._span_exporter(collector))
        )
        # Not registered as the global provider: that is process-wide state a
        # test should not leave behind.
        self._tracer = self._provider.get_tracer("troncos.perf")

    def run(self, iterations: int) -> None:
        for iteration in range(iterations):
            with self._tracer.start_as_current_span("perf.root") as root:
                root.set_attribute("workload", "perf")
                root.set_attribute("http.method", "GET")
                root.set_attribute("iteration", iteration)
                for index in range(CHILDREN_PER_ROOT):
                    with self._tracer.start_as_current_span("perf.child") as child:
                        child.set_attribute("child.name", f"child-{index}")
                        child.set_attribute("child.index", index)
        self._provider.force_flush()

    def teardown(self) -> None:
        if self._provider is not None:
            self._provider.shutdown()
            self._provider = None
            self._tracer = None


class OpenTelemetryHttpArm(_OpenTelemetryArmBase):
    """The OpenTelemetry SDK over HTTP: the baseline for the troncos HTTP arm."""

    name = "opentelemetry-http"

    def _span_exporter(self, collector: NullCollector) -> Any:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        return OTLPSpanExporter(endpoint=collector.exporter().endpoint)


class OpenTelemetryGrpcArm(_OpenTelemetryArmBase):
    """The OpenTelemetry SDK over gRPC: the baseline for the troncos gRPC arm."""

    name = "opentelemetry-grpc"

    def _span_exporter(self, collector: NullCollector) -> Any:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        return OTLPSpanExporter(endpoint=collector.grpc_exporter().endpoint)


_ARM_FACTORIES: dict[str, Callable[[], Arm]] = {
    "ddtrace": DDTraceArm,
    "opentelemetry-http": OpenTelemetryHttpArm,
    "opentelemetry-grpc": OpenTelemetryGrpcArm,
    "troncos-http": TroncosHttpArm,
    "troncos-grpc": TroncosGrpcArm,
}


def build_arm(name: str) -> Arm:
    try:
        factory = _ARM_FACTORIES[name]
    except KeyError:
        raise ValueError(
            f"unknown arm {name!r}; valid arms are {list(ALL_ARMS)}"
        ) from None
    return factory()


def spans_per_iteration() -> int:
    return CHILDREN_PER_ROOT + 1
