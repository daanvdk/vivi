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


def clean_value(value):
    if not callable(value):
        return value

    args = {
        'prevent_default': False,
        'stop_propagation': False,
        'stop_immediate_propagation': False,
    }

    while isinstance(value, CallbackWrapper):
        args[value.key] = value.value
        value = value.callback

    parts = ['call(event']
    for arg in [
        'prevent_default',
        'stop_propagation',
        'stop_immediate_propagation',
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
        value = clean_value(value)
        if value is False:
            continue
        if value is True:
            value = ''
        if not isinstance(value, str):
            value = json.dumps(value)
        cleaned_props[key] = value

    cleaned_children = []
    stack = [iter(children)]
    while stack:
        try:
            child = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue

        if isinstance(child, tuple) and child[0] is None:
            stack.append(islice(child, 3, None))
            continue

        if child is None:
            continue

        child = clean_node(child)
        if (
            cleaned_children and
            isinstance(child, str) and
            isinstance(cleaned_children[-1], str)
        ):
            cleaned_children[-1] += child
        else:
            cleaned_children.append(child)

    return (tag, cleaned_props, *cleaned_children)


def node_flatten(node):
    if not isinstance(node, tuple) or node[0] is not None:
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


def node_get(node, path):
    for index in path:
        if node[0] is not None:
            node = (None, {}, {}, *node[3:])
        node = next(islice(node_flatten(node), index, None))
    return node


def node_parts(node):
    if isinstance(node, SafeText):
        yield node.text
        return

    if isinstance(node, str):
        yield html.escape(node, quote=False)
        return

    if node is None:
        return

    tag, props, _, *children = node

    if tag is not None:
        yield '<'
        yield tag
        for key, value in props.items():
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

    for child in children:
        yield from node_parts(child)

    if tag is not None:
        yield '</'
        yield tag
        yield '>'


def node_diff(old_node, new_node, path=()):
    old_nodes_iter = node_flatten(old_node)
    old_nodes = []
    while True:
        try:
            old_nodes.append(next(old_nodes_iter))
        except StopIteration as e:
            old_path_indexes = e.value
            break

    new_nodes_iter = node_flatten(new_node)
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

    rev_index_mapping = {v: k for k, v in index_mapping.items()}

    # Remove old nodes
    to_remove = set()
    for old_index in old_path_indexes.values():
        try:
            new_index = rev_index_mapping[old_index]
        except KeyError:
            to_remove.add(old_index)
        else:
            old_node = old_nodes[old_index]
            new_node = new_nodes[new_index]
            if old_node[0] != new_node[0]:
                to_remove.add(old_index)
                del index_mapping[new_index]
                del rev_index_mapping[old_index]

    # Make sure nodes are in the correct order
    old_indexes = sorted(rev_index_mapping)
    for i in range(0, len(old_indexes) - 1):
        j = min(
            range(i, len(old_indexes)),
            key=lambda i: rev_index_mapping[old_indexes[i]],
        )
        if j != i:
            a_old = old_indexes[i]
            a_new = rev_index_mapping[a_old]
            b_old = old_indexes[j]
            b_new = rev_index_mapping[b_old]

            index_mapping[a_new] = b_old
            rev_index_mapping[b_old] = a_new

            index_mapping[b_new] = a_old
            rev_index_mapping[a_old] = b_new

            old_nodes[a_old], old_nodes[b_old] = (
                old_nodes[b_old], old_nodes[a_old]
            )

    # Divide in sections based on the known same nodes
    splits = [
        (0, 0),
        *(
            (old_index, rev_index_mapping[old_index])
            for old_index in old_indexes
        ),
        (len(old_nodes), len(new_nodes)),
    ]
    index = 0
    removes = 0

    for (old_start, new_start), (old_end, new_end) in zip(splits, splits[1:]):
        while old_start < old_end and new_start < new_end:
            old_node = old_nodes[old_start]
            new_node = new_nodes[new_start]

            if old_start in to_remove:
                assert isinstance(old_node, tuple)
                removes += 1
                old_start += 1

            elif not isinstance(new_node, tuple):
                assert not isinstance(old_node, tuple)
                while removes:
                    yield ('remove', *path, index)
                    removes -= 1
                if new_node != old_node:
                    yield ('replace', *path, index, clean_node(new_node))
                old_start += 1
                new_start += 1
                index += 1

            elif not isinstance(old_node, tuple):
                if removes:
                    action = 'replace'
                    removes -= 1
                else:
                    action = 'insert'
                yield (action, *path, index, clean_node(new_nodes[new_start]))
                new_start += 1
                index += 1

            else:
                assert old_node[0] == new_node[0]
                while removes:
                    yield ('remove', *path, index)
                    removes -= 1
                if old_node is not new_node:
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

                    yield from node_diff(
                        (None, {}, old_mapping, *old_children),
                        (None, {}, new_mapping, *new_children),
                        (*path, index),
                    )
                old_start += 1
                new_start += 1
                index += 1

        while old_start < old_end:
            removes += 1
            old_start += 1

        while new_start < new_end:
            if removes:
                action = 'replace'
                removes -= 1
            else:
                action = 'insert'
            yield (action, *path, index, clean_node(new_nodes[new_start]))
            index += 1
            new_start += 1

    while removes:
        yield ('remove', *path, index)
        removes -= 1
