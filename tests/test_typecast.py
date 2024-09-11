import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional, Union

import pytest

from glue.typecast import TypeCastError, typecast

AnyFunc = Callable[[], Any]


@dataclass
class EmptyClass:
    pass


@dataclass
class MultipleFields:
    a: str
    b: str


@dataclass
class UnionFields:
    c: Union[EmptyClass, MultipleFields]  # noqa: FA100


@dataclass
class OptionalField:
    x: Optional[str]  # noqa: FA100


@dataclass
class ListField:
    lst: list[str]


@dataclass
class DictField:
    dct: dict[str, ListField]


@pytest.mark.parametrize(
    ("typ", "val", "result"),
    [
        (str, "hello", "hello"),
        (EmptyClass, {}, EmptyClass()),
        (MultipleFields, {"a": "A", "b": "B"}, MultipleFields("A", "B")),
        (UnionFields, {"c": {}}, UnionFields(EmptyClass())),
        (
            UnionFields,
            {"c": {"a": "A", "b": "B"}},
            UnionFields(MultipleFields("A", "B")),
        ),
        (OptionalField, {"x": "YY"}, OptionalField("YY")),
        (OptionalField, {"x": None}, OptionalField(None)),
        (ListField, {"lst": []}, ListField([])),
        (ListField, {"lst": ["foo", "bar"]}, ListField(["foo", "bar"])),
        (DictField, {"dct": {"a": {"lst": ["a"]}}}, DictField({"a": ListField(["a"])})),
    ],
)
def test_typecast(typ: type, val: Any, result: Any) -> None:
    assert typecast(typ, val) == result


def test_typecast_generic_error() -> None:
    with pytest.raises(TypeCastError, match="Value was str, but expected int"):
        typecast(list[int], ["3"])


def test_unsupported_error() -> None:
    typ = re.escape(str(AnyFunc))
    with pytest.raises(NotImplementedError, match=f"{typ} is not supported yet"):
        typecast(AnyFunc, "")


@dataclass
class ClassWithPostInit:
    a: str

    def __post_init__(self) -> None:
        if not self.a:  # pragma: no cover
            msg = "a cannot be empty string"
            raise TypeError(msg)


def test_some_other_error() -> None:
    with pytest.raises(TypeError, match="a cannot be empty string"):
        typecast(ClassWithPostInit, {"a": ""})


def test_union_error() -> None:
    with pytest.raises(
        TypeCastError,
        match=r"""
Unable to parse config key 'c':\s
Possible issues:
- unknown keys: \['x'\]
- missing keys: \['a', 'b'\], unknown keys: \['x'\]
""".strip(),
    ):
        typecast(UnionFields, {"c": {"x": "y"}})
