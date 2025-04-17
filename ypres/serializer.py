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

        real_cls._field_map = field_map  # type: ignore
        real_cls._compiled_fields = compiled_fields  # type: ignore

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

    toval_is_coro: bool = inspect.iscoroutinefunction(to_value)
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


class Serializer(SerializerBase, metaclass=SerializerMeta):
    default_getter: Any = operator.attrgetter

    def _serialize(self, instance: Any, fields: list[FieldDefinitions]) -> dict:
        v: dict = {}

        for (
            name,
            getter,
            tval,
            call,
            required,
            pass_self,
            emit_none,
            _,
            _,
        ) in fields:
            try:
                result = getter(self, instance) if pass_self else getter(instance)
            except (KeyError, AttributeError):
                if required:
                    raise
                continue

            # Skip if result is None and not required
            if result is None and not required:
                if emit_none:
                    v[name] = result
                    continue
                continue

            if call:
                result = result()

            if tval:
                result = tval(result)

            # If `None` values should not appear in the output,
            # and we have a result that is None, we just skip
            # it and continue to the next field.
            if result is None and not emit_none:
                continue

            v[name] = result

        return v

    def to_value(self, instance: Any) -> list | dict:
        if self.many:
            return self._serialize_list(instance)
        return self._serialize_dict(instance)

    def _serialize_dict(self, instance: Any) -> dict:
        self._serialized = self._serialize(instance, self._compiled_fields)
        return self._serialized

    def _serialize_list(self, instance: Any) -> list:
        self._serialized_many = [
            self._serialize(o, self._compiled_fields) for o in instance
        ]
        return self._serialized_many

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

    async def to_value(self, instance: Any) -> list | dict:
        if self.many:
            return await self._serialize_list(instance)
        return await self._serialize_dict(instance)

    async def _serialize_dict(self, instance: Any) -> dict:
        self._serialized = await self._serialize(instance, self._compiled_fields)
        return self._serialized

    async def _serialize_list(self, instance: Any) -> list:
        if isinstance(instance, AsyncIterable):
            self._serialized_many = [
                await self._serialize(o, self._compiled_fields) async for o in instance
            ]
        else:
            self._serialized_many = [
                await self._serialize(o, self._compiled_fields) for o in instance
            ]
        return self._serialized_many

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
