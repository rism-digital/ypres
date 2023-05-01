import inspect
import operator
from typing import Callable, Optional, Union, Any, Mapping

from ypres.fields import Field


class SerializerBase(Field):
    _field_map: dict = {}
    _compiled_fields: tuple = ()


def _compile_field_to_tuple(field: Field, name: str, serializer_cls: Any) -> tuple:
    getter = field.as_getter(name, serializer_cls)
    if getter is None:
        getter = serializer_cls.default_getter(field.attr or name)

    # Only set a to_value function if it has been overridden for performance.
    to_value: Optional[Callable] = None
    if field.is_to_value_overridden():
        to_value = field.to_value

    # Set the field name to a supplied label; defaults to the attribute name.
    name = field.label or name

    return (name, getter, to_value, field.call, field.required,
            field.getter_takes_serializer)


class SerializerMeta(type):

    @staticmethod
    def _get_fields(direct_fields: Mapping, serializer_cls: Any) -> dict:
        field_map: dict = {}
        # Get all the fields from base classes.
        for cls in serializer_cls.__mro__[::-1]:
            if issubclass(cls, SerializerBase):
                field_map.update(cls._field_map)
        field_map.update(direct_fields)
        return field_map

    @staticmethod
    def _compile_fields(field_map: dict, serializer_cls: Any) -> list[tuple]:
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
        for k in direct_fields.keys():
            del attrs[k]

        real_cls = super(SerializerMeta, mcs).__new__(mcs, name, bases, attrs)

        field_map = mcs._get_fields(direct_fields, real_cls)
        compiled_fields = mcs._compile_fields(field_map, real_cls)

        real_cls._field_map = field_map  # type: ignore
        real_cls._compiled_fields = tuple(compiled_fields)  # type: ignore

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
        FooSerializer(foo).data
        # {'foo': 'hello', 'bar': 5}

    :param instance: The object or objects to serialize.
    :param bool many: If ``instance`` is a collection of objects, set ``many``
        to ``True`` to serialize to a list.
    :param data: Provided for compatibility with DRF serializers. Should not be used.
    :param dict context: A context dictionary for additional parameters to be passed into
        the serializer instance.
    """
    #: The default getter used if :meth:`Field.as_getter` returns None.
    default_getter: Any = operator.attrgetter

    def __init__(self,  # type: ignore
                 instance: Optional[Any] = None,
                 many: bool = False,
                 context: Optional[dict] = None,
                 **kwargs):

        super(Serializer, self).__init__(**kwargs)
        self.instance: Any = instance
        self.many: bool = many
        self.context = context
        self._data: Optional[Union[list, dict]] = None

    def _serialize(self, instance: Any, fields: tuple) -> dict:
        v: dict = {}
        for name, getter, to_value, call, required, pass_self in fields:
            if pass_self:
                result = getter(self, instance)
            else:
                try:
                    result = getter(instance)
                except (KeyError, AttributeError):
                    if required:
                        raise
                    else:
                        continue

                if required or result is not None:
                    if call:
                        result = result()
                    if to_value:
                        result = to_value(result)

            if result is not None:
                v[name] = result

        return v

    def to_value(self, instance) -> Union[list, dict]:
        fields: tuple = self._compiled_fields
        if self.many:
            serialize = self._serialize
            return [serialize(o, fields) for o in instance]
        return self._serialize(instance, fields)

    @property
    def data(self) -> Union[list, dict]:
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
        FooSerializer(foo).data
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

    def __init__(self,  # type: ignore
                 instance: Optional[Any] = None,
                 many: bool = False,
                 context: Optional[dict] = None,
                 **kwargs):

        super(AsyncSerializer, self).__init__(**kwargs)
        self.instance: Optional[Any] = instance
        self.many: bool = many
        self.context: Optional[dict] = context
        self._data: Optional[Union[list, dict]] = None

    async def _serialize(self, instance: Any, fields: tuple) -> dict:
        v: dict = {}
        for name, getter, to_value, call, required, pass_self in fields:
            if pass_self:
                # checks to see if the incoming method is a coroutine
                if inspect.iscoroutinefunction(getter):
                    result = await getter(self, instance)
                else:
                    result = getter(self, instance)
            else:
                try:
                    result = getter(instance)
                except (KeyError, AttributeError):
                    if required:
                        raise
                    else:
                        continue

                if required or result is not None:
                    if call:
                        result = result()
                    if to_value:
                        if inspect.iscoroutinefunction(to_value):
                            result = await to_value(result)
                        else:
                            result = to_value(result)

            if result is not None:
                v[name] = result

        return v

    async def to_value(self, instance: Any) -> Union[list, dict]:
        fields: tuple = self._compiled_fields
        if self.many:
            serialize = self._serialize
            return [await serialize(o, fields) async for o in instance]
        return await self._serialize(instance, fields)

    @property
    async def data(self) -> Union[list, dict]:
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
        FooSerializer(foo).data
        # {'foo': 5, 'bar': 2.2}
    """
    default_getter: Any = operator.itemgetter
