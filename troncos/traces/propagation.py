from opentelemetry.context import Context
from opentelemetry.propagators import textmap
from opentelemetry.trace.propagation import tracecontext
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def get_context_from_dict(carrier: textmap.CarrierT) -> Context:
    """
    Gets trace context from a dictionary that contains a 'traceparent' entry
    """

    propagator = tracecontext.TraceContextTextMapPropagator()
    return propagator.extract(carrier=carrier)


def add_context_to_dict(carrier: textmap.CarrierT) -> None:
    """
    Adds a trace parent entry to a dictionary
    """

    TraceContextTextMapPropagator().inject(carrier)
