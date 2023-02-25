import logging

from starlette.middleware import Middleware

from troncos.frameworks.asgi.middleware import AsgiLoggingMiddleware
from troncos.logs.filters import HttpPathFilter

try:
    from starlette.applications import Starlette
except ImportError:
    raise Exception("This feature is only available if 'starlette' is installed")


class _UvicornErrorFilter(logging.Filter):
    """
    This filter can be added to uvicorn logging so exceptions that happen when serving
    requests, are not logged 2 times. See 'init_uvicorn_logging' below for context.
    """

    def __init__(self, name: str = "UvicornErrorFilter") -> None:
        super().__init__(name)

    def filter(self, record: logging.LogRecord) -> bool:
        return record.msg != "Exception in ASGI application\n"


def init_uvicorn_logging(
    *,
    app: Starlette,
    logger_name: str | None = None,
    log_access_ignored_paths: list[str] | None = None,
) -> None:
    """
    This function sets up logging for uvicorn + starlette. There is a lot of meddling
    around with loggers in this function, so I will try my best to explain what I am
    trying to do here.

    First off, we cannot use the 'uvicorn.access' logger at all. The reason for that is
    because it logs messages after all middleware has been executed. Meaning that our
    tracing span is gone (like tears in the rain) when that logger logs. So we just
    disable 'uvicorn.access' and add new LoggingMiddleWare (see implementation in
    asgi/middleware.py) that handles logging, because that can see our tracing spans.
    The new loggers it uses are called 'velodrome.access' and 'velodrome.error'

    Now using our own middleware for logging poses another problem. Errors are logged
    twice! So, to mitigate that, we filter all exceptions that would be logged my our
    middleware out of the 'uvicorn.error' logger using _UvicornErrorFilter (above). We
    do not want to disable that logger completely, because it also logs other important
    messages.

    We also make sure that all loggers (except ROOT) just propagate records and none of
    them has a handler. Meaning all logs are funneled through ROOT. That is convenient,
    because it is a single place to add a "global" handler.

    Lastly we set the TraceIdFilter on the ROOT handler (yes, handler, not logger,
    because filters on loggers are not executed when record is propagated from a 'child'
    logger). We do this to add trace id to the records whenever they are available.

    It could help to take a look at this flowchart:
    https://docs.python.org/3/howto/logging.html#logging-flow

    So we end up with this situation in the end:
    [ root                 ] logging.RootLogger LEVEL: 20 PROPAGATE: True
      └ HANDLER logging.StreamHandler  LEVEL: 20
        └ FILTER troncos.logs.filters.TraceIdFilter
        └ FORMATTER troncos.logs.formatters.PrettyFormatter
    [ uvicorn.access       ] logging.Logger LEVEL: 20 PROPAGATE: False
    [ uvicorn.error        ] logging.Logger LEVEL: 20 PROPAGATE: True
      └ FILTER troncos.frameworks.starlette.uvicorn._UvicornErrorFilter
    [ velodrome.access     ] logging.Logger LEVEL: 20 PROPAGATE: True
      └ FILTER troncos.logs.filters.HttpPathFilter
    [ velodrome.error      ] logging.Logger LEVEL: 40 PROPAGATE:True
    """

    logger_name = logger_name or (
        getattr(app, "title") if hasattr(app, "title") else "starlette"
    )

    # Setup uvicorn by just propagating to root logger
    uvicorn = logging.getLogger("uvicorn")
    uvicorn.propagate = True
    uvicorn.handlers = []

    # Disable uvicorn.access log
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn.propagate = False
    uvicorn_access.handlers = []

    # Put a filter on uvicorn.error log
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn.propagate = True
    uvicorn_error.handlers = []
    uvicorn_error.addFilter(_UvicornErrorFilter())

    # Set up our custom access and error logger
    app_logger_access = logging.getLogger(f"{logger_name}.access")
    app_logger_access.propagate = True
    app_logger_access.addFilter(HttpPathFilter(log_access_ignored_paths))
    app_logger_access.setLevel(logging.INFO)

    app_logger_error = logging.getLogger(f"{logger_name}.error")
    app_logger_error.setLevel(logging.ERROR)

    # Add our middleware to starlette
    app.user_middleware.append(
        Middleware(AsgiLoggingMiddleware, logger_name=logger_name)
    )
