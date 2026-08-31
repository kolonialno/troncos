"""A real in-process OTLP/gRPC collector.

Grafana Alloy's (and the OpenTelemetry Collector's) OTLP receiver listens on
gRPC at 4317 by default, so that is the transport a large share of deployments
actually use. Constructing the gRPC exporter proves the import path still
exists; only a server on the other end proves the payload arrives, which is
what this collector is for.

Deliberately not a mock: the gRPC stack rejects malformed call metadata and
oversized messages on its own, so failures here are the ones a real collector
would produce.
"""

import threading
from collections.abc import Iterator
from concurrent import futures
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import grpc
from opentelemetry.proto.collector.trace.v1 import trace_service_pb2_grpc
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from tests.tracing.otlp import ExportedSpan, spans_from_message


@dataclass(frozen=True)
class GrpcExportRequest:
    """One Export call, with the call metadata gRPC delivered alongside it."""

    message: ExportTraceServiceRequest
    metadata: dict[str, str]

    @property
    def headers(self) -> dict[str, str]:
        """Alias so assertions can read the same as on the HTTP transport."""
        return self.metadata


class _TraceServicer(trace_service_pb2_grpc.TraceServiceServicer):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests: list[GrpcExportRequest] = []

    def Export(  # the name comes from the OTLP service definition
        self, request: ExportTraceServiceRequest, context: Any
    ) -> ExportTraceServiceResponse:
        metadata = dict(context.invocation_metadata())
        with self._lock:
            self.requests.append(GrpcExportRequest(message=request, metadata=metadata))
        return ExportTraceServiceResponse()


class GrpcSpanCollector:
    """OTLP/gRPC endpoint on an ephemeral localhost port."""

    def __init__(self) -> None:
        self._servicer = _TraceServicer()
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        trace_service_pb2_grpc.add_TraceServiceServicer_to_server(  # type: ignore[no-untyped-call]
            self._servicer, self._server
        )
        self._port = self._server.add_insecure_port("127.0.0.1:0")

    def start(self) -> "GrpcSpanCollector":
        self._server.start()
        return self

    def stop(self) -> None:
        # grace=None: no in-flight call should outlive a test, and waiting for
        # one would hide an exporter that never finished.
        self._server.stop(None)

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def port(self) -> str:
        return str(self._port)

    @property
    def requests(self) -> list[GrpcExportRequest]:
        with self._servicer._lock:
            return list(self._servicer.requests)

    def exported_spans(self) -> list[ExportedSpan]:
        spans: list[ExportedSpan] = []
        for request in self.requests:
            spans.extend(spans_from_message(request.message))
        return spans


@contextmanager
def grpc_collector() -> Iterator[GrpcSpanCollector]:
    collector = GrpcSpanCollector().start()
    try:
        yield collector
    finally:
        collector.stop()


__all__ = ["GrpcExportRequest", "GrpcSpanCollector", "grpc_collector"]
