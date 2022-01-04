from typing import Tuple

from ddtrace.ext import SpanTypes, http
from ddtrace.propagation.http import HTTPPropagator

from troncos.base.tracing import PrintServiceTracer

try:
    from starlette.middleware.base import BaseHTTPMiddleware, DispatchFunction
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.routing import Match
    from starlette.types import ASGIApp
except ImportError:
    raise Exception("This feature is only available if Starlette is installed")


class DDTraceMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware used for distributed tracing.
    """

    def __init__(self, app: ASGIApp, middleware_tracer: PrintServiceTracer) -> None:
        super().__init__(app)
        self.tracer = middleware_tracer

    # noqa: E501
    async def dispatch(self, request: Request, call_next: DispatchFunction) -> Response:  # type: ignore
        """
        Activate span context from HTTP headers if found, start a new request span.
        """
        propagator = HTTPPropagator()
        context = propagator.extract(request.headers)  # type: ignore[arg-type]

        # Only need to active the new context if something was propagated
        if context.trace_id:
            self.tracer.context_provider.activate(context)

        request_span = self.tracer.trace("starlette.request", span_type=SpanTypes.WEB)  # type: ignore[arg-type]

        try:
            response = await call_next(request)  # type: ignore[call-arg]

            if 500 <= response.status_code < 600:
                request_span.error = 1

            path_template, _ = self.get_path_template(request)
            request_span.resource = f"{request.method} {path_template}"
            request_span.set_tag("http.method", request.method)
            request_span.set_tag("http.status_code", response.status_code)
            request_span.set_tag(http.URL, request.url.path)

            # Finish the span to track execution time
            request_span.finish()
        except Exception:
            request_span.set_traceback()
            raise

        return response

    @staticmethod
    def get_path_template(request: Request) -> Tuple[str, bool]:
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                return route.path, True

        return request.url.path, False
