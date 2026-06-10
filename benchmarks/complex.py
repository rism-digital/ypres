import ypres
from benchmarks.utils import write_csv


class SubS(ypres.Serializer):
    w = ypres.IntField()
    x = ypres.MethodField()
    y = ypres.StrField()
    z = ypres.IntField()

    def get_x(self, obj):
        return obj.x + 10


class ComplexS(ypres.Serializer):
    foo = ypres.StrField()
    bar = ypres.IntField(call=True)
    sub = SubS()
    subs = SubS(many=True)


if __name__ == '__main__':
    data = {
        'foo': 'bar',
        'bar': lambda: 5,
        'sub': {
            'w': 1000,
            'x': 20,
            'y': 'hello',
            'z': 10
        },
        'subs': [{
            'w': 1000 * i,
            'x': 20 * i,
            'y': 'hello' * i,
            'z': 10 * i
        } for i in range(10)]
    }
    write_csv(__file__, data, ComplexS, 1)