import unittest
from datetime import date, datetime

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

from .obj import Obj


class TestFields(unittest.TestCase):
    def test_to_value_noop(self):
        self.assertEqual(Field().to_value(5), 5)
        self.assertEqual(Field().to_value("a"), "a")
        self.assertEqual(Field().to_value(None), None)

    def test_as_getter_none(self):
        self.assertEqual(Field().as_getter(None, None), None)  # noqa

    def test_is_to_value_overridden(self):
        class TransField(Field):
            def to_value(self, value):
                return value

        field = Field()
        self.assertFalse(field.is_to_value_overridden())
        field = TransField()
        self.assertTrue(field.is_to_value_overridden())
        field = IntField()
        self.assertTrue(field.is_to_value_overridden())

    def test_str_field(self):
        field = StrField()
        self.assertEqual(field.to_value("a"), "a")
        self.assertEqual(field.to_value(5), "5")

    def test_str_field_none(self):
        field = StrField()
        self.assertIsNone(field.to_value(None))

    def test_bool_field(self):
        field = BoolField()
        self.assertTrue(field.to_value(True))
        self.assertFalse(field.to_value(False))
        self.assertTrue(field.to_value(1))
        self.assertFalse(field.to_value(0))

    def test_bool_field_none(self):
        field = BoolField()
        self.assertIsNone(field.to_value(None))

    def test_int_field(self):
        field = IntField()
        self.assertEqual(field.to_value(5), 5)
        self.assertEqual(field.to_value(5.4), 5)
        self.assertEqual(field.to_value("5"), 5)

    def test_int_field_none(self):
        field = IntField()
        # Ensure this raises an error if trying to serialize `None` as an `int`
        with self.assertRaises(TypeError):
            field.to_value(None)

    def test_float_field(self):
        field = FloatField()
        self.assertEqual(field.to_value(5.2), 5.2)
        self.assertEqual(field.to_value("5.5"), 5.5)

    def test_method_field(self):
        class FakeSerializer:
            def get_a(self, obj):
                return obj.a

            def z_sub_1(self, obj):
                return obj.z - 1

        serializer = FakeSerializer()

        fn = MethodField().as_getter("a", serializer)
        self.assertEqual(fn(Obj(a=3)), 3)

        fn = MethodField("z_sub_1").as_getter("a", serializer)
        self.assertEqual(fn(Obj(z=3)), 2)

        self.assertTrue(MethodField.getter_takes_serializer)

    def test_field_label(self):
        field1 = StrField(label="@id")
        self.assertEqual(field1.label, "@id")

    def test_static_field(self):
        field = StaticField("hello")
        self.assertEqual(field.to_value("ignored"), "hello")
        getter = field.as_getter("any", None)
        self.assertEqual(getter("ignored"), "hello")

    def test_date_field(self):
        field = DateField()
        self.assertEqual(field.to_value(date(2024, 1, 2)), "2024-01-02")
        self.assertIsNone(field.to_value(None))

    def test_date_field_custom_format(self):
        field = DateField("%d/%m/%Y")
        self.assertEqual(field.to_value(date(2024, 1, 2)), "02/01/2024")

    def test_datetime_field(self):
        field = DateTimeField()
        self.assertEqual(
            field.to_value(datetime(2024, 1, 2, 3, 4, 5)),
            "2024-01-02T03:04:05.000000Z",
        )
        self.assertIsNone(field.to_value(None))


if __name__ == "__main__":
    unittest.main()
