from typing import Any, Callable, Coroutine

from troncos.frameworks.asgi.middleware import TRONCOS_SPAN_ATTR

try:
    from starlette.routing import Mount, Route
    from starlette.types import Receive, Scope, Send
except ImportError:
    raise Exception("This feature is only available if 'starlette' is installed")


def _wrap_handle(
    fn: Callable[[Any, Scope, Receive, Send], Coroutine[Any, Any, None]]
) -> Callable[[Any, Scope, Receive, Send], Coroutine[Any, Any, None]]:
    def inner(
        instance: Any, scope: Scope, receive: Receive, send: Send
    ) -> Coroutine[Any, Any, None]:
        span = scope.get(TRONCOS_SPAN_ATTR)
        if span and hasattr(instance, "path") and "method" in scope:
            scope[TRONCOS_SPAN_ATTR].set_attributes(
                {"http.route": getattr(instance, "path")}
            )
        return fn(instance, scope, receive, send)

    return inner


def init_starlette() -> None:
    """
    Monkeypatch routes and mounts in the starlette api to set resource on requests
    """

    Route.handle = _wrap_handle(Route.handle)  # type: ignore
    Mount.handle = _wrap_handle(Mount.handle)  # type: ignore
