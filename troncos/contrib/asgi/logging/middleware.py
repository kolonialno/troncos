import time
from typing import Any, Awaitable, Callable, Iterator, Mapping, MutableMapping, cast


from ddtrace.trace import tracer

from python_ipware.python_ipware import IpWare

try:
    from structlog import get_logger
except ImportError as exc:
    raise RuntimeError(
        "Structlog must be installed to use the asgi logging middleware."
    ) from exc

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]

Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class Headers(Mapping[str, str]):
    """
    An immutable, case-insensitive multidict.
    """

    def __init__(
        self,
        scope: MutableMapping[str, Any],
    ) -> None:
        self._list: list[tuple[bytes, bytes]] = list(scope["headers"])

    def add_client(self, client: tuple[str, int] | None) -> None:
        """
        The client IP is not stored in the ASGI headers by default.
        Add the client ip to make sure we use it as a fallback if no
        proxy headers are set.
        """
        host = client[0] if client else "<no-host>"
        port = client[1] if client else 0
        self._list.append(
            (
                "REMOTE_ADDR".encode("latin-1"),
                f"{host}:{port}".encode("latin-1"),
            )
        )

    def keys(self) -> list[str]:  # type: ignore[override]
        return [key.decode("latin-1") for key, value in self._list]

    def values(self) -> list[str]:  # type: ignore[override]
        return [value.decode("latin-1") for key, value in self._list]

    def items(self) -> list[tuple[str, str]]:  # type: ignore[override]
        return [
            (key.decode("latin-1"), value.decode("latin-1"))
            for key, value in self._list
        ]

    def getlist(self, key: str) -> list[str]:
        get_header_key = key.lower().encode("latin-1")
        return [
            item_value.decode("latin-1")
            for item_key, item_value in self._list
            if item_key == get_header_key
        ]

    def __getitem__(self, key: str) -> str:
        get_header_key = key.lower().encode("latin-1")
        for header_key, header_value in self._list:
            if header_key == get_header_key:
                return header_value.decode("latin-1")
        raise KeyError(key)

    def __contains__(self, key: Any) -> bool:
        get_header_key = key.lower().encode("latin-1")
        for header_key, _ in self._list:
            if header_key == get_header_key:
                return True
        return False

    def __iter__(self) -> Iterator[Any]:
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self._list)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Headers):
            return False
        return sorted(self._list) == sorted(other._list)

    def __hash__(self) -> int:
        return hash(tuple(sorted(self._list)))


class AsgiLoggingMiddleware:
    """
    ASGI application middleware that logs requests.
    """

    def __init__(
        self,
        app: ASGIApp,
        logger_name: str | None = None,
    ) -> None:
        self._app = app
        ln = logger_name or "troncos.asgi"
        self._access = get_logger(f"{ln}.access")
        self._error = get_logger(f"{ln}.error")

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Any],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> Any:
        if scope["type"] != "http":
            return await self._app(scope, receive, send)

        ipware = IpWare()

        headers = Headers(scope=scope)
        headers.add_client(scope.get("client"))

        client_ip, _ = ipware.get_client_ip(cast(dict[str, str], headers))

        method = scope.get("method")
        path = scope.get("path")
        http_version = scope.get("http_version")
        status = [0]
        start_time = time.perf_counter()

        async def wrapped_send(message: MutableMapping[str, Any]) -> None:
            if "status" in message:
                status[0] = message.get("status", 0)
            await send(message)

        log_fn = self._access.info
        extra = {}

        # Earlier implementations of this middleware logged calls in the 'wrapped_send'
        # function above, and made it the responsibility of the trace injection log
        # processor to add the trace/span id to the log entry. The problem is that the
        # ASGI TraceMiddleware defined in ddtrace, sometimes ends the span during the
        # 'send(message)' call, and so the trace injection processor would not see the
        # trace context, and therefore not log the trace/span id.
        #
        # To ensure that the trace information is always logged, we simply inject that
        # information in here, and by doing so we do not have to care about the
        # internals of the ASGI TraceMiddleware in ddtrace.
        if dd_context := tracer.current_trace_context():
            extra["trace_id"] = f"{dd_context.trace_id:x}"
            extra["span_id"] = f"{dd_context.span_id:x}"

        try:
            return await self._app(scope, receive, wrapped_send)
        except Exception as e:
            status[0] = 500
            log_fn = self._error.exception
            raise e
        finally:
            log_fn(
                "ASGI HTTP response",
                http_client_addr=str(client_ip) if client_ip else "NO_IP",
                http_method=method,
                http_path=path,
                http_version=http_version,
                http_status_code=status[0],
                duration=time.perf_counter() - start_time,
                **extra,
            )
