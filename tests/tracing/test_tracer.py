from ddtrace.trace import tracer
import os


def test_tracer_enabled_in_tests() -> None:
    assert os.environ["DD_TRACE_ENABLED"] == "True", "Tracer should be enabled in tests"

    assert tracer.enabled, "Tracer should be enabled in tests"
