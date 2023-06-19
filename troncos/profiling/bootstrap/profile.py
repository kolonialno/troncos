from troncos.profiling import bootstrap


def get_profile() -> tuple[bytes, dict[str, str]]:
    """Get the latest profile."""

    headers = {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": 'attachment; filename="python.pprof"',
        "X-Content-Type-Options": "nosniff",
    }

    if hasattr(bootstrap, "profiler"):
        return bootstrap.profiler.get_profile(), headers

    return b"", headers
