from typing import Any

from troncos._lazydd import dd_tracer, dd_propagator


def get_context_from_dict(carrier: dict[str, str]) -> Any:
    """
    Gets trace context from a dictionary that contains a 'dd trace' or 'b3' entries.
    """
    return dd_propagator().extract(carrier)


def add_context_to_dict(carrier: dict[str, str]) -> dict[str, str]:
    """
    Adds a trace "parent" entry to a dictionary. This injects all available formats
    """
    context = dd_tracer().current_trace_context()
    if context:
        dd_propagator().inject(context, carrier)
    return carrier


def get_propagation_value() -> str | None:
    """
    Returns the b3 propagation value
    """

    d: dict[str, str] = {}
    add_context_to_dict(d)
    return d.get("b3")
