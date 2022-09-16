import typing

from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer
from opentelemetry.trace.propagation import tracecontext

SAFE_TRACE_HEADERS = frozenset(
    [
        "accept",
        "cache-control",
        "content-security-policy",
        "content-type",
        "expires",
        "location",
        "origin",
        "range",
        "referer",
        "retry-after",
        "server",
        "traceparent",
        "tracestate",
        "uber-trace-id",
        "x-b3-traceid",
        "x-country",
        "x-language",
        "x-xss-protection",
    ]
)


def _convert_uber_trace_id_to_w3c(uber_trace_id: str) -> typing.Optional[str]:
    # uber-trace-id: https://www.jaegertracing.io/docs/1.29/client-libraries/
    # traceparent: https://www.w3.org/TR/trace-context/

    components = uber_trace_id.split(":")
    if len(components) != 4:
        return None

    trace_id, span_id, _, _ = components

    w3c_version = "00"
    # W3C format 00 supports only a single flag: 1 = "sampled"
    w3c_flags = "01"

    w3c_trace_id = trace_id.lower().zfill(32)
    w3c_span_id = span_id.lower().zfill(16)

    return "-".join([w3c_version, w3c_trace_id, w3c_span_id, w3c_flags])


def create_http_span(
    *,
    tracer: Tracer,
    span_name: str,
    http_req_method: str,
    http_req_url: str,
    http_req_scheme: str,
    http_req_flavor: str,
    http_req_client_ip: str,
    http_req_client_port: int,
    http_req_headers: typing.Dict[str, list[str]],
) -> Span:
    """
    Create a new span based on an incoming request. Note that http_req_headers
    key have to be lowercase!
    """

    attr = {
        "http.method": http_req_method,
        "http.url": http_req_url,
        "http.scheme": http_req_scheme,
        "http.flavor": http_req_flavor,
        "net.peer.ip": http_req_client_ip,
        "net.peer.port": http_req_client_port,
    }

    for k, vs in http_req_headers.items():
        if k in SAFE_TRACE_HEADERS:
            normalized_key = k.replace("-", "_")
            attr[f"http.request.header.{normalized_key}"] = (
                vs[0] if len(vs) == 1 else str(vs)
            )

    host_headers = http_req_headers.get("host", ())
    if host_headers:
        attr["http.host"] = host_headers[0]

    user_agent = http_req_headers.get("user-agent", ())
    if user_agent:
        attr["http.user_agent"] = user_agent[0]

    remote_addr = http_req_headers.get("x-forwarded-for", ())
    if remote_addr:
        attr["http.client_ip"] = remote_addr[0]

    # Shim to support the old Jaeger client format from nginx, rather
    # than the W3C standard header.
    if "traceparent" not in http_req_headers:
        try:
            uber_trace_id = http_req_headers["uber-trace-id"][0]
        except (KeyError, IndexError):
            pass
        else:
            traceparent = _convert_uber_trace_id_to_w3c(uber_trace_id)
            if traceparent:
                http_req_headers["traceparent"].append(traceparent)

    propagator = tracecontext.TraceContextTextMapPropagator()
    context = propagator.extract(carrier=http_req_headers)

    return tracer.start_span(
        span_name,
        attributes=attr,  # type: ignore[arg-type]
        kind=SpanKind.SERVER,
        context=context,
    )


def end_http_span(
    *,
    span: Span,
    http_res_status_code: int,
    http_res_headers: typing.Dict[str, list],
) -> None:
    """
    Add the response information to the traces span. Note that http_res_headers
    key have to be lowercase!
    """

    if res_length := http_res_headers.get("content-length"):
        span.set_attribute("http.response_content_length", res_length[0])

    for k, vs in http_res_headers.items():
        if k in SAFE_TRACE_HEADERS:
            normalized_key = k.replace("-", "_")
            span.set_attribute(
                f"http.response.header.{normalized_key}",
                vs[0] if len(vs) == 1 else str(vs),
            )

    span.set_attribute("http.status_code", http_res_status_code)

    if 200 <= http_res_status_code <= 399:
        span.set_status(
            Status(
                status_code=StatusCode.OK,
            )
        )
    else:
        span.set_status(
            Status(
                status_code=StatusCode.ERROR,
                description=str(http_res_status_code),
            )
        )
