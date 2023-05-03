# ypres: ridiculously fast object serialization

This is a fork of the amazing [Serpy
serializer](https://github.com/clarkduvall/serpy), which has been
[marked as feature-complete](https://github.com/clarkduvall/serpy/issues/69) 
by the original author. This fork adds some newer features, such as
`asyncio` support so that asynchronous methods may be called from 
within a serializer.

It was renamed to "ypres" ("serpy" backwards, pronounced like the [Belgian town
name](https://en.wikipedia.org/wiki/Ypres)) to avoid confusion with the
original.

**ypres** is a simple object serialization framework built for
speed. **ypres** serializes complex datatypes (Django Models, custom
classes, ...) to simple native types (dicts, lists, strings, ...). The
native types can easily be converted to JSON or any other format needed.

The goal of **ypres** is to be able to do this *simply*, *reliably*, and
*quickly*. Since serializers are class based, they can be combined,
extended and customized with very little code duplication.

## Changes from Serpy

There are some notable changes from the original Serpy serializer in this fork.

### New Serializer classes: AsyncSerializer and AsyncDictSerializer

Serpy did not allow for `MethodField` implementations to use async / await methods.
For those instances where you wish to embed an async / await coroutine in your serializer,
two new serializer classes, `AsyncSerializer` and `AsyncDictSerializer`, will automatically 
detect whether the method being called is a coroutine and handle it appropriately.

### New StaticField class

When combining many fields and manipulating output, it is sometimes desirable to have
a fixed value for certain fields in the output. The new `StaticField` class allows
you to specify a fixed value for the field, and this will always appear in the output.

### Serializers allow a context object

Additional context can be passed in to a serializer. This is helpful if you have some context
that you wish to use when serializing the object. For example, you might pass in a user object
that could customize the responses in the serializer with their name, or only perform certain
serialization tasks if they are of a specific class (e.g., admin).

```python
import ypres


class MySerializer(ypres.Serializer):
    foo = ypres.MethodField()
    blah = ypres.MethodField()
    
    def get_foo(self, obj):
        foo_data = obj.foo
        ctx_data = self.context.get("additional", "")
        return f"{foo_data}_{ctx_data}"
    
    def get_blah(self, obj):
        blah_data = obj.blah
        ctx_data = self.context.get("additional", "")
        return f"{blah_data}_{ctx_data}"
    
    
class Foo:
    foo = "foo"
    blah = "blah"

my_data = MySerializer(Foo(), context={"additional": "bar"})

# {"foo": "foo_bar", "blah": "blah_bar"}
```

### Changed behaviour of None

By default, data that evaluates to a value of `None` will **not** be included
in the output. To explicitly mark that a field should emit a `None` value, 
it should be instantiated with an `emit_none=True` argument.

Note that the combination of `emit_none` and `required` deserve special attention.

 - If `emit_none` is `False` and `required` is `True` (default), then the object
being serialized must have the matching attribute available, otherwise it will
raise an error. The only exception is if the field is a `MethodField`, in which 
case the attribute does not need to be present on the object. 
This behaviour is not changed.
 - If `emit_none` is `False` and `required` is `False` then the object being
serialized will not appear in the output if its value is `None`
 - If `emit_none` is `True` and `required` is `True`, then the object being
serialized will attempt to return the value. However, it may fail if the `to_value`
method being used does not accept `None`. An example of this is the `IntField`
serializer, where the `to_value` method would effectively be calling `int(None)`.
In this case, a `TypeError` will be raised. (This is the same as trying to serialize
a string with an `IntField`, for example)
 - If `emit_none` is `True` and `required` is `False`, then the object being
serialized will actually skip the `to_value` step and simply return `None`. 

Further to this, the behaviour of the `StrField` and `BoolField` were changed,
where calling `StrField` on a value of `None` would actually return the string
`"None"`. Similarly, calling `bool(None)` evaluates to `False`. In both of these
cases the `to_value` handler has been modified to return `None` if the incoming
value is `None`. 

This prevents unexpected type values from appearing in the 
output. For values that cannot be cast to `None` for `IntField` and `FloatField`,
a `None` input will raise an exception.

## Source

Source at: <https://github.com/rism-digital/ypres>

If you want a feature, send a pull request!

## Documentation

Full documentation at: <http://ypres.readthedocs.org/en/latest/>

## Installation

``` bash
$ pip install ypres
```

## Examples

### Simple Example

```python
import ypres

class Foo(object):
    """The object to be serialized."""
    y = 'hello'
    z = 9.5

    def __init__(self, x):
        self.x = x


class FooSerializer(ypres.Serializer):
    """The serializer schema definition."""
    # Use a Field subclass like IntField if you need more validation.
    x = serpy.IntField()
    y = serpy.Field()
    z = serpy.Field()

f = Foo(1)
FooSerializer(f).data
# {'x': 1, 'y': 'hello', 'z': 9.5}

fs = [Foo(i) for i in range(100)]
FooSerializer(fs, many=True).data
# [{'x': 0, 'y': 'hello', 'z': 9.5}, {'x': 1, 'y': 'hello', 'z': 9.5}, ...]
```

### Nested Example

```python
import ypres

class Nestee(object):
    """An object nested inside another object."""
    n = 'hi'


class Foo(object):
    x = 1
    nested = Nestee()


class NesteeSerializer(ypres.Serializer):
    n = serpy.Field()


class FooSerializer(ypres.Serializer):
    x = serpy.Field()
    # Use another serializer as a field.
    nested = NesteeSerializer()

f = Foo()
FooSerializer(f).data
# {'x': 1, 'nested': {'n': 'hi'}}
```

### Complex Example

```python
import ypres

class Foo(object):
    y = 1
    z = 2
    super_long_thing = 10

    def x(self):
        return 5


class FooSerializer(ypres.Serializer):
    w = ypres.Field(attr='super_long_thing')
    x = ypres.Field(call=True)
    plus = ypres.MethodField()

    def get_plus(self, obj):
        return obj.y + obj.z

f = Foo()
FooSerializer(f).data
# {'w': 10, 'x': 5, 'plus': 3}
```

### Inheritance Example

```python
import ypres

class Foo(object):
    a = 1
    b = 2


class ASerializer(ypres.Serializer):
    a = ypres.Field()


class ABSerializer(ASerializer):
    """ABSerializer inherits the 'a' field from ASerializer.

    This also works with multiple inheritance and mixins.
    """
    b = ypres.Field()

f = Foo()
ASerializer(f).data
# {'a': 1}
ABSerializer(f).data
# {'a': 1, 'b': 2}
```

## License

ypres is free software distributed under the terms of the MIT license.
See the [LICENSE](https://github.com/clarkduvall/serpy/blob/master/LICENSE)
file.