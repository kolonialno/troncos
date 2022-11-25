from typing import Dict

import ddtrace
from ddtrace.context import Context
from ddtrace.propagation.http import HTTPPropagator


def get_context_from_dict(carrier: dict[str, str]) -> Context:
    """
    Gets trace context from a dictionary that contains a 'dd trace' or 'b3' entries.
    """

    return HTTPPropagator().extract(carrier)


def add_context_to_dict(carrier: dict[str, str]) -> dict[str, str]:
    """
    Adds a trace "parent" entry to a dictionary. This injects all available formats
    """

    HTTPPropagator().inject(ddtrace.tracer.current_trace_context(), carrier)
    return carrier


def get_propagation_value() -> str | None:
    """
    Returns the b3 propagation value
    """

    d: Dict[str, str] = {}
    add_context_to_dict(d)
    return d.get("b3")
