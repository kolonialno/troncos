from typing import Any

from troncos._ddlazy import ddlazy


def activate_context_from_dict(carrier: dict[str, str]) -> Any:
    """
    Extracts trace context from dict and activates it
    """
    context = get_context_from_dict(carrier)
    ddlazy.dd_tracer().context_provider.activate(context)


def get_context_from_dict(carrier: dict[str, str]) -> Any:
    """
    Gets trace context from a dictionary that contains propagation entries.
    """
    return ddlazy.dd_propagator().extract(carrier)


def add_context_to_dict(carrier: dict[str, str]) -> dict[str, str]:
    """
    Adds a trace "parent" entry to a dictionary. This injects all available formats
    """
    context = ddlazy.dd_tracer().current_trace_context()
    if context:
        ddlazy.dd_propagator().inject(context, carrier)
    return carrier


def get_propagation_value() -> str | None:
    """
    Returns a propagation value
    """

    d: dict[str, str] = {}
    add_context_to_dict(d)
    return d.get("b3")
