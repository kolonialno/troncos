from typing import Any

import pytest

from troncos.tracing.decorators import trace_class


@trace_class
class A:
    dummy_classvar = 1

    def _dummy_underscore(self) -> None:
        pass

    def dummy_method(self) -> None:
        pass

    @staticmethod
    def dummy_staticmethod() -> None:
        pass

    @classmethod
    def dummy_classmethod(cls) -> None:
        pass

    @property
    def dummy_property(self) -> None:
        pass

    # Async

    async def adummy_method(self) -> None:
        pass

    @staticmethod
    async def adummy_staticmethod() -> None:
        pass

    @classmethod
    async def adummy_classmethod(cls) -> None:
        pass

    @property
    async def adummy_property(self) -> None:
        pass


@pytest.mark.parametrize(
    "class_attr",
    [
        A.dummy_method,
        A.adummy_method,
    ],
)
def test_trace_class_is_traced(class_attr: Any) -> None:
    assert hasattr(class_attr, "__wrapped__"), f"Expected {class_attr} to be traced"


@pytest.mark.parametrize(
    "class_attr",
    [
        A._dummy_underscore,
        A.dummy_property,
        A.adummy_property,
        A.adummy_staticmethod,
        A.adummy_classmethod,
        A.adummy_staticmethod,
        A.dummy_classmethod,
    ],
)
def test_trace_class_is_not_traced(class_attr: Any) -> None:
    assert (
        hasattr(class_attr, "__wrapped__") is False
    ), f"Expected {class_attr} not to be traced"
