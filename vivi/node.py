from collections.abc import Mapping
import weakref

from .html import SafeText, html_flatten, html_get, html_flatten_with_mapping


class Subscription:

    def __init__(self, node):
        self.ref = weakref.ref(node)

    def __hash__(self):
        return hash(id(self))

    def __call__(self, *args, **kwargs):
        return self.ref()._on_result(*args, **kwargs)


class Node(Mapping):

    def __init__(self, parents, node, queue=None, subscriptions=None):
        self._parents = parents
        self._node = node
        self._queue = queue
        self._subscriptions = subscriptions

        if subscriptions is not None:
            self._subscription = Subscription(self)
            subscriptions.add(self._subscription)
        else:
            self._subscription = None

    def _on_result(self, result):
        parents = []
        node = result

        old_parents = iter(self._parents)
        for prev_node, prev_index in old_parents:
            if node is prev_node:
                parents.append((prev_node, prev_index))
                parents.extend(old_parents)
                break

            _, nodes, index_mapping = (
                html_flatten_with_mapping(prev_node, node)
            )
            try:
                index = next(
                    index
                    for index, prev_index_ in index_mapping.items()
                    if prev_index_ == prev_index
                )
            except StopIteration:
                self._parents = tuple(old_parents)
                self._subscriptions.remove(self._subscription)
                self._subscriptions = None
                self._subscription = None
                self._queue = None
                return

            parents.append((node, index))
            node = nodes[index]

        self._parents = tuple(parents)
        self._node = node

    def __del__(self):
        if self._subscriptions is not None:
            self._subscriptions.remove(self._subscription)

    @classmethod
    def from_path(cls, result, path, *args, **kwargs):
        parents = []
        node = result
        for index in path:
            parents.append((node, index))
            node = html_get(node, index)
        return cls(parents, node, *args, **kwargs)

    @property
    def parent(self):
        try:
            *parents, (node, _) = self._parents
        except ValueError:
            raise ValueError('node has no parent') from None
        return Node(parents, node, self._subscriptions)

    @property
    def type(self):
        if isinstance(self._node, (str, SafeText)):
            return 'text'
        elif isinstance(self._node, tuple):
            if self._node[0] is None:
                return 'document'
            else:
                return 'element'
        else:
            raise ValueError('unknown node type')

    @property
    def tag(self):
        if self.type != 'element':
            raise ValueError('node is not an element')
        return self._node[0]

    def __getitem__(self, key):
        if self.type != 'element':
            raise ValueError('node is not an element')
        return self._node[1][key]

    def __iter__(self, key):
        if self.type != 'element':
            raise ValueError('node is not an element')
        return iter(self._node[1])

    def __len__(self, key):
        if self.type != 'element':
            raise ValueError('node is not an element')
        return len(self._node[1])

    def children(self):
        if self.type not in ('element', 'document'):
            raise ValueError('node is not an element')
        return (
            Node((*self._parents, (self._node, index)), node)
            for index, node in enumerate(html_flatten(
                (None, {}, {}, *self._node[3:])
            ))
        )

    @property
    def content(self):
        if self.type != 'text':
            raise ValueError('node is not text')
        return self._node

    def focus(self):
        if self.type != 'element':
            raise ValueError('node is not an element')
        if self._queue is None:
            raise ValueError('node is detached from the DOM')
        path = (index for _, index in self._parents)
        self._queue.put_nowait(('focus', *path))
