import pyroscope
from ddtrace import config
from ddtrace.trace import tracer

from ddtrace.internal.hostname import get_hostname


def start_py_spy_profiler(
    *,
    server_address: str,
    tags: dict[str, str] | None = None,
    enable_logging: bool = False,
    auth_token: str = "",
    basic_auth_username: str = "",
    basic_auth_password: str = "",
) -> None:
    """Start the py-spy continuous profiler."""

    # Use the default ddtrace service name.
    app_name = config.service or "unknown-service"

    profiler_tags = {
        "app": app_name,
        "env": config.env,
        "version": config.version,
        "instance": get_hostname(),
        # Use tags from the global tracer.
        **tracer._tags,
    }

    if tags:
        profiler_tags.update(tags)

    pyroscope.configure(
        application_name=app_name,
        tags=profiler_tags,
        server_address=server_address,
        sample_rate=100,
        detect_subprocesses=True,
        oncpu=False,
        gil_only=False,
        enable_logging=enable_logging,
        auth_token=auth_token,
        basic_auth_username=basic_auth_username,
        basic_auth_password=basic_auth_password,
    )
