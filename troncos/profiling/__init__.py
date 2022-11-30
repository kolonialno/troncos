import logging
import os
from typing import Callable, Tuple

from troncos._ddlazy import ddlazy

logger = logging.getLogger(__name__)


def init_profiling_basic() -> Callable[[], Tuple[str, dict[str, str]]]:
    if not ddlazy.dd_initialized():
        logger.warning(
            "YOU SHOULD CALL 'init_tracing_basic' BEFORE YOU INITIALIZE THE PROFILER"
        )

    import ddtrace
    from ddtrace.profiling.exporter import pprof  # type: ignore

    class _PprofExporter(pprof.PprofExporter):  # type: ignore
        pprof = ""

        def export(self, events, start_time_ns, end_time_ns):  # type: ignore
            pprof_profile, _ = super(_PprofExporter, self).export(
                events, start_time_ns, end_time_ns
            )
            self.pprof = pprof_profile.SerializeToString()

    _endpoint_exporter = _PprofExporter()

    @staticmethod  # type: ignore
    def _build_default_exporters():  # type: ignore
        return [_endpoint_exporter]

    ddtrace.profiling.profiler._ProfilerInstance._build_default_exporters = _build_default_exporters  # type: ignore # noqa: 501

    # Set this to the phlare scrape interval
    os.environ.setdefault("DD_PROFILING_UPLOAD_INTERVAL", "14")
    import ddtrace.profiling.auto  # noqa: E402

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
