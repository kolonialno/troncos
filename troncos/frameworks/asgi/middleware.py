import collections
import logging
from typing import Any, Awaitable, Callable

from opentelemetry import trace
from opentelemetry.trace import TracerProvider, use_span

from troncos import OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION
from troncos.frameworks.asgi.utils import guarantee_single_callable
from troncos.traces.http import create_http_span, end_http_span

TRONCOS_SPAN_ATTR = "troncos_span"


class AsgiTracingMiddleware:
    """
    ASGI application middleware that traces the requests.
    """

    def __init__(
        self,
        app: Any,
        tracer_provider: TracerProvider | None = None,
        span_name: str | None = None,
        tracing_ignored_urls: list[str] | None = None,
    ) -> None:
        self._app = guarantee_single_callable(app)
        tp = tracer_provider or trace.get_tracer_provider()
        self._tracer = tp.get_tracer(OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION)
        self._span_name = span_name or "asgi.request"
        self._ignored_urls = tracing_ignored_urls or []

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[Any], Any],
        send: Callable[[dict[str, Any]], Awaitable[Any]],
    ) -> Any:
        if scope["type"] != "http":
            return await self._app(scope, receive, send)

        server_ip, server_port = scope.get("server", ("NO_IP", -1))
        client_ip, client_port = scope.get("client", ("NO_IP", -1))

        scope_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        request_headers = collections.defaultdict(list)
        for req_k, req_v in scope_headers:
            request_headers[req_k.decode("utf-8")].append(req_v.decode("utf-8"))

        span = create_http_span(
            tracer=self._tracer,
            http_req_method=scope["method"],
            http_req_url=scope["path"],
            http_req_scheme=scope["type"],
            http_req_flavor=scope["http_version"],
            http_req_server_ip=server_ip,
            http_req_server_port=server_port,
            http_req_client_ip=client_ip,
            http_req_client_port=client_port,
            http_req_headers=request_headers,
            span_name=self._span_name or scope["method"],
            ignored_urls=self._ignored_urls,
        )
        scope[TRONCOS_SPAN_ATTR] = span

        response = [0, collections.defaultdict(list)]

        async def wrapped_send(message: dict[str, Any]) -> None:
            if "status" in message:
                response[0] = message.get("status")
            if "headers" in message:
                message_headers: list[tuple[bytes, bytes]] = message.get("headers", [])
                for res_k, res_v in message_headers:
                    response[1][res_k.decode("utf-8")].append(  # type: ignore
                        res_v.decode("utf-8")
                    )

            try:
                await send(message)
            finally:
                # "more_body" is used if there is still data to send. End the span if
                # "http.response.body" has no more data left to send in the response.
                if message.get("type") == "http.response.body" and not message.get(
                    "more_body", False
                ):
                    end_http_span(
                        span=span,
                        http_res_status_code=response[0],  # type: ignore
                        http_res_headers=response[1],  # type: ignore
                    )

        with use_span(span, end_on_exit=True):
            res = await self._app(scope, receive, wrapped_send)
            return res


class AsgiLoggingMiddleware:
    """
    ASGI application middleware that logs requests.
    """

    def __init__(
        self,
        app: Any,
        logger_name: str | None = None,
    ) -> None:
        self._app = guarantee_single_callable(app)
        ln = logger_name or "asgi"
        self._access = logging.getLogger(f"{ln}.access")
        self._error = logging.getLogger(f"{ln}.error")

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[Any], Any],
        send: Callable[[dict[str, Any]], Awaitable[Any]],
    ) -> Any:
        if scope["type"] != "http":
            return await self._app(scope, receive, send)

        client_ip, client_port = scope.get("client", ("NO_IP", -1))
        method = scope.get("method")
        path = scope.get("path")
        http_version = scope.get("http_version")
        status = [0]

        async def wrapped_send(message: dict[str, Any]) -> None:
            if "status" in message:
                status[0] = message.get("status", 0)

            await send(message)

            # "more_body" is used if there is still data to send. Log the request
            # when "http.response.body" has no more data left to send in the response.
            if message.get("type") == "http.response.body" and not message.get(
                "more_body", False
            ):
                self._access.info(
                    "",
                    extra={
                        "http_client_addr": f"{client_ip}:{client_port}",
                        "http_method": method,
                        "http_path": path,
                        "http_version": http_version,
                        "http_status_code": status[0],
                    },
                )

        try:
            return await self._app(scope, receive, wrapped_send)
        except Exception as e:
            self._error.error(
                "",
                exc_info=e,
                extra={
                    "http_client_addr": f"{client_ip}:{client_port}",
                    "http_method": method,
                    "http_path": path,
                    "http_version": http_version,
                    "http_status_code": 500,
                },
            )
            raise e
