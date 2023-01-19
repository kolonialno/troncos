from troncos.traces.decorate import trace_block
from troncos.traces.propagation import activate_context_from_dict, get_trace_and_span_id

SPAN_ATTR_NAME = "_troncos_gunicorn_trace_span"


def pre_request_trace(worker, req):  # type: ignore[no-untyped-def]
    # Get potential context from headers
    req_headers = {}
    for k, v in req.headers:
        req_headers[str(k).lower()] = str(v)
    activate_context_from_dict(req_headers)

    span = trace_block("gunicorn.request", resource=__name__, span_type="web")
    setattr(worker, SPAN_ATTR_NAME, span)

    # Start span
    span.__enter__()


def post_request_trace(worker, _req, _environ, res):  # type: ignore[no-untyped-def]
    trace_id, _ = get_trace_and_span_id()
    span = getattr(worker, SPAN_ATTR_NAME, None)
    try:
        span.__exit__(None, None, None)  # type: ignore[union-attr]
    except:  # noqa: E722
        worker.log.exception("Exception finishing trace")
    return None if trace_id is None else f"{trace_id:x}"
