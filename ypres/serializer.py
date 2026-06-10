import inspect
import operator
from abc import abstractmethod
from collections.abc import AsyncIterable, Callable, Iterable, Mapping
from typing import Any, NamedTuple
from warnings import deprecated

from ypres import Field


class FieldDefinitions(NamedTuple):
    name: str
    getter: Callable
    to_value: Any
    call: bool
    required: bool
    pass_self: bool
    emit_none: bool
    getter_is_coro: bool
    toval_is_coro: bool


class SerializerBase(Field):
    __slots__: list = [
        "instance",
        "many",
        "context",
        "_emit_none",
        "_data",
        "_serialized",
        "_serialized_many",
    ]

    def __init__(
        self,  # type: ignore
        instance: Any | None = None,
        many: bool = False,
        context: dict | None = None,
        emit_none: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if instance and isinstance(instance, list) and not many:
            # if we're serializing a list but have not set many=True then raise a value error.
            raise ValueError("Cannot serialize an object from a list.")
        elif (
            instance
            and many
            and (
                not isinstance(instance, Iterable | AsyncIterable)
                or isinstance(instance, dict)
            )
        ):
            # if we're not serializing a list (or some iterable object EXCEPT dicts) and many=True,
            # then raise a value error.
            raise ValueError("Cannot serialize a list from an object.")

        self.instance: Any = instance
        self.many: bool = many
        self.context: dict = context or {}
        self._emit_none = emit_none
        self._serialized: dict | None = None
        self._serialized_many: list | None = None

    @staticmethod
    @abstractmethod
    def default_getter(k: str) -> Any: ...

    _field_map: dict = {}
    _compiled_fields: list[FieldDefinitions] = []
    _compiled_sync_fields: list[Callable] = []


class SerializerMeta(type):
    @staticmethod
    def _get_fields(direct_fields: Mapping, serializer_cls) -> dict:
        field_map: dict = {}
        # Get all the fields from base classes.
        for cls in serializer_cls.__mro__[::-1]:
            if issubclass(cls, SerializerBase):
                field_map.update(cls._field_map)
        field_map.update(direct_fields)
        return field_map

    @staticmethod
    def _compile_fields(field_map: dict, serializer_cls) -> list[FieldDefinitions]:
        return [
            _compile_field_to_tuple(field, name, serializer_cls)
            for name, field in field_map.items()
        ]

    def __new__(mcs, name, bases, attrs: dict):
        # Fields declared directly on the class.
        direct_fields: dict = {}

        # Take all the Fields from the attributes.
        for attr_name, field in attrs.items():
            if isinstance(field, Field):
                direct_fields[attr_name] = field
        for k in direct_fields:
            del attrs[k]

        real_cls = super().__new__(mcs, name, bases, attrs)

        field_map = mcs._get_fields(direct_fields, real_cls)
        compiled_fields = mcs._compile_fields(field_map, real_cls)
        compiled_sync_fields = _compile_sync_fields(compiled_fields)

        real_cls._field_map = field_map  # type: ignore
        real_cls._compiled_fields = compiled_fields  # type: ignore
        real_cls._compiled_sync_fields = compiled_sync_fields  # type: ignore

        return real_cls


def _compile_field_to_tuple(
    field: Field, name: str, serializer_cls: type[SerializerBase]
) -> FieldDefinitions:
    getter = field.as_getter(name, serializer_cls)
    if getter is None:
        getter = serializer_cls.default_getter(field.attr or name)

    getter_is_coro: bool = inspect.iscoroutinefunction(getter)

    # Only set a to_value function if it has been overridden for performance.
    to_value: Callable | None = None
    if field.is_to_value_overridden():
        to_value = field.to_value

    # we only need to check if to_value is a coroutine if it is not None.
    toval_is_coro: bool = inspect.iscoroutinefunction(to_value) if to_value else False
    # Set the field name to a supplied label; defaults to the attribute name.
    name = field.label or name

    return FieldDefinitions(
        name=name,
        getter=getter,
        to_value=to_value,
        call=field.call,
        required=field.required,
        pass_self=field.getter_takes_serializer,
        emit_none=field.emit_none,
        getter_is_coro=getter_is_coro,
        toval_is_coro=toval_is_coro,
    )


def _compile_sync_fields(
    fields: list[FieldDefinitions],
) -> list[Callable]:
    return [_make_sync_field_writer(field) for field in fields]


def _required_self_call_tval(name: str, getter: Callable, tval: Callable, emit_none: bool) -> Callable:
    if emit_none:
        def emit(serializer, instance, out):
            out[name] = tval(getter(serializer, instance)())
    else:
        def emit(serializer, instance, out):
            result = tval(getter(serializer, instance)())
            if result is None:
                return
            out[name] = result
    return emit


def _required_self_call(name: str, getter: Callable, _tval: Callable | None, emit_none: bool) -> Callable:
    if emit_none:
        def emit(serializer, instance, out):
            out[name] = getter(serializer, instance)()
    else:
        def emit(serializer, instance, out):
            result = getter(serializer, instance)()
            if result is None:
                return
            out[name] = result
    return emit


def _required_self_tval(name: str, getter: Callable, tval: Callable, emit_none: bool) -> Callable:
    if emit_none:
        def emit(serializer, instance, out):
            out[name] = tval(getter(serializer, instance))
    else:
        def emit(serializer, instance, out):
            result = tval(getter(serializer, instance))
            if result is None:
                return
            out[name] = result
    return emit


def _required_self(name: str, getter: Callable, _tval: Callable | None, emit_none: bool) -> Callable:
    if emit_none:
        def emit(serializer, instance, out):
            out[name] = getter(serializer, instance)
    else:
        def emit(serializer, instance, out):
            result = getter(serializer, instance)
            if result is None:
                return
            out[name] = result
    return emit


def _optional_self_call_tval(name: str, getter: Callable, tval: Callable, emit_none: bool) -> Callable:
    def emit(serializer, instance, out):
        try:
            result = getter(serializer, instance)
        except (KeyError, AttributeError):
            return
        if result is None:
            if emit_none:
                out[name] = None
            return
        result = tval(result())
        if result is None and not emit_none:
            return
        out[name] = result
    return emit


def _optional_self_call(name: str, getter: Callable, _tval: Callable | None, emit_none: bool) -> Callable:
    def emit(serializer, instance, out):
        try:
            result = getter(serializer, instance)
        except (KeyError, AttributeError):
            return
        if result is None:
            if emit_none:
                out[name] = None
            return
        result = result()
        if result is None and not emit_none:
            return
        out[name] = result
    return emit


def _optional_self_tval(name: str, getter: Callable, tval: Callable, emit_none: bool) -> Callable:
    def emit(serializer, instance, out):
        try:
            result = getter(serializer, instance)
        except (KeyError, AttributeError):
            return
        if result is None:
            if emit_none:
                out[name] = None
            return
        result = tval(result)
        if result is None and not emit_none:
            return
        out[name] = result
    return emit


def _optional_self(name: str, getter: Callable, _tval: Callable | None, emit_none: bool) -> Callable:
    def emit(serializer, instance, out):
        try:
            result = getter(serializer, instance)
        except (KeyError, AttributeError):
            return
        if result is None:
            if emit_none:
                out[name] = None
            return
        out[name] = result
    return emit


def _required_call_tval(name: str, getter: Callable, tval: Callable, emit_none: bool) -> Callable:
    if emit_none:
        def emit(serializer, instance, out):
            out[name] = tval(getter(instance)())
    else:
        def emit(serializer, instance, out):
            result = tval(getter(instance)())
            if result is None:
                return
            out[name] = result
    return emit


def _required_call(name: str, getter: Callable, _tval: Callable | None, emit_none: bool) -> Callable:
    if emit_none:
        def emit(serializer, instance, out):
            out[name] = getter(instance)()
    else:
        def emit(serializer, instance, out):
            result = getter(instance)()
            if result is None:
                return
            out[name] = result
    return emit


def _required_tval(name: str, getter: Callable, tval: Callable, emit_none: bool) -> Callable:
    if emit_none:
        def emit(serializer, instance, out):
            out[name] = tval(getter(instance))
    else:
        def emit(serializer, instance, out):
            result = tval(getter(instance))
            if result is None:
                return
            out[name] = result
    return emit


def _required_plain(name: str, getter: Callable, _tval: Callable | None, emit_none: bool) -> Callable:
    if emit_none:
        def emit(serializer, instance, out):
            out[name] = getter(instance)
    else:
        def emit(serializer, instance, out):
            result = getter(instance)
            if result is None:
                return
            out[name] = result
    return emit


def _optional_call_tval(name: str, getter: Callable, tval: Callable, emit_none: bool) -> Callable:
    def emit(serializer, instance, out):
        try:
            result = getter(instance)
        except (KeyError, AttributeError):
            return
        if result is None:
            if emit_none:
                out[name] = None
            return
        result = tval(result())
        if result is None and not emit_none:
            return
        out[name] = result
    return emit


def _optional_call(name: str, getter: Callable, _tval: Callable | None, emit_none: bool) -> Callable:
    def emit(serializer, instance, out):
        try:
            result = getter(instance)
        except (KeyError, AttributeError):
            return
        if result is None:
            if emit_none:
                out[name] = None
            return
        result = result()
        if result is None and not emit_none:
            return
        out[name] = result
    return emit


def _optional_tval(name: str, getter: Callable, tval: Callable, emit_none: bool) -> Callable:
    def emit(serializer, instance, out):
        try:
            result = getter(instance)
        except (KeyError, AttributeError):
            return
        if result is None:
            if emit_none:
                out[name] = None
            return
        result = tval(result)
        if result is None and not emit_none:
            return
        out[name] = result
    return emit


def _optional_plain(name: str, getter: Callable, _tval: Callable | None, emit_none: bool) -> Callable:
    def emit(serializer, instance, out):
        try:
            result = getter(instance)
        except (KeyError, AttributeError):
            return
        if result is None:
            if emit_none:
                out[name] = None
            return
        out[name] = result
    return emit


# Each key is `(pass_self, required, call, has_to_value)`.
# The selected factory returns a specialized writer for that exact field shape,
# so the runtime serializer loop does not need to branch on these flags.
_SYNC_FIELD_WRITER_FACTORIES: dict[tuple[bool, bool, bool, bool], Callable] = {
    (True, True, True, True): _required_self_call_tval,
    (True, True, True, False): _required_self_call,
    (True, True, False, True): _required_self_tval,
    (True, True, False, False): _required_self,
    (True, False, True, True): _optional_self_call_tval,
    (True, False, True, False): _optional_self_call,
    (True, False, False, True): _optional_self_tval,
    (True, False, False, False): _optional_self,
    (False, True, True, True): _required_call_tval,
    (False, True, True, False): _required_call,
    (False, True, False, True): _required_tval,
    (False, True, False, False): _required_plain,
    (False, False, True, True): _optional_call_tval,
    (False, False, True, False): _optional_call,
    (False, False, False, True): _optional_tval,
    (False, False, False, False): _optional_plain,
}


def _make_sync_field_writer(field: FieldDefinitions) -> Callable:
    # `bool(field.to_value)` is the compile-time "has transform" flag used by
    # the dispatch table above. The actual callable is still passed through to
    # the selected factory for execution.
    key = (field.pass_self, field.required, field.call, bool(field.to_value))
    factory = _SYNC_FIELD_WRITER_FACTORIES[key]
    return factory(field.name, field.getter, field.to_value, field.emit_none)


class Serializer(SerializerBase, metaclass=SerializerMeta):
    default_getter: Any = operator.attrgetter

    def _serialize(self, instance: Any, fields: list[FieldDefinitions]) -> dict:
        v: dict = {}

        for emit in self._compiled_sync_fields:
            emit(self, instance, v)

        return v

    def to_value(self, value: Any) -> list | dict:
        if self.many:
            return self._serialize_list(value)
        return self._serialize_dict(value)

    def _serialize_dict(self, instance: Any) -> dict:
        self._serialized = self._serialize(instance, self._compiled_fields)
        return self._serialized or {}

    def _serialize_list(self, instance: Any) -> list:
        self._serialized_many = [
            self._serialize(o, self._compiled_fields) for o in instance
        ]
        return self._serialized_many or []

    @property
    @deprecated("Use the .serialized and .serialized_many properties.")
    def data(self) -> list | dict:
        """Get the serialized data from the :class:`Serializer`.

        The data will be cached for future accesses.
        """
        # Cache the data for next time .data is called.
        return self.to_value(self.instance)

    @property
    def serialized(self) -> dict:
        if self._serialized is not None:
            return self._serialized
        return self._serialize_dict(self.instance)

    @property
    def serialized_many(self) -> list:
        if self._serialized_many is not None:
            return self._serialized_many
        return self._serialize_list(self.instance)


class DictSerializer(Serializer):
    default_getter: Any = operator.itemgetter


class AsyncSerializer(SerializerBase, metaclass=SerializerMeta):
    default_getter: Any = operator.attrgetter

    async def _serialize(self, instance: Any, fields: list[FieldDefinitions]) -> dict:
        v: dict = {}
        for (
            name,
            getter,
            tval,
            call,
            required,
            pass_self,
            emit_none,
            getter_coro,
            toval_coro,
        ) in fields:
            try:
                if getter_coro:
                    result = (
                        await getter(self, instance)
                        if pass_self
                        else await getter(instance)
                    )
                else:
                    result = getter(self, instance) if pass_self else getter(instance)
            except (KeyError, AttributeError):
                if required:
                    raise
                continue

            if result is None and not required:
                if emit_none:
                    v[name] = result
                    continue
                continue

            if call:
                result = result()

            if tval:
                if toval_coro:
                    result = await tval(result)
                else:
                    result = tval(result)

            if result is None and not emit_none:
                continue

            v[name] = result

        return v

    async def to_value(self, value: Any) -> list | dict:
        if self.many:
            return await self._serialize_list(value)
        return await self._serialize_dict(value)

    async def _serialize_dict(self, instance: Any) -> dict:
        self._serialized = await self._serialize(instance, self._compiled_fields)
        return self._serialized or {}

    async def _serialize_list(self, instance: Any) -> list:
        if isinstance(instance, AsyncIterable):
            self._serialized_many = [
                await self._serialize(o, self._compiled_fields) async for o in instance
            ]
        else:
            self._serialized_many = [
                await self._serialize(o, self._compiled_fields) for o in instance
            ]
        return self._serialized_many or []

    @property
    @deprecated("Use the .serialized and .serialized_many properties.")
    async def data(self) -> list | dict:
        """Get the serialized data from the :class:`Serializer`.

        The data will be cached for future accesses.
        """
        # Cache the data for next time .data is called.
        return await self.to_value(self.instance)

    @property
    async def serialized(self) -> dict:
        if self._serialized is not None:
            return self._serialized
        return await self._serialize_dict(self.instance)

    @property
    async def serialized_many(self) -> list:
        if self._serialized_many is not None:
            return self._serialized_many
        return await self._serialize_list(self.instance)


class AsyncDictSerializer(AsyncSerializer):
    default_getter: Any = operator.itemgetter
