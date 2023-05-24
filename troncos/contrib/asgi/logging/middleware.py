import time
from typing import Any, Awaitable, Callable, Iterator, Mapping, MutableMapping

from ipware import IpWare

try:
    from structlog import get_logger
except ImportError:
    raise RuntimeError(
        "Structlog must be installed to use the asgi logging middleware."
    )


class Headers(Mapping[str, str]):
    """
    An immutable, case-insensitive multidict.
    """

    def __init__(
        self,
        scope: MutableMapping[str, Any],
    ) -> None:
        self._list: list[tuple[bytes, bytes]] = list(scope["headers"])

    def add_client(self, client: tuple[str, int]) -> None:
        """
        The client IP is not stored in the ASGI headers by default.
        Add the client ip to make sure we use it as a fallback if no
        proxy headers are set.
        """
        self._list.append(
            (
                "REMOTE_ADDR".encode("latin-1"),
                f"{client[0]}:{client[1]}".encode("latin-1"),
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
        for header_key, header_value in self._list:
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

        ipware = IpWare()

        headers = Headers(scope=scope)
        headers.add_client(scope["client"])

        client_ip, _ = ipware.get_client_ip(headers)

        method = scope.get("method")
        path = scope.get("path")
        http_version = scope.get("http_version")
        status = [0]
        start_time = time.perf_counter()

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
                    "http_client_addr": str(client_ip) if client_ip else "NO_IP",
                    "http_method": method,
                    "http_path": path,
                    "http_version": http_version,
                    "http_status_code": status[0],
                    "duration": time.perf_counter() - start_time,
                }
                self._access.info(
                    "",
                    **extra,
                )

        try:
            return await self._app(scope, receive, wrapped_send)
        except Exception as e:
            extra = {
                "http_client_addr": str(client_ip) if client_ip else "NO_IP",
                "http_method": method,
                "http_path": path,
                "http_version": http_version,
                "http_status_code": 500,
                "duration": time.perf_counter() - start_time,
            }

            self._error.exception(
                "",
                **extra,
            )
            raise e
