import asyncio
import contextlib
import inspect
import logging

# noinspection PyUnresolvedReferences,PyProtectedMember
from functools import wraps
from types import FunctionType
from typing import (
    Any,
    Awaitable,
    Callable,
    Iterator,
    ParamSpec,
    Type,
    TypeVar,
    cast,
    overload,
)

from troncos._ddlazy import ddlazy

_TRACE_IGNORE_ATTR = "_trace_ignore"

TClass = TypeVar("TClass")

P = ParamSpec("P")
R = TypeVar("R")


@contextlib.contextmanager
def trace_block(
    name: str,
    *,
    resource: str | None = None,
    service: str | None = None,
    span_type: str | None = None,
    attributes: dict[str, str] | None = None,
) -> Iterator[Any]:  # This is set to any, because we want to lazy-load ddtrace
    """
    Trace a code block using a with statement. Example:

    with trace_block("cool.block", resource="data!", attributes={"some": "attribute"}):
        time.sleep(1)
    """

    attributes = attributes or {}
    with ddlazy.dd_tracer().trace(
        name=name,
        resource=resource,
        service=service,
        span_type=span_type,
    ) as span:
        if attributes:
            span.set_tags(attributes)
        yield span


def _trace_function(
    f: Callable[P, R],
    name: str | None = None,
    resource: str | None = None,
    service: str | None = None,
    span_type: str | None = None,
    attributes: dict[str, str] | None = None,
) -> Callable[P, R]:
    if inspect.iscoroutinefunction(f):
        # Async function
        @wraps(f)
        async def traced_func_async(*args: P.args, **kwargs: P.kwargs) -> R:
            with trace_block(
                name=name or f"{f.__module__}.{f.__qualname__}",
                resource=resource,
                service=service,
                span_type=span_type,
                attributes=attributes,
            ):
                awaitable_func = cast(Callable[P, Awaitable[R]], f)
                return await awaitable_func(*args, **kwargs)

        if hasattr(f, _TRACE_IGNORE_ATTR):
            return f  # type: ignore[return-value]

        return cast(Callable[P, R], traced_func_async)

    else:
        # "Regular" function
        @wraps(f)
        def traced_func(*args: P.args, **kwargs: P.kwargs) -> R:
            with trace_block(
                name=name or f"{f.__module__}.{f.__qualname__}",
                resource=resource,
                service=service,
                span_type=span_type,
                attributes=attributes,
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
    service: str | None = None,
    span_type: str | None = None,
    attributes: dict[str, str] | None = None,
) -> Callable[P, R]:
    ...


@overload
def trace_function(
    fn: None = None,
    *,
    name: str | None = None,
    resource: str | None = None,
    service: str | None = None,
    span_type: str | None = None,
    attributes: dict[str, str] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    ...


def trace_function(
    fn: Callable[P, R] | None = None,
    *,
    name: str | None = None,
    resource: str | None = None,
    service: str | None = None,
    span_type: str | None = None,
    attributes: dict[str, str] | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """
    This decorator adds tracing to a function. Example:

    @trace_function
    def myfunc1()
        return "This will be traced"

    @trace_function(service="custom_service")
    def myfunc2()
        return "This will be traced as a custom service"
    """

    if fn and (callable(fn) or asyncio.iscoroutinefunction(fn)):
        assert fn  # type: ignore[truthy-function]
        return _trace_function(fn, name, resource, service, span_type, attributes)
    else:
        # No args
        def _inner(f: Callable[P, R]) -> Callable[P, R]:
            return _trace_function(f, name, resource, service, span_type, attributes)

        return _inner


@overload
def trace_class(
    klass: None = None,
    *,
    resource: str | None = None,
    service: str | None = None,
    span_type: str | None = None,
    attributes: dict[str, str] | None = None,
) -> Callable[[Type[TClass]], Type[TClass]]:
    ...


@overload
def trace_class(
    klass: Type[TClass],
    *,
    resource: str | None = None,
    service: str | None = None,
    span_type: str | None = None,
    attributes: dict[str, str] | None = None,
) -> Type[TClass]:
    ...


def trace_class(
    klass: Type[TClass] | None = None,
    *,
    resource: str | None = None,
    service: str | None = None,
    span_type: str | None = None,
    attributes: dict[str, str] | None = None,
) -> Type[TClass] | Callable[[Type[TClass]], Type[TClass]]:
    """
    This decorator adds a tracing decorator to every method of the decorated class. If
    you don't want some methods to be traced, you can add the 'trace_ignore' decorator
    to them. Example:

    @trace_class
    class MyClass1:

        def m1(self):
            return "This will be traced"

        @trace_ignore
        def m2(self):
            return "This will not be traced"


    @trace_class(service="custom_service")
    class MyClass2:

        def m3(self):
            return "This will be traced as a custom service"
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
                    service=service,
                    span_type=span_type,
                    attributes=attributes,
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
    service: str | None = None,
    span_type: str | None = None,
    attributes: dict[str, str] | None = None,
) -> None:
    """
    This function adds a tracing decorator to every function of the calling module. If
    you don't want some functions to be traced, you can add the 'trace_ignore' decorator
    to them. Example:

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
            service=service,
            span_type=span_type,
            attributes=attributes,
        )


def trace_ignore(f: Callable[P, R]) -> Callable[P, R]:
    """
    Decorator to disable automatic tracing of functions.
    See 'trace_module' and 'trace_class'.
    """

    setattr(f, _TRACE_IGNORE_ATTR, ())
    return f


def trace_set_span_attributes(attr: dict[str, str | bool | int]) -> None:
    """
    Add attributes to current span: Example:

    with trace_block("cool.block", attributes={"some": "attribute"}):
        result = calculate_something()
        trace_set_span_attributes({"result": result})
    """

    span = ddlazy.dd_tracer().current_span()
    if span:
        span.set_tags(attr)


def trace_set_traceback() -> None:
    ddlazy.dd_tracer().current_span().set_traceback()
