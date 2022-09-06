from functools import partial
from itertools import chain
import json


WORD_INIT_CHARS = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    'abcdefghijklmnopqrstuvwxyz'
    '-_'
)
WORD_CONT_CHARS = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    'abcdefghijklmnopqrstuvwxyz'
    '0123456789-_'
)


def _sort_nodes(nodes):
    nodes_by_path = {}
    for node in nodes:
        path = tuple(index for _, index in node._parents)
        nodes_by_path[path] = node
    for path in sorted(nodes_by_path):
        yield nodes_by_path[path]


def _lazy_index(nodes, index):
    nodes = list(_sort_nodes(nodes))
    try:
        yield nodes[index]
    except IndexError:
        pass


def _check(predicate, nodes):
    if predicate[0] == 'tag':
        _, tag = predicate
        return (node for node in nodes if (
            node.type == 'element' and node.tag == tag
        ))

    elif predicate[0] == 'prop':
        _, key, value = predicate
        return (node for node in nodes if (
            node.type == 'element' and
            key in node and
            node[key] == value
        ))

    elif predicate[0] == 'has_prop':
        _, key = predicate
        return (node for node in nodes if (
            node.type == 'element' and key in node
        ))

    elif predicate[0] == 'class':
        _, classname = predicate
        return (node for node in nodes if (
            node.type == 'element' and
            classname in node.get('class', '').split()
        ))

    elif predicate[0] == 'selector':
        _, selector, *args = predicate

        if selector == 'eq':
            index, = args
            return _lazy_index(nodes, index)

        elif selector == 'text':
            content, = args
            return (node for node in nodes if (
                node.text() == content
            ))

        elif selector == 'contains':
            content, = args
            return (node for node in nodes if (
                content in node.text()
            ))

        else:
            raise AssertionError(f'unknown selector: {selector}')

    else:
        raise AssertionError(f'unknown predicate: {predicate[0]}')


def _children(nodes, deep):
    for node in nodes:
        yield from node.children(deep=deep)


def _find(filters, nodes):
    nodes = list(nodes)
    matches = []

    for filter in filters:
        nodes_ = list(nodes)
        for predicates, deep in filter:
            nodes_ = _children(nodes_, deep)
            for predicate in predicates:
                nodes_ = predicate(nodes_)
        matches.append(nodes_)

    return _sort_nodes(chain.from_iterable(matches))


def parse_filter(filter):
    __tracebackhide__ = True

    filters = [[]]
    index = 0

    def space():
        nonlocal index
        while index < len(filter) and filter[index].isspace():
            index += 1

    def word():
        nonlocal index
        assert index < len(filter) and filter[index] in WORD_INIT_CHARS, (
            f'{index}: expected a word'
        )
        start = index
        index += 1
        while index < len(filter) and filter[index] in WORD_CONT_CHARS:
            index += 1
        return filter[start:index]

    def value():
        nonlocal index
        start = index
        depth = 0
        while True:
            if filter.startswith('"', index):
                index += 1
                while not filter.startswith('"', index):
                    if filter.startswith('\\"', index):
                        index += 2
                    elif index < len(filter):
                        index += 1
                    else:
                        raise AssertionError(f'{start}: expected a value')
                index += 1
            elif (
                filter.startswith('{', index) or
                filter.startswith('[', index)
            ):
                depth += 1
                index += 1
            elif (
                filter.startswith('}', index) or
                filter.startswith(']', index)
            ):
                depth -= 1
                index += 1
            elif depth == 0 and filter.startswith('true'):
                index += 4
            elif depth == 0 and filter.startswith('false'):
                index += 5
            elif depth == 0 and filter.startswith('null'):
                index += 4
            elif depth == 0 and index < len(filter) and (
                filter[index].isdigit() or
                filter[index] == '-'
            ):
                if filter[index] == '-':
                    index += 1
                assert index < len(filter) and filter[index].isdigit(), (
                    f'{start}: expected a value'
                )
                index += 1
                while index < len(filter) and filter[index].isdigit():
                    index += 1
                if filter.startswith('.', index):
                    index += 1
                    assert index < len(filter) and filter[index].isdigit(), (
                        f'{start}: expected a value'
                    )
                    index += 1
                    while index < len(filter) and filter[index].isdigit():
                        index += 1
            elif depth != 0 and index < len(filter):
                index += 1
            else:
                index = start
                raise AssertionError(f'{index}: expected a value')

            if depth == 0:
                break

        try:
            return json.loads(filter[start:index])
        except ValueError:
            index = start
            raise AssertionError(f'{index}: expected a value') from None

    space()
    while index < len(filter):
        if filter[index] == ',' and filters[-1]:
            index += 1
            filters.append([])
            space()
            continue

        if filter[index] == '>':
            deep = False
            index += 1
            space()
        else:
            deep = True

        predicates = []
        star = False

        if index < len(filter):
            if filter[index] == '*':
                star = True
                index += 1
            elif filter[index] in WORD_INIT_CHARS:
                predicates.append(partial(_check, ('tag', word())))

        while index < len(filter):
            if filter[index] == '#':
                index += 1
                predicates.append(partial(_check, ('prop', 'id', word())))
            elif filter[index] == '.':
                index += 1
                predicates.append(partial(_check, ('class', word())))
            elif filter[index] == '[':
                index += 1
                key = word()
                if filter.startswith('=', index):
                    index += 1
                    value = value()
                    predicates.append(partial(_check, ('prop', key, value)))
                else:
                    predicates.append(partial(_check, ('has_prop', key)))
                assert filter.startswith(']', index), (
                    f'{index}: expected right bracket'
                )
                index += 1

            elif filter[index] == ':':
                start = index
                index += 1
                selector = word()
                args = []
                if filter.startswith('(', index):
                    index += 1
                    space()
                    while not filter.startswith(')', index):
                        args.append(value())
                        space()
                        if filter.startswith(')', index):
                            break
                        assert filter.startswith(',', index), (
                            f'{index}: expected right par or comma'
                        )
                        index += 1
                        space()
                    index += 1

                if selector == 'eq':
                    assert len(args) == 1, f'{index}: :eq expects 1 argument'
                    assert isinstance(args[0], int), (
                        f'{start}: :eq index should be an int'
                    )

                elif selector == 'text':
                    assert len(args) == 1, f'{index}: :text expects 1 argument'
                    assert isinstance(args[0], str), (
                        f'{start}: :text content should be a str'
                    )

                elif selector == 'contains':
                    assert len(args) == 1, (
                        f'{start}: :contains expects 1 argument'
                    )
                    assert isinstance(args[0], str), (
                        f'{start}: :contains content should be a str'
                    )

                else:
                    raise AssertionError(
                        f'{start}: unknown selector {selector}'
                    )

                predicates.append(
                    partial(_check, ('selector', selector, *args))
                )
            else:
                break

        assert predicates or star, f'{index}: expected a predicate'

        filters[-1].append((tuple(predicates), deep))
        space()

    assert filters[-1], f'{index}: expected a predicate'

    return partial(_find, tuple(map(tuple, filters)))
