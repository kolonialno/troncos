from troncos.profiling import bootstrap, profiler


def start_profiler() -> None:
    if hasattr(bootstrap, "profiler"):
        bootstrap.profiler.stop()

    # Export the profiler so we can introspect it if needed
    bootstrap.profiler = profiler.Profiler()  # type: ignore
    bootstrap.profiler.start()  # type: ignore


start_profiler()
