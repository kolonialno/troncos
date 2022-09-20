import opentelemetry.propagators.b3
from opentelemetry.context import Context
from opentelemetry.propagators import textmap
from opentelemetry.trace.propagation import tracecontext
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def get_context_from_dict(carrier: textmap.CarrierT) -> Context:
    """
    Gets trace context from a dictionary that contains a 'traceparent' or 'b3' entries
    """

    if carrier.get("traceparent"):
        # Use default propagator
        propagator = tracecontext.TraceContextTextMapPropagator()
    else:
        # Try using b3 propagator
        propagator = opentelemetry.propagators.b3.B3MultiFormat()
    return propagator.extract(carrier=carrier)


def add_context_to_dict(carrier: textmap.CarrierT) -> None:
    """
    Adds a trace parent entry to a dictionary
    """

    TraceContextTextMapPropagator().inject(carrier)
