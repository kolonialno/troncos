"""Shared fixtures for the profiling tests."""

import inspect
from collections.abc import Iterator
from typing import Any, TypeAlias

import pytest
from ddtrace import config
from ddtrace.trace import tracer

Configured: TypeAlias = list[dict[str, Any]]
"""Calls troncos made to `pyroscope.configure`, in order."""


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> Configured:
    """Capture what troncos would hand the SDK, without starting a profiler.

    Every captured call is bound against the installed `pyroscope.configure`
    first. The v6 wrapper this replaces passed `auth_token` and
    `detect_subprocesses`, both of which the SDK has since dropped; binding
    turns that class of drift into a test failure rather than a TypeError in
    whichever service upgrades first.
    """
    pyroscope = pytest.importorskip("pyroscope", reason="needs the 'profiling' extra")

    signature = inspect.signature(pyroscope.configure)
    calls: Configured = []

    def record(**kwargs: Any) -> None:
        signature.bind(**kwargs)
        calls.append(kwargs)

    monkeypatch.setattr(pyroscope, "configure", record)
    return calls


@pytest.fixture(autouse=True)
def restore_ddtrace_config() -> Iterator[None]:
    """Undo the process-wide ddtrace config that tags are derived from."""
    original = (config.service, config.env, config.version, dict(tracer._tags))

    yield

    config.service, config.env, config.version = original[:3]
    tracer._tags = original[3]
