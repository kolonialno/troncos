import pyroscope
from ddtrace import config


def start_py_spy_profiler(
    *,
    server_address: str,
    tags: dict[str, str] | None = None,
    enable_logging: bool = False,
) -> None:
    """Start the py-spy continuous profiler."""

    app_name = config.service or "unknown-service"
    profiler_tags = {
        "app": app_name,
        "env": config.env,
        "version": config.version,
        **config.tags,
    }

    if tags:
        profiler_tags.update(tags)

    pyroscope.configure(
        app_name=app_name,
        tags=profiler_tags,
        server_address=server_address,
        sample_rate=100,
        detect_subprocesses=True,
        oncpu=False,
        gil_only=False,
        enable_logging=enable_logging,
    )
