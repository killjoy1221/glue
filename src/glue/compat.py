import sys

if sys.version_info < (3, 11):
    import tomli as tomllib
else:
    import tomllib

if sys.version_info < (3, 10):
    from typing import Union as UnionType

    NoneType = type(None)
else:
    from types import NoneType, UnionType

__all__ = [
    "NoneType",
    "UnionType",
    "tomllib",
]
