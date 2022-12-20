import logging
import os
from typing import Tuple

try:
    import ddtrace
    from ddtrace.profiling.exporter import pprof  # type: ignore
except ImportError:
    raise Exception("This feature is only available if 'ddtrace' is installed")


class _PprofExporter(pprof.PprofExporter):  # type: ignore
    pprof = ""

    @staticmethod
    def _map_frames(events):  # type: ignore
        for _, e1 in events.items():
            for e2 in e1:
                new_frames = []
                for frame in e2.frames:
                    file = frame[0].split("/lib/", 1)[-1]
                    loc = f"{file}:{frame[1]}:{frame[2]}"
                    new_frames.append((frame[0], frame[1], loc, frame[3]))
                e2.frames = new_frames

    def export(self, events, start_time_ns, end_time_ns):  # type: ignore
        self._map_frames(events)  # type: ignore
        pprof_profile, _ = super(_PprofExporter, self).export(
            events, start_time_ns, end_time_ns
        )
        self.pprof = pprof_profile.SerializeToString()


_endpoint_exporter = _PprofExporter()


@staticmethod  # type: ignore
def _build_default_exporters():  # type: ignore
    return [_endpoint_exporter]


def python_pprof() -> Tuple[str, dict[str, str]]:
    """
    Returns the pprof content as a string and the headers that should be returned by
    a http endpoint
    """

    return _endpoint_exporter.pprof, {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": 'attachment; filename="python.pprof"',
        "X-Content-Type-Options": "nosniff",
    }


ddtrace.profiling.profiler._ProfilerInstance._build_default_exporters = _build_default_exporters  # type: ignore # noqa: 501

# Set this to the phlare scrape interval
os.environ["DD_PROFILING_UPLOAD_INTERVAL"] = os.environ.get(
    "DD_PROFILING_UPLOAD_INTERVAL", "14"
)
_interval = os.environ["DD_PROFILING_UPLOAD_INTERVAL"]

logging.getLogger(__name__).info(
    f"Starting continuous profiling with interval of {_interval} seconds"
)
import ddtrace.profiling.auto  # noqa: E402
