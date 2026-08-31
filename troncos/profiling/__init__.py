from typing import Any

from ddtrace import config
from ddtrace.internal.hostname import get_hostname
from ddtrace.trace import tracer

from ._exporter import Exporter
from ._options import LineNo, ProfilerOptions

__all__ = [
    "Exporter",
    "LineNo",
    "ProfilerOptions",
    "configure_profiler",
    "stop_profiler",
]


def _pyroscope() -> Any:
    try:
        import pyroscope
    except ImportError as exc:
        raise ImportError(
            "Profiling needs the 'profiling' extra: pip install 'troncos[profiling]'"
        ) from exc

    return pyroscope


def _resolve_app_name(service_name: str | None) -> str:
    """Name the profiled service, refusing to invent one.

    Profiles are grouped by this name in Pyroscope, so a placeholder would put
    every unnamed service in one pile.
    """
    # Omitting the argument asks for the ddtrace name. Passing a blank one is a
    # mistake, and silently answering it with the fallback would hide it.
    if service_name is None:
        app_name = (config.service or "").strip()
    else:
        app_name = service_name.strip()

    if not app_name:
        raise ValueError(
            "Profiling needs a service name. Pass "
            "configure_profiler(service_name=...), or set the DD_SERVICE "
            "environment variable for ddtrace to pick up."
        )

    return app_name


def _build_tags(*, app_name: str, tags: dict[str, str] | None) -> dict[str, str]:
    profiler_tags = {"app": app_name, "instance": get_hostname()}

    if config.env:
        profiler_tags["env"] = config.env
    if config.version:
        profiler_tags["version"] = config.version

    # Whatever the application already declared on the tracer, so a profile can
    # be filtered by the same labels as its traces.
    profiler_tags.update({k: str(v) for k, v in tracer._tags.items()})

    if tags:
        profiler_tags.update(tags)

    return profiler_tags


def configure_profiler(
    *,
    service_name: str | None = None,
    exporter: Exporter | None = None,
    tags: dict[str, str] | None = None,
    options: ProfilerOptions | None = None,
    enabled: bool = True,
) -> None:
    """Configure the continuous profiler to push profiles to Grafana Pyroscope."""

    if not enabled:
        return

    if exporter is None:
        exporter = Exporter()
    if options is None:
        options = ProfilerOptions()

    app_name = _resolve_app_name(service_name)

    pyroscope = _pyroscope()

    pyroscope.configure(
        application_name=app_name,
        server_address=exporter.endpoint,
        basic_auth_username=exporter.basic_auth_username,
        basic_auth_password=exporter.basic_auth_password,
        tenant_id=exporter.tenant_id,
        http_headers=exporter.headers,
        tags=_build_tags(app_name=app_name, tags=tags),
        sample_rate=options.sample_rate,
        oncpu=options.oncpu,
        gil_only=options.gil_only,
        cpu_enabled=options.cpu_enabled,
        upload_interval=options.upload_interval,
        report_pid=options.report_pid,
        report_thread_id=options.report_thread_id,
        report_thread_name=options.report_thread_name,
        # The SDK's LineNo is a native type that rejects both int and str, so
        # troncos' mirror of it is resolved back by variant name.
        line_no=getattr(pyroscope.LineNo, options.line_no.value),
        enable_logging=options.enable_logging,
        mem_enabled=options.mem_enabled,
        mem_max_nframe=options.mem_max_nframe,
        mem_heap_sample_size=options.mem_heap_sample_size,
        mem_enable_mem_domain=options.mem_enable_mem_domain,
    )


def stop_profiler() -> None:
    """Stop the profiler and flush what it has collected."""

    _pyroscope().shutdown()
