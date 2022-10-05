import collections
import logging

from opentelemetry.trace import TracerProvider, use_span

from troncos import OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION
from troncos.traces.http import create_http_span, end_http_span

try:
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp
except ImportError:
    raise Exception("This feature is only available if 'starlette' is installed")


class TracingMiddleware(BaseHTTPMiddleware):
    """
    Tracing middleware for starlette
    """

    def __init__(
        self,
        app: ASGIApp,
        tracer_provider: TracerProvider,
        span_name: str | None = None,
    ) -> None:
        super().__init__(app)
        self._span_name = span_name
        self._tracer = tracer_provider.get_tracer(
            OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION
        )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        client_ip, client_port = request.client or ("NO_IP", -1)

        request_headers = collections.defaultdict(list)
        for k, v in request.headers.items():
            request_headers[k.lower()].append(v)

        span = create_http_span(
            tracer=self._tracer,
            http_req_method=request.method,
            http_req_url=str(request.url),
            http_req_scheme=request.url.scheme,
            http_req_flavor="".join(
                str(v) for v in request.scope.get("http_version", [])
            ),
            http_req_client_ip=client_ip,
            http_req_client_port=client_port,
            http_req_headers=request_headers,
            span_name=self._span_name,
        )
        with use_span(span, end_on_exit=True):
            response: Response = await call_next(request)

            response_headers = collections.defaultdict(list)
            for k, v in response.headers.items():
                response_headers[k.lower()].append(v)

            end_http_span(
                span=span,
                http_res_status_code=response.status_code,
                http_res_headers=response_headers,
            )

            return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    This is our custom logs middleware for starlette. We need this so trace_id is
    added to our log records.
    """

    def __init__(
        self,
        app: ASGIApp,
        access_logger: logging.Logger,
        error_logger: logging.Logger,
    ) -> None:
        super().__init__(app)
        self._access = access_logger
        self._error = error_logger

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        req_cli_ip, req_cli_port = request.scope.get("client")  # type: ignore[misc]
        try:
            response: Response = await call_next(request)

            self._access.info(
                "",
                extra={
                    "http_client_addr": f"{req_cli_ip}:{req_cli_port}",
                    "http_method": request.scope.get("method"),
                    "http_path": request.scope.get("path"),
                    "http_version": request.scope.get("http_version"),
                    "http_status_code": response.status_code,
                },
            )
        except Exception as e:
            self._error.error(
                "",
                exc_info=e,
                extra={
                    "http_client_addr": f"{req_cli_ip}:{req_cli_port}",
                    "http_method": request.scope.get("method"),
                    "http_path": request.scope.get("path"),
                    "http_version": request.scope.get("http_version"),
                    "http_status_code": 500,
                },
            )
            raise e
        return response
