from troncos.traces.decorate import trace_block
from troncos.traces.propagation import (
    add_context_to_dict,
    get_context_from_dict,
    get_propagation_value,
)


def test_propagation_inject_no_context() -> None:
    d: dict[str, str] = {}
    add_context_to_dict(d)
    assert len(d) == 0


def test_propagation_inject() -> None:
    d: dict[str, str] = {}
    with trace_block("test"):
        add_context_to_dict(d)

    assert len(d) == 3
    assert d.get("b3", None)
    assert d.get("traceparent", None)


def test_propagation_extract_no_context() -> None:
    d: dict[str, str] = {}
    context = get_context_from_dict(d)
    assert not context.trace_id


def test_propagation_extract() -> None:
    d: dict[str, str] = {}
    with trace_block("test"):
        add_context_to_dict(d)

    context = get_context_from_dict(d)
    assert context.trace_id


def test_get_propagation_value() -> None:
    assert get_propagation_value() is None

    with trace_block("test"):
        default = get_propagation_value()
        assert default

        w3c = get_propagation_value("w3c")
        assert w3c
        assert default == w3c

        b3 = get_propagation_value("b3")
        assert b3
