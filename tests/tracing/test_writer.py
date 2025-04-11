from contextlib import contextmanager
from typing import Any, Generator

from ddtrace.trace import tracer, Tracer
from pytest_httpserver import HTTPServer

from troncos.tracing._exporter import Exporter, ExporterType
from troncos.tracing._writer import OTELWriter


@contextmanager
def tracer_test(
    httpserver: HTTPServer,
    service_name: str,
    resource_attributes: dict[str, Any] | None = None,
) -> Generator[Tracer, Any, Any]:
    httpserver.expect_request("/v1/trace").respond_with_data("OK")

    assert tracer.current_span() is None

    tracer._writer = OTELWriter(
        enabled=True,
        service_name=service_name,
        exporter=Exporter(
            host=httpserver.host,
            port=f"{httpserver.port}",
            path="/v1/trace",
            exporter_type=ExporterType.HTTP,
        ),
        resource_attributes=resource_attributes,
    )
    tracer._recreate()  # type: ignore

    yield tracer

    tracer.flush()  # type: ignore[no-untyped-call]


def tracer_assert(httpserver: HTTPServer) -> bytes:
    assert len(httpserver.log), "We should have gotten at least 1 request"

    data: bytes = b""

    for req, res in httpserver.log:
        assert res.status_code == 200, "Response should have been 200"
        data += req.data

    return data


def test_simple_span(httpserver: HTTPServer) -> None:
    with tracer_test(httpserver, "test_service") as tracer:
        with tracer.trace("test", service="test_service"):
            pass

    data = tracer_assert(httpserver)
    assert b"service.name\x12\x0e\n\x0ctest_service" in data


def test_attributes(httpserver: HTTPServer) -> None:
    with tracer_test(
        httpserver,
        "test_attributes",
        resource_attributes={"resource_attribute": "working"},
    ) as tracer:
        with tracer.trace("test", service="test_attributes") as span:
            span.set_tag("span_attribute", "also_working")

    data = tracer_assert(httpserver)
    assert b"service.name\x12\x11\n\x0ftest_attributes" in data
    assert b"resource_attribute\x12\t\n\x07working" in data
    assert b"span_attribute\x12\x0e\n\x0calso_working" in data


def test_exceptions(httpserver: HTTPServer) -> None:
    with tracer_test(httpserver, "test_exception") as tracer:
        try:
            with tracer.trace("test", service="test_exception"):
                raise AssertionError("TestFailure")
        except AssertionError:
            pass

    data = tracer_assert(httpserver)
    assert b"service.name\x12\x10\n\x0etest_exception" in data
    assert b"exception.type\x12\x19\n\x17builtins.AssertionError" in data


def test_headers(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v1/trace").respond_with_data("OK")
    httpserver.expect_request("/v1/trace/custom-header").respond_with_data("OK")

    tracer._writer = OTELWriter(
        enabled=True,
        service_name="test_headers",
        exporter=Exporter(
            host=httpserver.host,
            port=f"{httpserver.port}",
            path="/v1/trace/custom-header",
            exporter_type=ExporterType.HTTP,
            headers={"test-header": "works"},
        ),
        resource_attributes={},
    )
    tracer._recreate()  # type: ignore
    assert tracer.current_span() is None

    with tracer.trace("test"):
        pass

    tracer.flush()  # type: ignore[no-untyped-call]

    relevant_requests = [
        entry for entry in httpserver.log if entry[0].path == "/v1/trace/custom-header"
    ]

    assert len(relevant_requests) == 1, "We should have gotten 1 request"

    req, _ = relevant_requests[0]

    assert req.headers.get("test-header") == "works"


def test_writer_disabled(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/v1/trace").respond_with_data("OK")

    assert tracer.current_span() is None

    tracer._writer = OTELWriter(
        enabled=True,
        service_name="test",
        exporter=Exporter(
            host=httpserver.host,
            port=f"{httpserver.port}",
            path="/v1/trace",
            exporter_type=ExporterType.HTTP,
        ),
        resource_attributes={},
    )
    tracer._recreate()  # type: ignore

    with tracer.trace("test"):
        pass

    tracer.flush()  # type: ignore[no-untyped-call]

    relevant_requests = [
        entry for entry in httpserver.log if entry[0].path == "/v1/trace/custom-header"
    ]

    assert not relevant_requests, "We should have gotten 0 request"
