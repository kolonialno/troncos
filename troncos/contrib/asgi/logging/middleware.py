import time
from typing import Any, Awaitable, Callable

try:
    from structlog import get_logger
except ImportError:
    raise RuntimeError(
        "Structlog must be installed to use the asgi logging middleware."
    )


class AsgiLoggingMiddleware:
    """
    ASGI application middleware that logs requests.
    """

    def __init__(
        self,
        app: Any,
        logger_name: str | None = None,
    ) -> None:
        self._app = app
        ln = logger_name or "asgi"
        self._access = get_logger(f"{ln}.access")
        self._error = get_logger(f"{ln}.error")

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
        start_time = time.time()

        async def wrapped_send(message: dict[str, Any]) -> None:
            if "status" in message:
                status[0] = message.get("status", 0)

            await send(message)

            # "more_body" is used if there is still data to send. Log the request
            # when "http.response.body" has no more data left to send in the response.
            if message.get("type") == "http.response.body" and not message.get(
                "more_body", False
            ):
                extra = {
                    "http_client_addr": f"{client_ip}:{client_port}",
                    "http_method": method,
                    "http_path": path,
                    "http_version": http_version,
                    "http_status_code": status[0],
                    "duration": f"{time.time()-start_time:.6f}",
                }
                self._access.info(
                    "",
                    **extra,
                )

        try:
            return await self._app(scope, receive, wrapped_send)
        except Exception as e:
            extra = {
                "http_client_addr": f"{client_ip}:{client_port}",
                "http_method": method,
                "http_path": path,
                "http_version": http_version,
                "http_status_code": 500,
                "duration": f"{time.time()-start_time:.6f}",
            }

            self._error.exception(
                "",
                **extra,
            )
            raise e
