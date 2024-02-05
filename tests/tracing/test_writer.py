from contextlib import contextmanager
from typing import Any, Generator

from ddtrace import Tracer
from pytest_httpserver import HTTPServer

from troncos.tracing._exporter import Exporter, ExporterType
from troncos.tracing._writer import OTELWriter


@contextmanager
def tracer_test(
    httpserver: HTTPServer,
    service_name: str,
    resource_attributes: dict[str, Any] | None = None,
) -> Generator[Tracer, Any, Any]:
    httpserver.expect_oneshot_request("/v1/trace").respond_with_data("OK")

    tracer = Tracer()
    tracer.configure(
        writer=OTELWriter(
            service_name=service_name,
            exporter=Exporter(
                host=httpserver.host,
                port=f"{httpserver.port}",
                path="/v1/trace",
                exporter_type=ExporterType.HTTP,
            ),
            resource_attributes=resource_attributes,
        )
    )

    yield tracer

    tracer.flush()  # type: ignore[no-untyped-call]


def tracer_assert(httpserver: HTTPServer) -> bytes:
    assert len(httpserver.log), "We should have gotten 1 request"
    req, res = httpserver.log[0]
    assert res.status_code == 200, "Response should have been 200"
    return req.data


def test_simple_span(httpserver: HTTPServer) -> None:
    with tracer_test(httpserver, "test_service") as tracer:
        with tracer.trace("test"):
            pass

    data = tracer_assert(httpserver)
    assert b"service.name\x12\x0e\n\x0ctest_service" in data


def test_attributes(httpserver: HTTPServer) -> None:
    with tracer_test(
        httpserver,
        "test_attributes",
        resource_attributes={"resource_attribute": "working"},
    ) as tracer:
        with tracer.trace("test") as span:
            span.set_tag("span_attribute", "also_working")

    data = tracer_assert(httpserver)
    assert b"service.name\x12\x11\n\x0ftest_attributes" in data
    assert b"resource_attribute\x12\t\n\x07working" in data
    assert b"span_attribute\x12\x0e\n\x0calso_working" in data


def test_exceptions(httpserver: HTTPServer) -> None:
    with tracer_test(httpserver, "test_exception") as tracer:
        try:
            with tracer.trace("test"):
                assert False, "TestFailure"
        except AssertionError:
            pass

    data = tracer_assert(httpserver)
    assert b"service.name\x12\x10\n\x0etest_exception" in data
    assert b"exception.type\x12\x19\n\x17builtins.AssertionError" in data


def test_headers(httpserver: HTTPServer) -> None:
    httpserver.expect_oneshot_request("/v1/trace").respond_with_data("OK")

    tracer = Tracer()
    tracer.configure(
        writer=OTELWriter(
            service_name="test_headers",
            exporter=Exporter(
                host=httpserver.host,
                port=f"{httpserver.port}",
                path="/v1/trace",
                exporter_type=ExporterType.HTTP,
                headers={"test-header": "works"},
            ),
            resource_attributes={},
        )
    )

    with tracer.trace("test"):
        pass

    tracer.flush()  # type: ignore[no-untyped-call]

    assert len(httpserver.log), "We should have gotten 1 request"
    req, _ = httpserver.log[0]
    assert req.headers.get("test-header") == "works"
