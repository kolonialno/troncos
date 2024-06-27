import time
from typing import Any

from asgiref.sync import iscoroutinefunction
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import sync_and_async_middleware
from python_ipware.python_ipware import IpWare

try:
    from structlog import get_logger
except ImportError as exc:
    raise RuntimeError(
        "Structlog must be installed to use the asgi logging middleware."
    ) from exc


@sync_and_async_middleware
def DjangoLoggingMiddleware(get_response):  # type: ignore
    """
    Django middleware that logs requests.
    """

    access = get_logger("troncos.django.access")
    error = get_logger("troncos.django.error")

    ipware = IpWare()

    def extract_request_data(request: HttpRequest) -> tuple[dict[str, Any], float]:
        start_time = time.perf_counter()

        client_ip, _ = ipware.get_client_ip(request.META)

        request_data = {
            "http_method": request.method,
            "http_path": request.path,
            "http_client_addr": str(client_ip) if client_ip else "NO_IP",
        }

        return request_data, start_time

    def log_response(
        *, response: HttpResponse, request_data: dict[str, Any], start_time: float
    ) -> None:
        http_status_code = response.status_code

        logger_method = access.info if http_status_code < 500 else error.error

        logger_method(
            "Django HTTP response",
            http_status_code=http_status_code,
            duration=time.perf_counter() - start_time,
            **request_data,
        )

    if iscoroutinefunction(get_response):

        async def middleware(request: HttpRequest) -> HttpResponse:
            request_data, start_time = extract_request_data(request)

            response = await get_response(request)

            log_response(
                response=response,
                request_data=request_data,
                start_time=start_time,
            )

            return response

    else:

        def middleware(request: HttpRequest) -> HttpResponse:  # type: ignore
            request_data, start_time = extract_request_data(request)

            response = get_response(request)

            log_response(
                response=response,
                request_data=request_data,
                start_time=start_time,
            )

            return response

    return middleware
