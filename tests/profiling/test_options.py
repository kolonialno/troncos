import dataclasses
from typing import Any

import pytest

from troncos.profiling import LineNo, ProfilerOptions, configure_profiler

from tests.profiling.conftest import Configured

pyroscope = pytest.importorskip("pyroscope", reason="needs the 'profiling' extra")


def test_every_option_reaches_the_sdk(configured: Configured) -> None:
    """Field names match `pyroscope.configure`, so each one forwards unchanged."""
    options = ProfilerOptions(
        sample_rate=200,
        oncpu=True,
        gil_only=True,
        cpu_enabled=True,
        upload_interval=15,
        report_pid=True,
        report_thread_id=True,
        report_thread_name=True,
        enable_logging=True,
        mem_enabled=True,
        mem_max_nframe=64,
        mem_heap_sample_size=1024,
        mem_enable_mem_domain=False,
    )

    configure_profiler(service_name="svc", options=options)

    call = configured[0]
    for field in dataclasses.fields(options):
        if field.name == "line_no":
            continue  # Translated rather than forwarded, asserted separately.
        assert call[field.name] == getattr(options, field.name), field.name


def test_defaults_keep_pre_v7_behaviour(configured: Configured) -> None:
    configure_profiler(service_name="svc")

    call = configured[0]
    assert call["oncpu"] is False, "the SDK defaults this to True"
    assert call["gil_only"] is False, "the SDK defaults this to True"
    assert call["sample_rate"] == 100
    assert call["upload_interval"] == 10


@pytest.mark.parametrize(
    ("line_no", "variant"),
    [
        (LineNo.LAST_INSTRUCTION, "LastInstruction"),
        (LineNo.FIRST, "First"),
        (LineNo.NO_LINE, "NoLine"),
    ],
)
def test_line_no_becomes_the_sdk_type(
    configured: Configured, line_no: LineNo, variant: str
) -> None:
    """The SDK's LineNo rejects int and str, so the mirror must resolve to it."""
    configure_profiler(service_name="svc", options=ProfilerOptions(line_no=line_no))

    assert configured[0]["line_no"] == getattr(pyroscope.LineNo, variant)


def test_line_no_mirror_covers_the_sdk() -> None:
    """A variant added or renamed upstream should fail here, not at runtime."""
    upstream = {name for name in dir(pyroscope.LineNo) if not name.startswith("_")}

    assert {member.value for member in LineNo} == upstream


@pytest.mark.parametrize(
    "field",
    ["sample_rate", "upload_interval", "mem_max_nframe", "mem_heap_sample_size"],
)
@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_values_are_rejected(field: str, value: int) -> None:
    """Pyroscope takes these silently and then collects nothing."""
    override: dict[str, Any] = {field: value}

    with pytest.raises(ValueError, match=rf"{field} must be greater than 0"):
        ProfilerOptions(**override)


def test_collecting_nothing_is_rejected() -> None:
    """`configure_profiler(enabled=False)` is how profiling gets switched off."""
    with pytest.raises(ValueError, match="collect nothing"):
        ProfilerOptions(cpu_enabled=False, mem_enabled=False)


def test_memory_only_is_not_a_no_op() -> None:
    options = ProfilerOptions(cpu_enabled=False, mem_enabled=True)

    assert options.mem_enabled is True


def test_options_are_frozen() -> None:
    """Shared config that a caller can mutate after the fact is a trap."""
    options = ProfilerOptions()

    with pytest.raises(dataclasses.FrozenInstanceError):
        options.sample_rate = 1  # type: ignore[misc]
