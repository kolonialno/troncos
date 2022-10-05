import asyncio
import inspect
import logging

# noinspection PyUnresolvedReferences,PyProtectedMember
from contextlib import _GeneratorContextManager
from functools import wraps
from types import FunctionType
from typing import Any, Callable, Type, TypeVar, cast

import opentelemetry.trace
from opentelemetry.sdk.resources import Attributes

from troncos import OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION

_TRACE_IGNORE_ATTR = "_trace_ignore"
TFun = TypeVar("TFun", bound=Callable[..., Any])
TClass = TypeVar("TClass")


def _trace_function(
    f: TFun,
    name: str | None = None,
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> TFun:
    if asyncio.iscoroutinefunction(f):

        @wraps(f)
        async def traced_func_async(*args: tuple, **kwargs: dict[str, Any]) -> Any:
            tp = tracer_provider or opentelemetry.trace.get_tracer_provider()
            tr = tp.get_tracer(OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION)
            with tr.start_as_current_span(
                name or f"{f.__module__}.{f.__qualname__}", attributes=attributes
            ):
                resolved_future = await f(*args, **kwargs)
                return resolved_future

        if hasattr(f, _TRACE_IGNORE_ATTR):
            return f

        return cast(TFun, traced_func_async)
    else:

        @wraps(f)
        def traced_func(*args: tuple, **kwargs: dict[str, Any]) -> Any:
            tp = tracer_provider or opentelemetry.trace.get_tracer_provider()
            tr = tp.get_tracer(OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION)
            with tr.start_as_current_span(
                name or f"{f.__module__}.{f.__qualname__}", attributes=attributes
            ):
                return f(*args, **kwargs)

        if hasattr(f, _TRACE_IGNORE_ATTR):
            return f

        return cast(TFun, traced_func)


def trace_function(
    *args: Any,
    name: str | None = None,
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> Any:
    """
    This decorator adds tracing to a function. You can supply a tracer provider, if none
    is supplied, the global tracer provider will be used. Example:

    @trace_function
    def myfunc1()
        return "This will be traced"

    @trace_function(tracer_provider=custom_provider)
    def myfunc2()
        return "This will be traced using a custom provider"
    """

    if len(args) > 1:
        raise RuntimeError("Invalid usage of decorator")
    if len(args) == 1 and (callable(args[0]) or asyncio.iscoroutinefunction(args[0])):
        return _trace_function(args[0], name, attributes, tracer_provider)
    else:
        # No args
        def _inner(f: TFun) -> Any:
            return _trace_function(f, name, attributes, tracer_provider)

        return _inner


def trace_block(
    name: str,
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> _GeneratorContextManager[opentelemetry.trace.Span]:
    """
    Trace using a with statement. You can supply a tracer provider, if none is supplied,
    the global tracer provider will be used. Example:

    with trace_block(name="my block", attributes={"some": "attribute"}):
        time.sleep(1)
    """
    tp = tracer_provider or opentelemetry.trace.get_tracer_provider()
    tr = tp.get_tracer(OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION)
    return tr.start_as_current_span(name, attributes=attributes)


def trace_class(
    *args: Any,
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> Type[TClass] | Callable[[Type[TClass]], Type[TClass]]:
    """
    This decorator adds a tracing decorator to every method of the decorated class. If
    you don't want some methods to be traced, you can add the 'trace_ignore' decorator
    to them. You can supply a tracer provider, if none is supplied, the global tracer
    provider will be used. Example:

    @trace_class
    class MyClass1:

        def m1(self):
            return "This will be traced"

        @trace_ignore
        def m2(self):
            return "This will not be traced"


    @trace_class(tracer_provider=custom_provider)
    class MyClass2:

        def m3(self):
            return "This will be traced using a custom provider"
    """

    def _dec(cls: Type[TClass]) -> Type[TClass]:
        for key, value in cls.__dict__.items():
            if key.startswith("_"):
                continue
            if not (
                isinstance(value, FunctionType) or asyncio.iscoroutinefunction(value)
            ):
                continue

            logging.getLogger(__name__).debug(f"Tracing function {cls.__name__}.{key}")
            setattr(
                cls,
                key,
                _trace_function(
                    value,
                    name=None,
                    attributes=attributes,
                    tracer_provider=tracer_provider,
                ),
            )
        return cls

    if len(args) > 1:
        raise RuntimeError("Invalid usage of decorator")
    if len(args) == 1:
        return _dec(args[0])
    else:
        return _dec


def trace_module(
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> None:
    """
    This function adds a tracing decorator to every function of the calling module. If
    you don't want some functions to be traced, you can add the 'trace_ignore' decorator
    to them. You can supply a tracer provider, if none is supplied, the global tracer
    provider will be used. Example:

    # Start of module

    def my_function():
        return "This func will be traced"

    @trace_ignore
    def my_function():
        return "This func will not be traced"

    trace_module()

    # End of module
    """

    frame = inspect.stack()[1].frame
    scope = frame.f_locals
    module_name = scope.get("__name__", "unknown")
    for key, value in list(frame.f_locals.items()):
        if key.startswith("_"):
            continue
        if not (isinstance(value, FunctionType) or asyncio.iscoroutinefunction(value)):
            continue
        if getattr(value, "__module__", None) != module_name:
            continue

        logging.getLogger(__name__).debug(f"Tracing function {module_name}.{key}")
        scope[key] = _trace_function(
            value, name=None, attributes=attributes, tracer_provider=tracer_provider
        )


def trace_ignore(f: TFun) -> TFun:
    """
    Decorator to disable automatic tracing of functions.
    See 'trace_module' and 'trace_class'.
    """

    setattr(f, _TRACE_IGNORE_ATTR, ())
    return f
