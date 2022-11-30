import logging
import os
from typing import Callable, Tuple

from troncos._ddlazy import ddlazy

logger = logging.getLogger(__name__)


def init_profiling_basic() -> Callable[[], Tuple[str, dict[str, str]]]:
    """
    Enables continuous profiling
    """

    if not ddlazy.dd_initialized():
        logger.warning(
            "YOU SHOULD CALL 'init_tracing_basic' BEFORE YOU INITIALIZE THE PROFILER"
        )

    import ddtrace
    from ddtrace.profiling.exporter import pprof  # type: ignore[attr-defined]

    # Define exporter
    class _PprofExporter(pprof.PprofExporter):  # type: ignore[misc]
        pprof = ""

        def export(self, events, start_time_ns, end_time_ns):  # type: ignore[no-untyped-def] # noqa: E501
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

    # Set params and enable
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
