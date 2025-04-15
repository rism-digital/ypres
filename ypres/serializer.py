import inspect
import operator
from abc import abstractmethod
from collections.abc import Callable, Mapping
from typing import Any, NamedTuple

from ypres.fields import Field


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
    @staticmethod
    @abstractmethod
    def default_getter(k: str) -> Any: ...

    _field_map: dict = {}
    _compiled_fields: list[FieldDefinitions] = []


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


class Serializer(SerializerBase, metaclass=SerializerMeta):
    """:class:`Serializer` is used as a base for custom serializers.

    The :class:`Serializer` class is also a subclass of :class:`Field`, and can
    be used as a :class:`Field` to create nested schemas. A serializer is
    defined by subclassing :class:`Serializer` and adding each :class:`Field`
    as a class variable:

    Example: ::

        class FooSerializer(Serializer):
            foo = Field()
            bar = Field()

        foo = Foo(foo='hello', bar=5)
        res = FooSerializer(foo).data
        # {'foo': 'hello', 'bar': 5}

    :param instance: The object or objects to serialize.
    :param bool many: If ``instance`` is a collection of objects, set ``many``
        to ``True`` to serialize to a list.
    :param data: Provided for compatibility with DRF serializers. Should not
        be used.
    :param dict context: A context dictionary for additional parameters to be
        passed into the serializer instance.
    """

    #: The default getter used if :meth:`Field.as_getter` returns None.
    default_getter: Any = operator.attrgetter

    def __init__(
        self,  # type: ignore
        instance: Any | None = None,
        many: bool = False,
        context: dict | None = None,
        emit_none: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.instance: Any = instance
        self.many: bool = many
        self.context: dict = context or {}
        self._emit_none = emit_none
        self._data: list | dict | None = None

    def _serialize(self, instance: Any, fields: list[FieldDefinitions]) -> dict:
        v: dict = {}

        for (
            name,
            getter,
            to_value,
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

            if to_value:
                result = to_value(result)

            # If `None` values should not appear in the output,
            # and we have a result that is None, we just skip
            # it and continue to the next field.
            if result is None and not emit_none:
                continue

            v[name] = result

        return v

    def to_value(self, instance) -> list | dict:
        fields: list[FieldDefinitions] = self._compiled_fields
        if self.many:
            serialize = self._serialize
            return [serialize(o, fields) for o in instance]
        return self._serialize(instance, fields)

    @property
    def data(self) -> list | dict:
        """Get the serialized data from the :class:`Serializer`.

        The data will be cached for future accesses.
        """
        # Cache the data for next time .data is called.
        if self._data is None:
            self._data = self.to_value(self.instance)
        return self._data


class DictSerializer(Serializer):
    """:class:`DictSerializer` serializes python ``dicts`` instead of objects.

    Instead of the serializer's fields fetching data using
    ``operator.attrgetter``, :class:`DictSerializer` uses
    ``operator.itemgetter``.

    Example: ::

        class FooSerializer(DictSerializer):
            foo = IntField()
            bar = FloatField()

        foo = {'foo': '5', 'bar': '2.2'}
        res = FooSerializer(foo).data
        # {'foo': 5, 'bar': 2.2}
    """

    default_getter: Any = operator.itemgetter


class AsyncSerializer(SerializerBase, metaclass=SerializerMeta):
    """:class:`Serializer` is used as a base for custom serializers, but that
    can support asynchronous methods in the :class:`MethodField` instances,
    or from objects with asynchronous accessors.

    Non-async method fields are also supported on the same serializer.

    Example: ::

        class FooSerializer(AsyncSerializer):
            foo = MethodField()
            bar = MethodField()

            async def get_foo(self, obj):
                return await my_async_foo_data(obj)

            def get_bar(self, obj):
                return my_bar_data(obj)

        out_data = await FooSerializer(in_data).data

    """

    #: The default getter used if :meth:`Field.as_getter` returns None.
    default_getter: Any = operator.attrgetter

    def __init__(
        self,  # type: ignore
        instance: Any | None = None,
        many: bool = False,
        context: dict | None = None,
        emit_none: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.instance: Any | None = instance
        self.many: bool = many
        self.context: dict = context or {}
        self._emit_none = emit_none
        self._data: list | dict | None = None

    async def _serialize(self, instance: Any, fields: list[FieldDefinitions]) -> dict:
        v: dict = {}
        for (
            name,
            getter,
            to_value,
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

            if to_value:
                if toval_coro:
                    result = await to_value(result)
                else:
                    result = to_value(result)

            if result is None and not emit_none:
                continue

            v[name] = result

        return v

    async def to_value(self, instance: Any) -> list | dict:
        fields: list[FieldDefinitions] = self._compiled_fields
        if self.many:
            serialize = self._serialize
            return [await serialize(o, fields) async for o in instance]
        return await self._serialize(instance, fields)

    @property
    async def data(self) -> list | dict:
        """Get the serialized data from the :class:`Serializer`.

        The data will be cached for future accesses.
        """
        # Cache the data for next time .data is called.
        if self._data is None:
            self._data = await self.to_value(self.instance)
        return self._data


class AsyncDictSerializer(AsyncSerializer):
    """:class:`DictSerializer` serializes python ``dicts`` instead of objects.
    Supports asynchronous :class:`MethodField` contents.

    Example: ::

        class FooSerializer(Async DictSerializer):
            foo = IntField()
            bar = FloatField()

        foo = {'foo': '5', 'bar': '2.2'}
        res = await FooSerializer(foo).data
        # {'foo': 5, 'bar': 2.2}
    """

    default_getter: Any = operator.itemgetter
