import itertools
import unittest

from ypres.fields import BoolField, Field, FloatField, IntField, MethodField, StrField
from ypres.serializer import DictSerializer, Serializer

from .obj import Obj


class TestSerializer(unittest.TestCase):
    def test_simple(self):
        class ASerializer(Serializer):
            a = Field()

        a = Obj(a=5)
        self.assertEqual(ASerializer(a).serialized["a"], 5)

    def test_data_cached(self):
        class ASerializer(Serializer):
            a = Field()

        a = Obj(a=5)
        serializer = ASerializer(a)
        data1 = serializer.serialized
        data2 = serializer.serialized
        # Use assertTrue instead of assertIs for python 2.6.
        self.assertTrue(data1 is data2)

    def test_inheritance(self):
        class ASerializer(Serializer):
            a = Field()

        class CSerializer(Serializer):
            c = Field()

        class ABSerializer(ASerializer):
            b = Field()

        class ABCSerializer(ABSerializer, CSerializer):
            pass

        a = Obj(a=5, b="hello", c=100)
        self.assertEqual(ASerializer(a).serialized["a"], 5)
        data = ABSerializer(a).serialized
        self.assertEqual(data["a"], 5)
        self.assertEqual(data["b"], "hello")
        data = ABCSerializer(a).serialized
        self.assertEqual(data["a"], 5)
        self.assertEqual(data["b"], "hello")
        self.assertEqual(data["c"], 100)

    def test_many(self):
        class ASerializer(Serializer):
            a = Field()

        objs = [Obj(a=i) for i in range(5)]
        data = ASerializer(objs, many=True).serialized_many
        self.assertEqual(len(data), 5)
        self.assertEqual(data[0]["a"], 0)
        self.assertEqual(data[1]["a"], 1)
        self.assertEqual(data[2]["a"], 2)
        self.assertEqual(data[3]["a"], 3)
        self.assertEqual(data[4]["a"], 4)

    def test_serializer_as_field(self):
        class ASerializer(Serializer):
            a = Field()

        class BSerializer(Serializer):
            b = ASerializer()

        b = Obj(b=Obj(a=3))
        self.assertEqual(BSerializer(b).serialized["b"]["a"], 3)

    def test_serializer_as_field_many(self):
        class ASerializer(Serializer):
            a = Field()

        class BSerializer(Serializer):
            b = ASerializer(many=True)

        b = Obj(b=[Obj(a=i) for i in range(3)])
        b_data = BSerializer(b).serialized["b"]
        self.assertEqual(len(b_data), 3)
        self.assertEqual(b_data[0]["a"], 0)
        self.assertEqual(b_data[1]["a"], 1)
        self.assertEqual(b_data[2]["a"], 2)

    def test_serializer_as_field_call(self):
        class ASerializer(Serializer):
            a = Field()

        class BSerializer(Serializer):
            b = ASerializer(call=True)

        b = Obj(b=lambda: Obj(a=3))
        self.assertEqual(BSerializer(b).serialized["b"]["a"], 3)

    def test_serializer_method_field(self):
        class ASerializer(Serializer):
            a = MethodField()
            b = MethodField("add_9")

            def get_a(self, obj):
                return obj.a + 5

            def add_9(self, obj):
                return obj.a + 9

        a = Obj(a=2)
        data = ASerializer(a).serialized
        self.assertEqual(data["a"], 7)
        self.assertEqual(data["b"], 11)

    def test_to_value_called(self):
        class ASerializer(Serializer):
            a = IntField()
            b = FloatField(call=True)
            c = StrField(attr="foo.bar.baz")

        o = Obj(a="5", b=lambda: "6.2", foo=Obj(bar=Obj(baz=10)))
        data = ASerializer(o).serialized
        self.assertEqual(data["a"], 5)
        self.assertEqual(data["b"], 6.2)
        self.assertEqual(data["c"], "10")

    def test_dict_serializer(self):
        class ASerializer(DictSerializer):
            a = IntField()
            b = Field(attr="foo")

        d = {"a": "2", "foo": "hello"}
        data = ASerializer(d).serialized
        self.assertEqual(data["a"], 2)
        self.assertEqual(data["b"], "hello")

    def test_dotted_attr(self):
        class ASerializer(Serializer):
            a = Field("a.b.c")

        o = Obj(a=Obj(b=Obj(c=2)))
        data = ASerializer(o).serialized
        self.assertEqual(data["a"], 2)

    def test_custom_field(self):
        class Add5Field(Field):
            def to_value(self, value):
                return value + 5

        class ASerializer(Serializer):
            a = Add5Field()

        o = Obj(a=10)
        data = ASerializer(o).serialized
        self.assertEqual(data["a"], 15)

    def test_optional_intfield(self):
        class ASerializer(Serializer):
            a = IntField(required=False)

        o = Obj(a=None)
        data = ASerializer(o).serialized
        self.assertIsNone(data.get("a"))
        self.assertNotIn("a", data)

        o = Obj(a="5")
        data = ASerializer(o).serialized
        self.assertEqual(data["a"], 5)

        class ASerializer(Serializer):
            a = IntField()

        o = Obj(a=None)
        with self.assertRaises(TypeError):
            _ = ASerializer(o).serialized

    def test_optional_field_dictserializer(self):
        class ASerializer(DictSerializer):
            a = Field(required=False)

        data = ASerializer({"a": None}).serialized
        self.assertIsNone(data.get("a"))

        data = ASerializer({}).serialized
        self.assertNotIn("a", data)

        class ASerializer(DictSerializer):
            a = Field()

        data = ASerializer({"a": None}).serialized
        self.assertIsNone(data.get("a"))

        with self.assertRaises(KeyError):
            _ = ASerializer({}).serialized

    def test_optional_field(self):
        class ASerializer(Serializer):
            a = Field(required=False)

        o = Obj(a=None)
        data = ASerializer(o).serialized
        self.assertIsNone(data.get("a"))

        o = Obj()
        data = ASerializer(o).serialized
        self.assertNotIn("a", data)

        class ASerializer(Serializer):
            a = Field()

        o = Obj(a=None)
        data = ASerializer(o).serialized
        self.assertIsNone(data.get("a"))

        o = Obj()
        with self.assertRaises(AttributeError):
            _ = ASerializer(o).serialized

    def test_optional_methodfield(self):
        class ASerializer(Serializer):
            a = MethodField(required=False)

            def get_a(self, obj):
                return obj.a

        o = Obj(a=None)
        data = ASerializer(o).serialized
        self.assertIsNone(data.get("a"))
        self.assertNotIn("a", data)

        o = Obj(a="5")
        data = ASerializer(o).serialized
        self.assertEqual(data["a"], "5")

        class ASerializer(Serializer):
            a = MethodField()

            def get_a(self, obj):
                return obj.a

        o = Obj(a=None)
        data = ASerializer(o).serialized
        self.assertIsNone(data.get("a"))

    def test_error_on_data(self):
        with self.assertRaises(TypeError):
            Serializer(data="foo")

    def test_serializer_with_custom_output_label(self):
        class ASerializer(Serializer):
            context = StrField(label="@context")
            content = MethodField(label="@content")

            def get_content(self, obj):
                return obj.content

        o = Obj(context="http://foo/bar/baz/", content="http://baz/bar/foo/")
        data = ASerializer(o).serialized

        self.assertIn("@context", data)
        self.assertEqual(data["@context"], "http://foo/bar/baz/")
        self.assertIn("@content", data)
        self.assertEqual(data["@content"], "http://baz/bar/foo/")

    def test_emit_none_true_required_true_serializer(self):
        class FooSerializer(Serializer):
            foo = StrField(emit_none=True)

        o = Obj(foo="blah")
        data = FooSerializer(o).serialized
        self.assertIn("foo", data)

        # This should raise because it doesn't have a "foo" field
        o2 = Obj(bar="blah")
        with self.assertRaises(AttributeError):
            _ = FooSerializer(o2).serialized

    def test_emit_none_false_required_true_serializer(self):
        class FooSerializer(Serializer):
            foo = StrField(required=False)

        # This should not raise an error because 'foo' is not required. "bar" will
        # be ignored since we don't have a serializer field for it.
        o = Obj(bar="blah")
        data = FooSerializer(o).serialized
        self.assertNotIn("bar", data)

    def test_emit_none_true_required_false_serializer(self):
        class FooSerializer(Serializer):
            foo = StrField(emit_none=True, required=False)
            bar = StrField(emit_none=True, required=False)
            baz = BoolField(emit_none=True, required=False)
            gab = IntField(emit_none=True, required=False)

        o = Obj(foo="blah", bar=None, baz=None, gab=None)
        data = FooSerializer(o).serialized
        self.assertIn("foo", data)
        self.assertIsNotNone(data["foo"])
        self.assertIn("bar", data)
        self.assertIsNone(data["bar"])
        self.assertIn("baz", data)
        self.assertIsNone(data["baz"])
        self.assertIn("gab", data)
        self.assertIsNone(data["gab"])

    def test_serializing_int_and_none(self):
        class FooSerializer(Serializer):
            foo = IntField(emit_none=True)

        o = Obj(foo=None)
        # ensure this works as expected
        with self.assertRaises(TypeError):
            _ = FooSerializer(o).serialized

    def test_many_iterable(self):
        class ASerializer(Serializer):
            a = Field()

        objs1 = [Obj(a=i) for i in range(5)]
        objs2 = [Obj(a=i) for i in range(7, 10)]
        objs = itertools.chain(objs1, objs2)
        data = ASerializer(objs, many=True).serialized_many
        self.assertEqual(len(data), 8)
        self.assertEqual(data[0]["a"], 0)
        self.assertEqual(data[1]["a"], 1)
        self.assertEqual(data[2]["a"], 2)
        self.assertEqual(data[3]["a"], 3)
        self.assertEqual(data[4]["a"], 4)

    def test_many_dict_raises_valueerror(self):
        class ASerializer(Serializer):
            a = Field()

        class BSerializer(DictSerializer):
            b = Field()

        o = Obj(foo=None)
        m = {"bar": None}

        with self.assertRaises(ValueError):
            _ = ASerializer(o, many=True)

        with self.assertRaises(ValueError):
            _ = BSerializer(m, many=True)


if __name__ == "__main__":
    unittest.main()
