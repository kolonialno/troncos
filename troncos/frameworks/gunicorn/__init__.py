import collections

from opentelemetry import trace
from opentelemetry.trace import Span

from troncos import OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION
from troncos.traces.http import create_http_span, end_http_span
from troncos.traces.propagation import get_propagation_value

SPAN_ATTR_NAME = "_troncos_gunicorn_trace_span"
ACTIVATION_ATTR_NAME = "_troncos_gunicorn_trace_activation"


def _get_span_trace_id(span: Span) -> str | None:
    context = span.get_span_context()
    if not context:
        return None
    return hex(context.trace_id)[2:]


def pre_request_trace(  # type: ignore[no-untyped-def]
    worker, req, tracer_provider=None, ignored_uris=None
):
    """
    Gunicorn pre request hook function for tracing
    """

    # noinspection PyBroadException
    try:
        tp = tracer_provider or trace.get_tracer_provider()
        tracer = tp.get_tracer(OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION)

        peer_ip, peer_port = req.peer_addr

        request_headers = collections.defaultdict(list)
        for k, v in req.headers:
            request_headers[k.lower()].append(v)

        span = create_http_span(
            tracer=tracer,
            http_req_method=req.method,
            http_req_url=req.uri,
            http_req_scheme=req.scheme,
            http_req_flavor=".".join(str(v) for v in req.version),
            http_req_server_ip=None,
            http_req_server_port=None,
            http_req_client_ip=peer_ip,
            http_req_client_port=peer_port,
            http_req_headers=request_headers,
            span_name="gunicorn.request",
            ignored_urls=ignored_uris,
        )

        # This is usually used as a context manager, but we can't do that here
        # because we only have pre- and post- hooks.
        # So instead we save the activation object and call __enter__ and __exit__
        # manually.
        activation = trace.use_span(span, end_on_exit=True)

        # noinspection PyUnresolvedReferences
        activation.__enter__()

        # What follows is a trick to propagate traces correctly to the rest of the
        # application.
        # There appear to be two kinds of opentelemetry instrumentation:
        #   - client instrumentation (such as requests and psycogp2)
        #   - server instrumentation (such as wsgi and django)
        # Client instrumentation works fine without this hack -- it takes the
        # span parent from the "current span", which we've already set.
        # However, server instrumentation wants to find its trace parent in the
        # _headers_. If there's no incoming traceparent header, this gets
        # really confusing.
        # To avoid that, we create a new traceparent header with this span
        # as the parent, and we _mutate_ the headers that we send onwards to
        # the next level of server instrumentation.
        new_traceparent = get_propagation_value()
        did_set_traceparent = False
        for i, (key, _) in enumerate(req.headers):
            if key.lower() == "traceparent":
                req.headers[i] = (key, new_traceparent)
                did_set_traceparent = True
                break
        if not did_set_traceparent:
            req.headers.append(("TRACEPARENT", new_traceparent))

        setattr(worker, SPAN_ATTR_NAME, span)
        setattr(worker, ACTIVATION_ATTR_NAME, activation)

        return _get_span_trace_id(span)
    except Exception:
        worker.log.exception("Exception generating trace")
        return None


def post_request_trace(worker, _req, _environ, res):  # type: ignore[no-untyped-def]
    """
    Gunicorn post request hook function for tracing
    """

    # noinspection PyBroadException
    try:
        span = getattr(worker, SPAN_ATTR_NAME, None)
        activation = getattr(worker, ACTIVATION_ATTR_NAME, None)

        if not (span and activation):
            worker.log.error(
                "Finishing trace; but worker does not have attached trace info"
            )
            return None

        response_headers = collections.defaultdict(list)
        for k, v in res.headers:
            response_headers[k.lower()].append(v)

        end_http_span(
            span=span,
            http_res_status_code=res.status_code,
            http_res_headers=response_headers,
        )

        activation.__exit__(None, None, None)
        return _get_span_trace_id(span)
    except Exception:
        worker.log.exception("Exception finishing trace")
        return None
