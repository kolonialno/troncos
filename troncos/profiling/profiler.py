from typing import Any

from ddtrace.profiling import exporter
from ddtrace.profiling.exporter import pprof
from ddtrace.profiling.profiler import (
    Profiler as DDProfiler,
    _ProfilerInstance as DDProfilerInstance,
)


class _PprofExporter(pprof.PprofExporter):
    pprof = ""

    @staticmethod
    def _map_frames(events):  # type: ignore[no-untyped-def]
        """
        This function takes the profiling events, and iterates over all the frames,
        formatting the data for phlare.
        """

        for _, e1 in events.items():
            for e2 in e1:
                e2.frames = list(e2.frames)
                for i in range(len(e2.frames)):
                    frame = e2.frames[i]
                    file = frame[0].split("/lib/", 1)[-1]
                    loc = f"{file}:{frame[1]}:{frame[2]}"
                    e2.frames[i] = (frame[0], frame[1], loc, frame[3])

    def export(self, events, start_time_ns, end_time_ns):  # type: ignore[no-untyped-def]
        self._map_frames(events)  # type: ignore[no-untyped-call]
        pprof_profile, _ = super(_PprofExporter, self).export(
            events, start_time_ns, end_time_ns
        )

        self.pprof = pprof_profile.SerializeToString()  # type: ignore[assignment]


class _ProfilerInstance(DDProfilerInstance):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.exporter = _PprofExporter()

        super().__init__(*args, **kwargs)

    def _build_default_exporters(self) -> list[exporter.Exporter]:
        return [self.exporter]


class Profiler(DDProfiler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._profiler = _ProfilerInstance(*args, **kwargs)

    def get_profile(self) -> str:
        return self._profiler.exporter.pprof  # type: ignore
