import asyncio
import unittest

from ypres.fields import Field, IntField, MethodField
from ypres.serializer import AsyncDictSerializer, AsyncSerializer

from .obj import Obj


class AsyncIntField(Field):
    async def to_value(self, value):
        await asyncio.sleep(0)
        return int(value)


class TestAsyncSerializer(unittest.IsolatedAsyncioTestCase):
    async def test_simple(self):
        class ASerializer(AsyncSerializer):
            a = Field()

        a = Obj(a=5)
        data = await ASerializer(a).serialized
        self.assertEqual(data["a"], 5)

    async def test_data_cached(self):
        class ASerializer(AsyncSerializer):
            a = Field()

        a = Obj(a=5)
        serializer = ASerializer(a)
        data1 = await serializer.serialized
        data2 = await serializer.serialized
        self.assertTrue(data1 is data2)

    async def test_many_list(self):
        class ASerializer(AsyncSerializer):
            a = Field()

        objs = [Obj(a=i) for i in range(5)]
        data = await ASerializer(objs, many=True).serialized_many
        self.assertEqual(len(data), 5)
        self.assertEqual(data[0]["a"], 0)
        self.assertEqual(data[4]["a"], 4)

    async def test_many_async_iterable(self):
        class ASerializer(AsyncSerializer):
            a = Field()

        async def gen():
            for i in range(3):
                yield Obj(a=i)

        data = await ASerializer(gen(), many=True).serialized_many
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]["a"], 0)
        self.assertEqual(data[2]["a"], 2)

    async def test_methodfield_async_getter(self):
        class ASerializer(AsyncSerializer):
            a = MethodField()

            async def get_a(self, obj):
                await asyncio.sleep(0)
                return obj.a + 5

        data = await ASerializer(Obj(a=2)).serialized
        self.assertEqual(data["a"], 7)

    async def test_toval_coro(self):
        class ASerializer(AsyncSerializer):
            a = AsyncIntField()

        data = await ASerializer(Obj(a="5")).serialized
        self.assertEqual(data["a"], 5)

    async def test_dict_serializer(self):
        class ASerializer(AsyncDictSerializer):
            a = IntField()
            b = Field(attr="foo")

        data = await ASerializer({"a": "2", "foo": "hello"}).serialized
        self.assertEqual(data["a"], 2)
        self.assertEqual(data["b"], "hello")

    async def test_data_property(self):
        class ASerializer(AsyncSerializer):
            a = Field()

        data = await ASerializer(Obj(a=11)).data
        self.assertEqual(data["a"], 11)

    async def test_data_property_many(self):
        class ASerializer(AsyncSerializer):
            a = Field()

        objs = [Obj(a=i) for i in range(3)]
        data = await ASerializer(objs, many=True).data
        self.assertEqual(len(data), 3)
        self.assertEqual(data[2]["a"], 2)


if __name__ == "__main__":
    unittest.main()
