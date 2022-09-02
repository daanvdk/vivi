import asyncio
from collections import defaultdict, deque
import html
from itertools import islice
import json

from .events import CallbackWrapper


class SafeText:

    __slots__ = ['text']

    def __init__(self, text):
        self.text = text

    def __bool__(self):
        return bool(self.text)

    def __eq__(self, other):
        if isinstance(other, SafeText):
            return other.text == self.text
        elif isinstance(other, str):
            return html.escape(other, quote=False) == self.text
        else:
            return False

    def __hash__(self):
        return hash((SafeText, self.text))

    @classmethod
    def join(cls, parts):
        checked_parts = []
        safe = False

        for part in parts:
            if isinstance(part, cls):
                if not safe:
                    parts = [html.escape(part) for part in parts]
                    safe = True
                checked_parts.append(part.text)
            elif safe:
                checked_parts.append(html.escape(part))
            else:
                checked_parts.append(part)

        joined = ''.join(checked_parts)
        if safe:
            joined = cls(joined)
        return joined


def clean_value(value):
    if not callable(value):
        return value

    args = {
        'prevent_default': False,
        'stop_propagation': False,
    }

    while isinstance(value, CallbackWrapper):
        args[value.key] = value.value
        value = value.callback

    parts = ['call(event']
    for arg in [
        'prevent_default',
        'stop_propagation',
    ]:
        parts.append(', ')
        parts.append(json.dumps(args[arg]))
    parts.append(')')
    return ''.join(parts)


def clean_node(node):
    if not isinstance(node, tuple):
        return node

    tag, props, _, *children = node

    cleaned_props = {}
    for key, value in props.items():
        if key == 'ref':
            continue

        value = clean_value(value)
        if value is False:
            continue
        if value is True:
            value = ''
        if not isinstance(value, str):
            value = json.dumps(value)
        cleaned_props[key] = value

    return (
        tag, cleaned_props,
        *map(clean_node, html_flatten((None, {}, {}, *children))),
    )


def html_flatten(node):
    if not isinstance(node, tuple) or node[0] is not None:
        if node is None:
            return {}
        yield node
        return {(): 0}

    stack = [(enumerate(islice(node, 3, None)), ())]
    flat_index = 0
    path_indexes = {}

    while stack:
        nodes, path = stack[-1]
        try:
            index, node = next(nodes)
        except StopIteration:
            stack.pop()
            continue

        if isinstance(node, tuple) and node[0] is None:
            stack.append((enumerate(islice(node, 3, None)), (*path, index)))
            continue

        if isinstance(node, (str, SafeText)):
            while stack:
                nodes, path = stack[-1]
                try:
                    index, next_node = next(nodes)
                except StopIteration:
                    stack.pop()
                    continue

                if isinstance(next_node, tuple) and next_node[0] is None:
                    stack.append((
                        enumerate(islice(next_node, 3, None)),
                        (*path, index),
                    ))
                    continue

                if isinstance(next_node, str):
                    if isinstance(node, str):
                        node += next_node
                    else:
                        node = SafeText(
                            node.text +
                            html.escape(next_node, quote=False)
                        )
                elif isinstance(next_node, SafeText):
                    if isinstance(node, str):
                        node = SafeText(
                            html.escape(node, quote=False) +
                            next_node.text
                        )
                    else:
                        node = SafeText(node.text + next_node.text)
                else:
                    if node:
                        yield node
                        flat_index += 1
                    node = next_node
                    break

        if node is not None:
            yield node
            if not isinstance(node, (str, SafeText)):
                path_indexes[(*path, index)] = flat_index
            flat_index += 1

    return path_indexes


def html_get(node, index):
    if node[0] is not None:
        node = (None, {}, {}, *node[3:])
    try:
        return next(islice(html_flatten(node), index, None))
    except StopIteration:
        raise IndexError('node index out of range') from None


def html_parts(node):
    for node in html_flatten(node):
        if isinstance(node, SafeText):
            yield node.text
            continue

        if isinstance(node, str):
            yield html.escape(node, quote=False)
            continue

        tag, props, _, *children = node

        yield '<'
        yield tag
        for key, value in props.items():
            if key == 'ref':
                continue

            value = clean_value(value)
            if value is False:
                continue
            yield ' '
            yield key
            if value is True:
                continue
            yield '="'
            if not isinstance(value, str):
                value = json.dumps(value)
            yield html.escape(value)
            yield '"'
        yield '>'

        yield from html_parts((None, {}, {}, *children))

        yield '</'
        yield tag
        yield '>'


