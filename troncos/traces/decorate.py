import asyncio
import inspect
import logging

# noinspection PyUnresolvedReferences,PyProtectedMember
from contextlib import _GeneratorContextManager
from functools import wraps
from types import FunctionType
from typing import Awaitable, Callable, ParamSpec, Type, TypeVar, cast, overload

import opentelemetry.trace
from opentelemetry.sdk.resources import Attributes

from troncos import OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION

_TRACE_IGNORE_ATTR = "_trace_ignore"

TClass = TypeVar("TClass")

P = ParamSpec("P")
R = TypeVar("R")


def _trace_function(
    f: Callable[P, R],
    name: str | None = None,
    resource: str | None = None,
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> Callable[P, R]:
    attributes = attributes or {}
    if resource:
        attributes["resource"] = resource

    if inspect.iscoroutinefunction(f):

        @wraps(f)
        async def traced_func_async(*args: P.args, **kwargs: P.kwargs) -> R:
            tp = tracer_provider or opentelemetry.trace.get_tracer_provider()
            tr = tp.get_tracer(OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION)
            with tr.start_as_current_span(
                name or f"{f.__module__}.{f.__qualname__}", attributes=attributes
            ):
                awaitable_func = cast(Callable[P, Awaitable[R]], f)
                return await awaitable_func(*args, **kwargs)

        if hasattr(f, _TRACE_IGNORE_ATTR):
            return f

        return cast(Callable[P, R], traced_func_async)

    else:

        @wraps(f)
        def traced_func(*args: P.args, **kwargs: P.kwargs) -> R:
            tp = tracer_provider or opentelemetry.trace.get_tracer_provider()
            tr = tp.get_tracer(OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION)
            with tr.start_as_current_span(
                name or f"{f.__module__}.{f.__qualname__}", attributes=attributes
            ):
                return f(*args, **kwargs)

        if hasattr(f, _TRACE_IGNORE_ATTR):
            return f

        return traced_func


@overload
def trace_function(
    fn: Callable[P, R],
    *,
    name: str | None = None,
    resource: str | None = None,
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> Callable[P, R]:
    ...


@overload
def trace_function(
    fn: None = None,
    *,
    name: str | None = None,
    resource: str | None = None,
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    ...


def trace_function(
    fn: Callable[P, R] | None = None,
    *,
    name: str | None = None,
    resource: str | None = None,
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> (Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]):
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
    if fn and (callable(fn) or asyncio.iscoroutinefunction(fn)):
        assert fn
        return _trace_function(fn, name, resource, attributes, tracer_provider)
    else:
        # No args
        def _inner(f: Callable[P, R]) -> Callable[P, R]:
            return _trace_function(f, name, resource, attributes, tracer_provider)

        return _inner


def trace_block(
    name: str,
    *,
    resource: str | None = None,
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> _GeneratorContextManager[opentelemetry.trace.Span]:
    """
    Trace using a with statement. You can supply a tracer provider, if none is supplied,
    the global tracer provider will be used. Example:

    with trace_block("cool.block", "data!", attributes={"some": "attribute"}):
        time.sleep(1)
    """
    attributes = attributes or {}
    if resource:
        attributes["resource"] = resource

    tp = tracer_provider or opentelemetry.trace.get_tracer_provider()
    tr = tp.get_tracer(OTEL_LIBRARY_NAME, OTEL_LIBRARY_VERSION)
    return tr.start_as_current_span(name, attributes=attributes)


@overload
def trace_class(
    klass: None = None,
    *,
    resource: str | None = None,
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> Callable[[Type[TClass]], Type[TClass]]:
    ...


@overload
def trace_class(
    klass: Type[TClass],
    *,
    resource: str | None = None,
    attributes: Attributes | None = None,
    tracer_provider: opentelemetry.trace.TracerProvider | None = None,
) -> Type[TClass]:
    ...


def trace_class(
    klass: Type[TClass] | None = None,
    *,
    resource: str | None = None,
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
                    resource=resource,
                    attributes=attributes,
                    tracer_provider=tracer_provider,
                ),
            )
        return cls

    if klass:
        return _dec(klass)
    else:
        return _dec


def trace_module(
    *,
    resource: str | None = None,
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
            value,
            name=None,
            resource=resource,
            attributes=attributes,
            tracer_provider=tracer_provider,
        )


def trace_ignore(f: Callable[P, R]) -> Callable[P, R]:
    """
    Decorator to disable automatic tracing of functions.
    See 'trace_module' and 'trace_class'.
    """

    setattr(f, _TRACE_IGNORE_ATTR, ())
    return f
