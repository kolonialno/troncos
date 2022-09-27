from typing import Dict, Literal

from opentelemetry.context import Context
from opentelemetry.propagators import b3, jaeger
from opentelemetry.propagators.textmap import (
    CarrierT,
    DefaultGetter,
    Getter,
    TextMapPropagator,
)
from opentelemetry.trace.propagation import tracecontext


def get_context_from_dict(carrier: CarrierT) -> Context:
    """
    Gets trace context from a dictionary that contains a 'traceparent', 'uber-trace-id'
    or 'b3' entries.
    """

    getter: Getter[CarrierT] = DefaultGetter()  # type: ignore[assignment]
    propagator: TextMapPropagator

    if getter.get(carrier, "traceparent"):  # w3c
        propagator = tracecontext.TraceContextTextMapPropagator()
    elif getter.get(carrier, "uber-trace-id"):  # jaeger
        propagator = jaeger.JaegerPropagator()
    else:  # b3
        # The reason this is default is that multiple headers can be used for
        # propagation.
        propagator = b3.B3MultiFormat()

    return propagator.extract(carrier=carrier)


def add_context_to_dict(
    carrier: CarrierT, fmt: Literal["w3c", "jaeger", "b3"] = "w3c"
) -> CarrierT:
    """
    Adds a trace "parent" entry to a dictionary. This can be in jaeger, b3 or the
    default w3c format.
    """

    propagator: TextMapPropagator
    if fmt == "jaeger":
        propagator = jaeger.JaegerPropagator()
    elif fmt == "b3":
        propagator = b3.B3SingleFormat()
    else:
        propagator = tracecontext.TraceContextTextMapPropagator()

    propagator.inject(carrier)

    return carrier


def get_propagation_value(fmt: Literal["w3c", "jaeger", "b3"] = "w3c") -> str | None:
    """
    Returns the value of the context propagation header
    """

    d: Dict[str, str] = {}
    add_context_to_dict(d, fmt=fmt)

    if fmt == "jaeger":
        return d.get("uber-trace-id")
    elif fmt == "b3":
        return d.get("b3")
    else:
        return d.get("traceparent")
