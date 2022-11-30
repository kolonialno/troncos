from troncos.traces.decorate import trace_block
from troncos.traces.propagation import activate_context_from_dict

SPAN_ATTR_NAME = "_troncos_gunicorn_trace_span"


def pre_request_trace(  # type: ignore[no-untyped-def]
    worker, req, tracer_provider=None, ignored_uris=None
):
    # Get potential context from headers
    req_headers = {}
    for k, v in req.headers:
        req_headers[str(k).lower()] = str(v)
    activate_context_from_dict(req_headers)

    span = trace_block("gunicorn.request", resource=__name__)
    setattr(worker, SPAN_ATTR_NAME, span)

    # Start span
    span.__enter__()


def post_request_trace(worker, _req, _environ, res):  # type: ignore[no-untyped-def]
    span = getattr(worker, SPAN_ATTR_NAME, None)
    try:
        span.__exit__(None, None, None)  # type: ignore[union-attr]
    except:  # noqa: E722
        worker.log.exception("Exception finishing trace")
