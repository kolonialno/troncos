import opentelemetry.trace
import pytest

from troncos.traces.decorate import trace_function


@pytest.mark.asyncio
async def test_trace_function_no_args() -> None:
    @trace_function
    async def f() -> None:
        assert opentelemetry.trace.get_current_span()

    await f()


@pytest.mark.asyncio
async def test_trace_function_fn_arg() -> None:
    async def f() -> None:
        assert opentelemetry.trace.get_current_span()

    await trace_function(f)()


@pytest.mark.asyncio
async def test_trace_function_call_decorator() -> None:
    @trace_function()
    async def f() -> None:
        assert opentelemetry.trace.get_current_span()

    await f()
