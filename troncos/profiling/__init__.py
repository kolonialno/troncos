import logging
import os
from typing import Callable, Tuple

from troncos._ddlazy import ddlazy

logger = logging.getLogger(__name__)


def init_profiling_basic() -> Callable[[], Tuple[str, dict[str, str]]]:
    """
    Sets up and enables the continuous profiler.

    :return: A callable that returns the profile data and http headers that
             phlare is happy with.
    """

    if not ddlazy.dd_initialized():
        logger.warning(
            "If you are also tracing, YOU SHOULD CALL 'init_tracing_basic' "
            "BEFORE YOU INITIALIZE THE PROFILER"
        )

    # We import ddtrace here because we only want to import
    # it when this function is called, not when it is imported.
    import ddtrace
    from ddtrace.profiling.exporter import pprof  # type: ignore[attr-defined]

    # Define our custom exporter, again ve define this inside the function
    # so ddtrace does not get imported until the function is called.
    class _PprofExporter(pprof.PprofExporter):  # type: ignore[misc]
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

        def export(self, events, start_time_ns, end_time_ns):  # type: ignore[no-untyped-def] # noqa: E501
            self._map_frames(events)  # type: ignore[no-untyped-call]
            pprof_profile, _ = super(_PprofExporter, self).export(
                events, start_time_ns, end_time_ns
            )
            self.pprof = pprof_profile.SerializeToString()

    _endpoint_exporter = _PprofExporter()

    @staticmethod  # type: ignore[misc]
    def _build_default_exporters():  # type: ignore[no-untyped-def]
        return [_endpoint_exporter]

    # Monkey patch default exporter func
    ddtrace.profiling.profiler._ProfilerInstance._build_default_exporters = _build_default_exporters  # type: ignore[assignment] # noqa: 501

    # Set params and enable continuous profiling
    os.environ.setdefault("DD_PROFILING_UPLOAD_INTERVAL", "14")
    import ddtrace.profiling.auto  # noqa: E402

    # Create function to return
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

    return python_pprof
