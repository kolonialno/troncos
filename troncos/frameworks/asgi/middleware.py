import logging
import time
from typing import Any, Awaitable, Callable

from troncos.frameworks.asgi.utils import guarantee_single_callable


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
                self._access.info(
                    "",
                    extra={
                        "http_client_addr": f"{client_ip}:{client_port}",
                        "http_method": method,
                        "http_path": path,
                        "http_version": http_version,
                        "http_status_code": status[0],
                        "duration": f"{time.time()-start_time:.6f}",
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
                    "duration": f"{time.time()-start_time:.6f}",
                },
            )
            raise e
