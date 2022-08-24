import html
import json


class SafeText:

    __slots__ = ['text']

    def __init__(self, text):
        self.text = text


def node_flatten(result):
    if not isinstance(result, tuple):
        yield result
        return

    tag, props, *children = result

    flat_children = []
    for child in children:
        for flat_child in node_flatten(child):
            if isinstance(flat_child, SafeText):
                flat_child = flat_child.text
            elif isinstance(flat_child, str):
                flat_child = html.escape(flat_child)

            if (
                isinstance(flat_child, str) and
                flat_children and
                isinstance(flat_children[-1], str)
            ):
                flat_children[-1] += flat_child
            else:
                flat_children.append(flat_child)

    if tag is None:
        yield from flat_children
    else:
        yield (tag, props, *flat_children)


def node_parts(nodes):
    for i, node in enumerate(nodes):
        if isinstance(node, str):
            yield node
            continue

        tag, props, *children = node

        yield '<'
        yield tag
        for key, value in props.items():
            if value is False:
                continue
            yield ' '
            yield key
            if value is True:
                continue
            yield '="'
            if callable(value):
                value = 'call(event)'
            elif not isinstance(value, str):
                value = json.dumps(value)
            yield html.escape(value)
            yield '"'
        yield '>'

        yield from node_parts(children)

        yield '</'
        yield tag
        yield '>'


def node_diff(old_nodes, new_nodes, path=()):
    for index, (old_node, new_node) in enumerate(zip(old_nodes, new_nodes)):
        if (
            isinstance(new_node, tuple) and
            isinstance(old_node, tuple) and
            new_node[0] == old_node[0]
        ):
            _, old_props, *old_children = old_node
            _, new_props, *new_children = new_node

            for key in set(old_props) - set(new_props):
                yield ('unset', *path, index, key)

            for key, value in new_props.items():
                if key not in old_props or (
                    not callable(old_props[key])
                    if callable(value) else
                    old_props[key] != value
                ):
                    if callable(value):
                        value = 'call(event)'
                    yield ('set', *path, index, key, value)

            yield from node_diff(old_children, new_children, (*path, index))

        elif new_node == old_node:
            pass

        else:
            yield ('replace', *path, index, new_node)

    for _ in range(len(old_nodes) - len(new_nodes)):
        yield ('remove', *path, len(new_nodes))

    for index, node in enumerate(new_nodes[len(old_nodes):], len(old_nodes)):
        yield ('insert', *path, index, node)
