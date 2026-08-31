import enum
from dataclasses import dataclass


class LineNo(enum.Enum):
    """Which line of a sampled frame the profiler attributes a sample to.

    Values are the names of the SDK's own variants. The SDK's `LineNo` is a
    native type that only accepts itself, so troncos mirrors it here rather
    than importing it, which keeps `troncos.profiling` importable without the
    'profiling' extra.
    """

    LAST_INSTRUCTION = "LastInstruction"
    FIRST = "First"
    NO_LINE = "NoLine"


def _require_positive(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(
            f"{name} must be greater than 0, got {value!r}. Pyroscope accepts "
            f"the value and then collects nothing, so troncos rejects it here."
        )


@dataclass(frozen=True)
class ProfilerOptions:
    """How the profiler samples, on top of the endpoint an `Exporter` names.

    Field names match the arguments of `pyroscope.configure`, so Grafana's
    [SDK documentation](https://grafana.com/docs/pyroscope/latest/configure-client/language-sdks/python/)
    describes them directly.

    Two defaults differ from the SDK's own. `oncpu` and `gil_only` are both
    `False` here and `True` there, which widens profiling from on-CPU time in
    the GIL-holding thread to wall clock time across every thread, so that time
    spent waiting is visible.
    """

    sample_rate: int = 100
    """Samples per second."""

    oncpu: bool = False
    """Measure on-CPU time only, rather than wall clock time."""

    gil_only: bool = False
    """Sample only the thread holding the GIL."""

    cpu_enabled: bool = True
    """Collect CPU profiles."""

    upload_interval: int = 10
    """Seconds between uploads."""

    report_pid: bool = False
    """Tag samples with the process id."""

    report_thread_id: bool = False
    """Tag samples with the thread id."""

    report_thread_name: bool = False
    """Tag samples with the thread name."""

    line_no: LineNo = LineNo.LAST_INSTRUCTION
    """Which line of a frame a sample is attributed to."""

    enable_logging: bool = False
    """Let the SDK log its own activity, for debugging a silent profiler."""

    mem_enabled: bool = False
    """Collect heap profiles. Unavailable on free-threaded interpreters."""

    mem_max_nframe: int = 128
    """Frames to keep per allocation."""

    mem_heap_sample_size: int = 512 * 1024
    """Bytes allocated between heap samples."""

    mem_enable_mem_domain: bool = True
    """Track allocator domains, which needs Python 3.12 or newer."""

    def __post_init__(self) -> None:
        _require_positive("sample_rate", self.sample_rate)
        _require_positive("upload_interval", self.upload_interval)
        _require_positive("mem_max_nframe", self.mem_max_nframe)
        _require_positive("mem_heap_sample_size", self.mem_heap_sample_size)

        if not self.cpu_enabled and not self.mem_enabled:
            raise ValueError(
                "cpu_enabled and mem_enabled are both False, so the profiler "
                "would start and collect nothing. Pass enabled=False to "
                "configure_profiler to turn profiling off."
            )
