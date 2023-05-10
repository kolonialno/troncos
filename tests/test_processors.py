from typing import Any, _AnyMeta  # type: ignore[attr-defined]

import pytest
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.trace import SpanKind, StatusCode

from troncos.traces import _patch_dd_tracer
from troncos.traces.dd_shim import DDSpanProcessor
from troncos.traces.decorate import trace_block


class Event:
    def __init__(self, *, name: str, attributes: dict[str, Any]) -> None:
        self.name = name
        self.attributes = attributes


class Span:
    def __init__(
        self,
        *,
        name: str,
        attributes: dict[str, Any],
        kind: SpanKind = SpanKind.INTERNAL,
        status_code: StatusCode = StatusCode.UNSET,
        events: list[Event] = [],
        has_parent: bool = False,
    ) -> None:
        self.name = name
        self.attributes = attributes
        self.kind = kind
        self.status_code = status_code
        self.events = events
        self.has_parent = has_parent


class TSpanProcessor(SpanProcessor):
    def __init__(self) -> None:
        self.__exit__(None, None, None)

    def on_end(self, span: "ReadableSpan") -> None:
        self.spans.append(span)

    def __enter__(self) -> "TSpanProcessor":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.spans: list[ReadableSpan] = []

    @staticmethod
    def _assert_attrs(a: dict[str, Any], b: dict[str, Any]) -> None:
        assert len(a) == len(b), f"Number of attributes differ: {a} != {b}"
        for k, v in a.items():
            if isinstance(v, _AnyMeta):
                assert b.get(k, None), f"Missing attribute '{k}'"
            else:
                assert v == b.get(k, None), f"Attribute '{k}' does not match"

    def assert_spans(self, *spans: Span) -> None:
        assert len(self.spans) == len(spans), "Number of spans does not match"
        for si, a_span in enumerate(spans):
            b_span = self.spans[si]
            assert a_span.name == b_span.name, "Span name does not match"
            assert a_span.kind == b_span.kind, "Span kind does not match"
            assert (
                a_span.status_code == b_span.status.status_code
            ), "Span status does not match"

            self._assert_attrs(
                a_span.attributes, b_span.attributes  # type: ignore[arg-type]
            )

            if a_span.has_parent:
                assert b_span.parent, "Span should have a parent"
            else:
                assert not b_span.parent, "Span should not have a parent"

            for ei, a_event in enumerate(a_span.events):
                b_event = b_span.events[ei]
                assert a_event.name == b_event.name, "Event names do not match"
                self._assert_attrs(
                    a_event.attributes, b_event.attributes  # type: ignore[arg-type]
                )
                print()


def test_processors() -> None:
    test_span_processor = TSpanProcessor()

    dd_span_processor = DDSpanProcessor(
        "test-service",
        service_attributes=None,
        otel_span_processors=[test_span_processor],
        dd_traces_exported=True,
    )
    _patch_dd_tracer(dd_span_processor=dd_span_processor, enable_dd=False)

    with test_span_processor as t:
        with trace_block("test-block"):
            with pytest.raises(AssertionError):
                with trace_block("test-block-fail", attributes={"extra": "attr"}):
                    with trace_block(
                        "test-client",
                        resource="/test",
                        service="test-api",
                        span_type="client",
                    ):
                        pass
                    assert False, "Failure"

        t.assert_spans(
            Span(
                name="test-client",
                attributes={
                    "resource": "/test",
                    "dd_type": "client",
                    "dd_trace_id": Any,
                    "dd_span_id": Any,
                },
                has_parent=True,
            ),
            Span(
                name="test-block-fail",
                attributes={
                    "resource": "test-block-fail",
                    "dd_trace_id": Any,
                    "dd_span_id": Any,
                    "error.message": "Failure\nassert False",
                    "extra": "attr",
                },
                status_code=StatusCode.ERROR,
                events=[
                    Event(
                        name="exception",
                        attributes={
                            "exception.type": "builtins.AssertionError",
                            "exception.stacktrace": Any,
                        },
                    )
                ],
                has_parent=True,
            ),
            Span(
                name="test-block",
                attributes={
                    "resource": "test-block",
                    "process_id": Any,
                    "dd_trace_id": Any,
                    "dd_span_id": Any,
                },
            ),
        )
