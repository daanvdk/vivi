import html
from itertools import islice, zip_longest
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
    for arg in ['prevent_default', 'stop_propagation', 'stop_immediate_propagation']:
        parts.append(', ')
        parts.append(json.dumps(args[arg]))
    parts.append(')')
    return ''.join(parts)


def clean_node(node):
    if not isinstance(node, tuple):
        return node

    tag, props, *children = node

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

    return (tag, cleaned_props, *map(clean_node, children))


def node_flatten(node):
    stack = [iter([node])]

    while stack:
        try:
            node = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue

        if isinstance(node, tuple) and node[0] is None:
            stack.append(islice(node, 2, None))
            continue

        if isinstance(node, (str, SafeText)):
            while stack:
                try:
                    next_node = next(stack[-1])
                except StopIteration:
                    stack.pop()
                    continue

                if isinstance(next_node, tuple) and next_node[0] is None:
                    stack.append(islice(next_node, 2, None))
                    continue

                if isinstance(next_node, str):
                    if isinstance(node, str):
                        node += next_node
                    else:
                        node = SafeText(node.text + html.escape(next_node, quote=False))
                elif isinstance(next_node, SafeText):
                    if isinstance(node, str):
                        node = SafeText(html.escape(node, quote=False) + next_node.text)
                    else:
                        node = SafeText(node.text + next_node.text)
                else:
                    if node:
                        yield node
                    node = next_node
                    break

        if node is not None:
            yield node


def node_get(node, path):
    for index in path:
        if node[0] is not None:
            node = (None, {}, *node[2:])
        node = next(islice(node_flatten(node), index, None))
    return node


def node_parts(node):
    if isinstance(node, SafeText):
        yield node.text
        return

    if isinstance(node, str):
        yield html.escape(node, quote=False)
        return

    tag, props, *children = node

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
    old_nodes = node_flatten(old_node)
    new_nodes = node_flatten(new_node)

    for index, (old_node, new_node) in enumerate(zip_longest(old_nodes, new_nodes)):
        if old_node is None:
            yield ('insert', *path, index, clean_node(new_node))

        elif new_node is None:
            yield ('remove', *path, index)
            for _ in old_nodes:
                yield ('remove', *path, index)

        elif new_node is old_node:
            pass

        elif (
            isinstance(new_node, tuple) and
            isinstance(old_node, tuple) and
            new_node[0] == old_node[0]
        ):
            _, old_props, *old_children = old_node
            _, new_props, *new_children = new_node

            for key in set(old_props) - set(new_props):
                yield ('unset', *path, index, key)

            for key, value in new_props.items():
                value = clean_value(value)
                if key not in old_props or clean_value(old_props[key]) != value:
                    if value is False:
                        yield ('unset', *path, index, key)
                        continue
                    if value is True:
                        value = ''
                    yield ('set', *path, index, key, value)

            yield from node_diff(
                (None, {}, *old_children),
                (None, {}, *new_children),
                (*path, index),
            )

        elif new_node == old_node:
            pass

        else:
            yield ('replace', *path, index, clean_node(new_node))
