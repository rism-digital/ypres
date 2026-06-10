from importlib.metadata import PackageNotFoundError, version

from ypres.fields import (
    BoolField,
    DateField,
    DateTimeField,
    Field,
    FloatField,
    IntField,
    MethodField,
    StaticField,
    StrField,
)
from ypres.serializer import (
    AsyncDictSerializer,
    AsyncSerializer,
    DictSerializer,
    Serializer,
)

try:
    __version__ = version("ypres")
except PackageNotFoundError:
    __version__ = "0+unknown"

__author__ = "Andrew Hankinson"
__license__ = "MIT"

__all__ = [
    "Serializer",
    "DictSerializer",
    "AsyncSerializer",
    "AsyncDictSerializer",
    "Field",
    "BoolField",
    "IntField",
    "FloatField",
    "MethodField",
    "StrField",
    "StaticField",
    "DateField",
    "DateTimeField",
]