def html_flatten_with_mapping(old_node, new_node):
    old_nodes_iter = html_flatten(old_node)
    old_nodes = []
    while True:
        try:
            old_nodes.append(next(old_nodes_iter))
        except StopIteration as e:
            old_path_indexes = e.value
            break

    new_nodes_iter = html_flatten(new_node)
    new_nodes = []
    while True:
        try:
            new_nodes.append(next(new_nodes_iter))
        except StopIteration as e:
            new_path_indexes = e.value
            break

    index_mapping = {}
    for new_path, new_index in new_path_indexes.items():
        node = new_node
        old_path = []
        for index in new_path:
            try:
                old_index = node[2][index]
            except KeyError:
                break
            node = node[index + 3]
            old_path.append(old_index)
        else:
            try:
                old_index = old_path_indexes[tuple(old_path)]
            except KeyError:
                pass
            else:
                index_mapping[new_index] = old_index

    return old_nodes, new_nodes, index_mapping


def html_diff(old_node, new_node, path=()):
    old_nodes, new_nodes, index_mapping = (
        html_flatten_with_mapping(old_node, new_node)
    )

    old_str_indexes = defaultdict(deque)

    for old_index, node in enumerate(old_nodes):
        if isinstance(node, (str, SafeText)):
            old_str_indexes[node].append(old_index)

    for new_index, node in enumerate(new_nodes):
        if isinstance(node, (str, SafeText)):
            try:
                old_index = old_str_indexes[node].popleft()
            except IndexError:
                pass
            else:
                index_mapping[new_index] = old_index

    rev_index_mapping = {value: key for key, value in index_mapping.items()}

    inserts = deque()
    removes = 0
    waiting = {}
    index = 0
    old_index = 0

    for new_index, new_node in enumerate(new_nodes):
        if new_index not in index_mapping:
            inserts.append(new_node)
            continue

        try:
            curr_index = waiting.pop(new_index)
        except KeyError:
            target_old_index = index_mapping[new_index]
            while old_index < target_old_index:
                try:
                    new_index_ = rev_index_mapping[old_index]
                except KeyError:
                    removes += 1
                else:
                    waiting[new_index] = index
                    index += 1
                old_index += 1
        else:
            index -= 1
            yield ('move', *path, curr_index, index)
            for new_index_, curr_index_ in waiting.items():
                if curr_index < curr_index_:
                    waiting[new_index_] = curr_index_ - 1

        while inserts:
            if removes:
                action = 'replace'
                removes -= 1
            else:
                action = 'insert'
            yield (action, *path, index, clean_node(inserts.popleft()))
            index += 1

        while removes:
            yield ('remove', *path, index)
            removes -= 1

        old_node = old_nodes[old_index]

        if old_node is new_node:
            pass
        elif isinstance(old_node, tuple) and isinstance(new_node, tuple):
            _, old_props, old_mapping, *old_children = old_node
            _, new_props, new_mapping, *new_children = new_node

            for key in set(old_props) - set(new_props):
                yield ('unset', *path, index, key)

            for key, value in new_props.items():
                value = clean_value(value)
                if (
                    key not in old_props or
                    clean_value(old_props[key]) != value
                ):
                    if value is False:
                        yield ('unset', *path, index, key)
                        continue
                    if value is True:
                        value = ''
                    yield ('set', *path, index, key, value)

            yield from html_diff(
                (None, {}, old_mapping, *old_children),
                (None, {}, new_mapping, *new_children),
                (*path, index),
            )
        elif old_node != new_node:
            yield ('replace', *path, index, clean_node(new_node))

        old_index += 1
        index += 1

    removes += len(old_nodes) - old_index

    while inserts:
        if removes:
            action = 'replace'
            removes -= 1
        else:
            action = 'insert'
        yield (action, *path, index, clean_node(inserts.popleft()))
        index += 1

    while removes:
        yield ('remove', *path, index)
        removes -= 1


def html_refs(old_node, new_node, queue, subscriptions, path=(), root=None):
    loop = asyncio.get_running_loop()

    if new_node is old_node:
        return

    if root is None:
        root = new_node

    old_nodes, new_nodes, index_mapping = (
        html_flatten_with_mapping(old_node, new_node)
    )

    mapped_old_nodes = set(index_mapping.values())

    for old_index, old_node in enumerate(old_nodes):
        if old_index in mapped_old_nodes:
            continue

        if not isinstance(old_node, tuple):
            continue

        try:
            ref = old_node[1]['ref']
        except KeyError:
            pass
        else:
            loop.call_soon(ref, None)

    for new_index, new_node in enumerate(new_nodes):
        if not isinstance(new_node, tuple):
            continue

        try:
            old_index = index_mapping[new_index]
        except KeyError:
            old_node = None
        else:
            old_node = old_nodes[old_index]

        if new_node is not old_node:
            new_path = (*path, new_index)

            if old_node is None:
                try:
                    ref = new_node[1]['ref']
                except KeyError:
                    pass
                else:
                    from .node import Node
                    node = Node.from_path(root, new_path, queue, subscriptions)
                    loop.call_soon(ref, node)

            if isinstance(old_node, tuple):
                old_node = (None, {}, *old_node[2:])
            new_node = (None, {}, *new_node[2:])
            html_refs(
                old_node, new_node,
                queue, subscriptions, new_path, root,
            )
