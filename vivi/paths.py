from collections.abc import MutableMapping


VALUE = object()


class Paths(MutableMapping):

    def __init__(self):
        self._data = {}

    def __getitem__(self, path):
        data = self._data
        for key in path:
            data = data[key]
        return data[VALUE]

    def __setitem__(self, path, value):
        data = self._data
        for key in path:
            data = data.setdefault(key, {})
        data[VALUE] = value

    def __delitem__(self, path):
        data = self._data
        parents = []
        for key in path:
            parents.append((data, key))
            data = data[key]
        del data[VALUE]
        while not data and parents:
            data, key = parents.pop()
            del data[key]

    def __iter__(self):
        todo = [(self._data, ())]
        while todo:
            data, path = todo.pop()
            for key, value in data.items():
                if key is VALUE:
                    yield path
                else:
                    todo.append((value, (*path, key)))

    def __len__(self):
        todo = [(self._data, ())]
        res = 0
        while todo:
            data, path = todo.pop()
            for key, value in data.items():
                if key is VALUE:
                    res += 1
                else:
                    todo.append((value, (*path, key)))
        return res

    def closest_parent(self, path):
        data = self._data

        if VALUE in data:
            res = 0
        else:
            res = None

        for index, key in enumerate(path):
            try:
                data = data[key]
            except KeyError:
                break
            else:
                if VALUE in data:
                    res = index + 1

        if res is None:
            raise KeyError

        return path[:res]

    def children(self, path, stop=set(), stop_at_value=False):
        data = self._data
        for key in path:
            try:
                data = data[key]
            except KeyError:
                return

        root = path
        todo = [(data, path)]
        while todo:
            data, path = todo.pop()

            if path is not root and VALUE in data:
                yield path
                if stop_at_value:
                    continue

            for key, value in data.items():
                if key is not VALUE:
                    subpath = (*path, key)
                    if subpath not in stop:
                        todo.append((value, subpath))

    def prune(self, path):
        data = self._data
        parents = []
        for key in path:
            parents.append((data, key))
            try:
                data = data[key]
            except KeyError:
                return
        data.clear()
        while not data and parents:
            data, key = parents.pop()
            del data[key]
