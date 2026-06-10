import time


class Obj:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if isinstance(v, dict):
                v = Obj(**v)
            if isinstance(v, list):
                v = [Obj(**attrs) for attrs in v]
            setattr(self, k, v)


def write_csv(name, data, ypres, size):
    repetitions = 1000
    with open(f"{name}.csv", "w+") as f:
        f.write("repetitions,time\n")
        for i in range(10 * size, 101 * size, 10 * size):
            f.write(str(i * repetitions))
            for serializer in (ypres,):
                f.write(",")
                f.write(str(benchmark(serializer, repetitions, i, data=data)))
            f.write("\n")


def benchmark(serializer_fn, repetitions, num_objs=1, data=None):
    total_objs = repetitions * num_objs
    library = "ypres"
    print(f"Serializing {total_objs} objects using {library}")

    if data is None:
        data = {}

    objs = [Obj(**data) for i in range(num_objs)]
    many = num_objs > 1
    if not many:
        objs = objs[0]

    t1 = time.time()
    for _ in range(repetitions):
        if many:
            _ = serializer_fn(objs, many=many).serialized_many
        else:
            _ = serializer_fn(objs, many=many).serialized

    total_time = time.time() - t1
    print(f"Total time: {total_time}")
    print(f"Objs/s    : {int(total_objs / total_time)}\n")
    return total_time
