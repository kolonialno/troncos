from typing import Optional

import ddtrace
from ddtrace import Tracer
from ddtrace.contrib.asyncio import context_provider as asyncio_context_provider
from ddtrace.helpers import get_correlation_ids
from ddtrace.provider import BaseContextProvider, DefaultContextProvider


class PrintServiceTracer(Tracer):
    """
    DataDog tracer used to report spans to DataDog.
    """


tracer = PrintServiceTracer()


def configure_async_tracer(*args, **kwargs):
    # Patch the asyncio loop
    ddtrace_asyncio_patch()  # type: ignore
    return base_configure_tracer(
        *args, context_provider=asyncio_context_provider, **kwargs
    )


def configure_tracer(*args, **kwargs):
    return base_configure_tracer(
        *args, context_provider=DefaultContextProvider(), **kwargs
    )


def base_configure_tracer(
    service: str,
    environment: str,
    context_provider: BaseContextProvider,
    enabled: bool = False,
    version: Optional[str] = None,
) -> None:
    """
    Initialize global DataDog tracer
    """

    # Enable tracer with asyncio support
    tracer.configure(enabled=enabled, context_provider=context_provider)

    # set tracer tags
    tracer.set_tags({"service": service, "env": environment, "version": version})  # type: ignore

    # Set default tracer
    ddtrace.tracer = tracer

    # Set the tracer used by the logger to attach span and trace ids.
    ddtrace.config.logging.tracer = tracer

    # Set default service name
    ddtrace.config.service = service


def tracer_injection(logger, log_method, event_dict):  # pylint: disable=unused-argument
    # get correlation ids from current tracer context
    trace_id, span_id = get_correlation_ids()

    # add ids to structlog event dictionary
    event_dict["dd.trace_id"] = trace_id or 0
    event_dict["dd.span_id"] = span_id or 0

    # add the env, service, and version configured for the tracer
    event_dict["dd.env"] = ddtrace.config.env or ""
    event_dict["dd.service"] = ddtrace.config.service or ""
    event_dict["dd.version"] = ddtrace.config.version or ""

    return event_dict
