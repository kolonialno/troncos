import pytest

from troncos._ddlazy import ddlazy
from troncos.traces.decorate import trace_function


@pytest.mark.asyncio
async def test_trace_function_no_args() -> None:
    @trace_function
    async def f() -> None:
        assert ddlazy.dd_tracer().current_trace_context()

    await f()


@pytest.mark.asyncio
async def test_trace_function_fn_arg() -> None:
    async def f() -> None:
        assert ddlazy.dd_tracer().current_trace_context()

    await trace_function(f)()


@pytest.mark.asyncio
async def test_trace_function_call_decorator() -> None:
    @trace_function()
    async def f() -> None:
        assert ddlazy.dd_tracer().current_trace_context()

    await f()
