from opentelemetry.sdk.trace import RandomIdGenerator
from opentelemetry.trace import (
    NonRecordingSpan,
    Span,
    SpanContext,
    SpanKind,
    Status,
    StatusCode,
    Tracer,
)

from troncos.traces.propagation import get_context_from_dict

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

_id_gen = RandomIdGenerator()


def header_to_str(header: list[str]) -> str | list[str]:
    if len(header) == 1:
        return header[0]
    return header


def create_http_span(
    *,
    tracer: Tracer,
    http_req_method: str,
    http_req_url: str,
    http_req_scheme: str,
    http_req_flavor: str,
    http_req_server_ip: str | None,
    http_req_server_port: int | None,
    http_req_client_ip: str,
    http_req_client_port: int,
    http_req_headers: dict[str, list[str]],
    span_name: str | None,
    ignored_urls: list[str] | None,
) -> Span:
    """
    Create a new span based on an incoming request. Note that http_req_headers
    key have to be lowercase!
    """

    # If we want to ignore this url, create a non-recording span
    if http_req_url in (ignored_urls or []):
        return NonRecordingSpan(
            SpanContext(
                trace_id=_id_gen.generate_trace_id(),
                span_id=_id_gen.generate_span_id(),
                is_remote=False,
                trace_flags=None,
                trace_state=None,
            )
        )

    attr: dict[str, None | str | int | list[str]] = {
        "http.method": http_req_method,
        "http.target": http_req_url,
        "http.scheme": http_req_scheme,
        "http.flavor": http_req_flavor,
        "http.client_ip": http_req_client_ip,
        "net.peer.ip": http_req_client_ip,
        "net.peer.port": http_req_client_port,
    }

    if http_req_server_ip:
        attr["net.host.name"] = http_req_server_ip
    if http_req_server_port:
        attr["net.host.port"] = http_req_server_port

    for k, vs in http_req_headers.items():
        if k == "user-agent":
            attr["http.user_agent"] = header_to_str(vs)
            continue

        if k == "content-length":
            try:
                c_len = int(header_to_str(vs))  # type: ignore
                attr["http.request_content_length"] = c_len
            except Exception:
                attr["http.request_content_length"] = header_to_str(vs)
            continue

        if k == "x-forwarded-for":
            attr["http.client_ip"] = header_to_str(vs)
            continue

        if k == "host":
            attr["net.host.name"] = header_to_str(vs)
            continue

        if k in SAFE_TRACE_HEADERS:
            normalized_key = k.replace("-", "_")
            attr[f"http.request.header.{normalized_key}"] = header_to_str(vs)

    ctx = get_context_from_dict(http_req_headers)
    return tracer.start_span(
        span_name or f"HTTP {http_req_method}",
        attributes=attr,  # type: ignore
        kind=SpanKind.SERVER,
        context=ctx,
    )


def end_http_span(
    *,
    span: Span,
    http_res_status_code: int,
    http_res_headers: dict[str, list[str]],
) -> None:
    """
    Add the response information to the traces span. Note that http_res_headers
    key have to be lowercase!
    """

    attr: dict[str, str | int | list[str]] = {}

    for k, vs in http_res_headers.items():
        if k == "content-length":
            try:
                c_len = int(header_to_str(vs))  # type: ignore
                attr["http.response_content_length"] = c_len
            except Exception:
                attr["http.response_content_length"] = header_to_str(vs)
            continue

        if k in SAFE_TRACE_HEADERS:
            normalized_key = k.replace("-", "_")
            attr[f"http.response.header.{normalized_key}"] = header_to_str(vs)

    attr["http.status_code"] = http_res_status_code

    span.set_attributes(attr)  # type: ignore

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
