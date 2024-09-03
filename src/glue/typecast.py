from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, Union

from typing_extensions import TypeAlias, get_args, get_origin, overload

from .compat import NoneType, UnionType

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

    T_Data = TypeVar("T_Data", bound=DataclassInstance)


T = TypeVar("T")

Primitive: TypeAlias = (
    "str | float | int | bool | None | list[Primitive] | dict[str, Primitive]"
)


class TypeCastError(Exception):
    def __init__(self, key: str, message: str) -> None:
        self.key = key
        self.message = message
        super().__init__(f"Unable to parse config key {key!r}: {message}")


def _build_obj_key(key: str, next_key: str) -> str:
    return f"{key}{'.' if key else ''}{next_key}"


def _coerce_dataclass(typ: type[T_Data], val: Primitive, *, key: str) -> T_Data:
    val = _coerce_type(dict, val, key=key)
    all_fields = {f.name: f.type for f in fields(typ)}
    kwargs = {
        k: typecast(all_fields.get(k, Any), v, key=_build_obj_key(key, k))
        for k, v in val.items()
    }
    try:
        return typ(**kwargs)
    except TypeError:
        available_keys = {f.name for f in fields(typ)}
        required_keys = {
            f.name for f in fields(typ) if f.default is f.default_factory is MISSING
        }
        actual_keys = set(kwargs.keys())

        missing = list(required_keys.difference(actual_keys))
        unknown = list(actual_keys.difference(available_keys))

        missing.sort()
        unknown.sort()

        msg_parts = []
        if missing:
            msg_parts.append(f"missing keys: {missing}")
        if unknown:
            msg_parts.append(f"unknown keys: {unknown}")

        msg = ", ".join(msg_parts)
        if not msg:
            raise  # something else went wrong

        raise TypeCastError(key, msg) from None


@overload
def _coerce_type(typ: type[T], val: Primitive, *, key: str) -> T: ...
@overload
def _coerce_type(typ: type[Any], val: Primitive, *, key: str) -> Any: ...
def _coerce_type(typ: type[Any], val: Primitive, *, key: str) -> Any:
    if typ is Any:
        return val

    if is_dataclass(typ):
        return _coerce_dataclass(typ, val, key=key)

    if not isinstance(val, typ):
        msg = f"Value was {type(val).__name__}, but expected {typ.__name__}"
        raise TypeCastError(key, msg)
    return val


def _coerce_dict(typ: type[dict[str, T]], val: Primitive, *, key: str) -> dict[str, T]:
    val = _coerce_type(dict, val, key=key)

    kt, vt = get_args(typ)
    assert kt is str, "non-string dict keys are not supported"
    return {k: typecast(vt, v, key=_build_obj_key(key, k)) for k, v in val.items()}


def _coerce_list(typ: type[list[T]], val: Primitive, *, key: str) -> list[T]:
    val = _coerce_type(list, val, key=key)
    (it,) = get_args(typ)
    return [typecast(it, item, key=f"{key}[{index}]") for index, item in enumerate(val)]


def _coerce_union(typ: type[T], val: Primitive, *, key: str) -> T:
    errors = []
    for ut in get_args(typ):
        if ut is NoneType:
            continue
        try:
            return typecast(ut, val, key=key)
        except TypeCastError as e:
            errors.append(f"- {e.message}")
    raise TypeCastError(key, "\nPossible issues:\n" + "\n".join(errors))


_origin_mapper = {
    dict: _coerce_dict,
    list: _coerce_list,
    Union: _coerce_union,
    UnionType: _coerce_union,
}


class Coercable(Protocol):
    def __call__(self, typ: Any, val: Primitive, *, key: str) -> Any: ...


@overload
def typecast(typ: type[T], val: Primitive, *, key: str = ...) -> T: ...
@overload
def typecast(typ: Any, val: Primitive, *, key: str = ...) -> Any: ...
def typecast(typ: Any, val: Primitive, *, key: str = "") -> Any:
    coerce: Coercable
    if isinstance(typ, type):
        coerce = _coerce_type
    elif (origin := get_origin(typ)) in _origin_mapper:
        coerce = _origin_mapper[origin]
    else:
        raise NotImplementedError(f"{typ} is not supported yet")

    return coerce(typ, val, key=key)
