import asyncio
import html
import json
from types import SimpleNamespace

from ..html import html_flatten, SafeText
from ..node import Node


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


def _parse_filter(filter):
    __tracebackhide__ = True

    filters = [[]]
    index = 0

    def space():
        nonlocal index
        while index < len(filter) and filter[index].isspace():
            index += 1

    def word():
        nonlocal index
        if index >= len(filter) or filter[index] not in WORD_INIT_CHARS:
            raise AssertionError(f'{index}: expected a word')
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
                        index = start
                        raise AssertionError(f'{index}: expected a value')
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
                if index >= len(filter) or not filter[index].isdigit():
                    index = start
                    raise AssertionError(f'{index}: expected a value')
                index += 1
                while index < len(filter) and filter[index].isdigit():
                    index += 1
                if filter.startswith('.', index):
                    index += 1
                    if index >= len(filter) or not filter[index].isdigit():
                        index = start
                        raise AssertionError(f'{index}: expected a value')
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
            raise AssertionError(f'{index}: expected a value')

    space()
    while index < len(filter):
        if filter[index] == ',':
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
                predicates.append(('tag', word()))

        while index < len(filter):
            if filter[index] == '#':
                index += 1
                predicates.append(('prop', 'id', word()))
            elif filter[index] == '.':
                index += 1
                predicates.append(('class', word()))
            elif filter[index] == '[':
                index += 1
                key = word()
                if filter.startswith('=', index):
                    index += 1
                    value = value()
                    predicates.append(('prop', key, value))
                else:
                    predicates.append(('has_prop', key))
                if not filter.startswith(']', index):
                    raise AssertionError(f'{index}: expected right bracket')
                index += 1
            elif filter[index] == ':':
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
                        if not filter.startswith(',', index):
                            raise AssertionError(
                                f'{index}: expected right par or comma'
                            )
                        index += 1
                        space()
                    index += 1
                predicates.append(('selector', selector, *args))
            else:
                break

        if not predicates and not star:
            raise AssertionError(f'{index}: expected a predicate')

        filters[-1].append((tuple(predicates), deep))
        space()

    return tuple(map(tuple, filters))


def _children(node, *, deep=False):
    stack = []

    parents, node = node

    if isinstance(node, tuple):
        stack.append((
            parents, node,
            enumerate(html_flatten((None, {}, {}, *node[3:]))),
        ))

    while stack:
        parents, node, children = stack[-1]
        try:
            index, child = next(children)
        except StopIteration:
            stack.pop()
            continue

        yield (*parents, (node, index)), child

        if deep and isinstance(child, tuple):
            stack.append((
                (*parents, (node, index)), child,
                enumerate(html_flatten((None, {}, {}, *child[3:]))),
            ))


def _find(nodes, filter):
    for predicates, deep in filter:
        nodes = [
            child
            for node in nodes
            for child in _children(node, deep=deep)
        ]

        for predicate in predicates:
            if predicate[0] == 'tag':
                _, tag = predicate
                nodes = [node for node in nodes if (
                    isinstance(node[1], tuple) and
                    node[1][0] == tag
                )]

            elif predicate[0] == 'prop':
                _, key, value = predicate
                nodes = [node for node in nodes if (
                    isinstance(node[1], tuple) and
                    key in node[1][1] and
                    node[1][1][key] == value
                )]

            elif predicate[0] == 'has_prop':
                _, key = predicate
                nodes = [node for node in nodes if (
                    isinstance(node[1], tuple) and
                    key not in node[1][1]
                )]

            elif predicate[0] == 'class':
                _, classname = predicate
                nodes = [node for node in nodes if (
                    isinstance(node[1], tuple) and
                    classname in node[1][1].get('class', '').split()
                )]

            elif predicate[0] == 'selector':
                _, selector, *args = predicate

                if selector == 'eq':
                    try:
                        index, = args
                    except ValueError:
                        raise AssertionError(
                            ':eq expects 1 argument'
                        ) from None
                    if not isinstance(index, int):
                        raise AssertionError(':eq index should be an int')
                    try:
                        nodes = [nodes[index]]
                    except IndexError:
                        raise AssertionError(
                            ':eq index out of range'
                        ) from None

                elif selector == 'text':
                    try:
                        content, = args
                    except ValueError:
                        raise AssertionError(
                            ':text expects 1 argument'
                        ) from None
                    if not isinstance(content, str):
                        raise AssertionError(':text content should be a str')
                    nodes = [node for node in nodes if (
                        _text([node]) == content
                    )]

                elif selector == 'contains':
                    try:
                        content, = args
                    except ValueError:
                        raise AssertionError(
                            ':text expects 1 argument'
                        ) from None
                    if not isinstance(content, str):
                        raise AssertionError(':text content should be a str')
                    nodes = [node for node in nodes if (
                        content in _text([node])
                    )]

                else:
                    raise AssertionError(f'unknown selector: {selector}')

            else:
                raise AssertionError(f'unknown predicate: {predicate[0]}')

    return nodes


def _text(nodes):
    parts = []
    safe = False

    for node in nodes:
        for child in _children(node, deep=True):
            if isinstance(child[1], str):
                if safe:
                    parts.append(html.escape(child[1]))
                else:
                    parts.append(child[1])

            elif isinstance(child[1], SafeText):
                if not safe:
                    parts = [html.escape(part) for part in parts]
                    safe = True
                parts.append(child[1].text)

    text = ''.join(parts)
    if safe:
        text = SafeText(text)
    return text


NO_VALUE = object()


class Assertion:

    def __init__(self, session, actions):
        self._session = session
        self._actions = actions

    def _holds(self):
        actions = self._actions
        if not actions or actions[-1][0] == 'find':
            actions = (*actions, ('exists',))

        nodes = [((), self._session._result)]
        for action in actions:
            if action[0] == 'find':
                _, filters = action
                nodes = [
                    node
                    for filter in filters
                    for node in _find(nodes, filter)
                ]

            elif action[0] == 'parent':
                nodes = [
                    (parents[:-1], parents[-1][0])
                    for parents, node in nodes
                    if parents
                ]

            elif action[0] == 'exists':
                if not nodes:
                    return 'node does not exist'

            elif action[0] == 'not_exists':
                if nodes:
                    return 'node exists'

            elif action[0] == 'has_text':
                _, expected = action
                actual = _text(nodes)
                if actual != expected:
                    return f'node has text {actual!r} instead of {expected!r}'

            elif action[0] == 'not_has_text':
                _, expected = action
                if _text(nodes) == expected:
                    return f'node has text {expected!r}'

            elif action[0] == 'has_prop':
                _, key = action

                try:
                    (_, node), = nodes
                except ValueError:
                    if nodes:
                        return 'cannot check props of multiple nodes'
                    else:
                        return 'no node to check props of'

                if not isinstance(node, tuple) or key not in node[1]:
                    return f'node does not have prop {key}'

            elif action[0] == 'not_has_prop':
                _, key = action

                try:
                    (_, node), = nodes
                except ValueError:
                    if nodes:
                        return 'cannot check props of multiple nodes'
                    else:
                        return 'no node to check props of'

                if isinstance(node, tuple) and key in node[1]:
                    return f'node does have prop {key}'

            elif action[0] == 'prop':
                _, key, expected = action

                try:
                    (_, node), = nodes
                except ValueError:
                    if nodes:
                        return 'cannot check props of multiple nodes'
                    else:
                        return 'no node to check props of'

                try:
                    assert isinstance(node, tuple)
                    actual = node[1][key]
                except (AssertionError, KeyError):
                    return f'node does not have prop {key}'
                else:
                    if actual != expected:
                        return (
                            f'node prop {key} has value {actual!r} instead of '
                            f'{expected!r}'
                        )

            elif action[0] == 'not_prop':
                _, key, expected = action

                try:
                    (_, node), = nodes
                except ValueError:
                    if nodes:
                        return 'cannot check props of multiple nodes'
                    else:
                        return 'no node to check props of'

                try:
                    assert isinstance(node, tuple)
                    actual = node[1][key]
                except (AssertionError, KeyError):
                    pass
                else:
                    if actual == expected:
                        return f'node prop {key} does have value {expected!r}'

            elif action[0] == 'has_len':
                _, expected = action
                actual = len(nodes)
                if actual != expected:
                    return f'node has len {actual} instead of {expected}'

            elif action[0] == 'has_cookie':
                _, key = action
                if key not in self._session._cookies:
                    return f'node does not have cookie {key}'

            elif action[0] == 'not_has_cookie':
                _, key = action
                if key in self._session._cookies:
                    return f'session does have cookie {key}'

            elif action[0] == 'cookie':
                _, key, expected = action
                try:
                    actual = self._session._cookies[key]
                except KeyError:
                    return f'session does not have cookie {key}'
                else:
                    if actual != expected:
                        return (
                            f'session cookie {key} has value {actual!r} '
                            f'instead of {expected!r}'
                        )

            elif action[0] == 'not_cookie':
                _, key, expected = action
                try:
                    actual = self._session._cookies[key]
                except KeyError:
                    pass
                else:
                    if actual == expected:
                        return f'session cookie {key} has value {actual!r}'

            elif action[0] == 'url':
                _, expected = action
                if self._session._url != expected:
                    return (
                        f'session has url {self._session.url!r} instead of '
                        f'{expected!r}'
                    )

            elif action[0] == 'not_url':
                _, expected = action
                if self._session._url == expected:
                    return f'session has url {expected!r}'

            elif action[0] == 'click':
                reason = self._event(nodes, 'click')
                if reason is not None:
                    return reason

            elif action[0] == 'input':
                _, value = action
                reason = self._event(nodes, 'input', value=value)
                if reason is not None:
                    return reason

            else:
                raise ValueError(f'unknown action: {action[0]}')

        return None

    def _event(self, nodes, event_type, **details):
        try:
            (parents, node), = nodes
        except ValueError:
            if nodes:
                return f'cannot {event_type} on multiple nodes'
            else:
                return f'no node to {event_type}'

        node = Node(
            parents, node,
            self._session._queue, self._session._subscriptions,
        )

        try:
            handler = node[f'on{event_type}']
            assert callable(handler)
        except (ValueError, KeyError, AssertionError):
            return f'node is not {event_type}able'

        loop = asyncio.get_running_loop()
        loop.call_soon(handler, SimpleNamespace(
            type=event_type,
            target=node,
            **details,
        ))

    async def _aholds(self, timeout):
        loop = asyncio.get_running_loop()

        timeout_fut = loop.create_task(asyncio.sleep(timeout))
        while True:
            try:
                reason = self._holds()
            except Exception:
                timeout_fut.cancel()
                raise

            if reason is None:
                timeout_fut.cancel()
                return None

            change_fut = loop.create_task(self._session._change.wait())
            await asyncio.wait(
                [change_fut, timeout_fut, self._session._run_fut],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if self._session._run_fut.done():
                if not timeout_fut.done():
                    timeout_fut.cancel()
                if not change_fut.done():
                    change_fut.cancel()
                try:
                    self._session._run_fut.result()
                except Exception:
                    raise
                else:
                    return reason

            if timeout_fut.done():
                if not change_fut.done():
                    change_fut.cancel()
                return reason

    def wait(self, timeout=None):
        if timeout is None:
            timeout = self._session._timeout

        loop = self._session._loop
        asyncio.set_event_loop(loop)
        try:
            reason = loop.run_until_complete(self._aholds(timeout))
        except AssertionError as e:
            reason = str(e)
        if reason is not None:
            __tracebackhide__ = True
            raise AssertionError(reason)
        self._session._update()

    def __bool__(self):
        __tracebackhide__ = True
        self.wait()
        return True

    def find(self, filter):
        __tracebackhide__ = True
        filters = _parse_filter(filter)
        return Assertion(self._session, (*self._actions, ('find', filters)))

    def parent(self):
        return Assertion(self._session, (*self._actions, ('parent',)))

    def exists(self):
        return Assertion(self._session, (*self._actions, ('exists',)))

    def not_exists(self):
        return Assertion(self._session, (*self._actions, ('not_exists',)))

    def has_text(self, text):
        return Assertion(self._session, (*self._actions, ('has_text', text)))

    def not_has_text(self, text):
        return Assertion(
            self._session,
            (*self._actions, ('not_has_text', text)),
        )

    def has_prop(self, key, value=NO_VALUE):
        if value is NO_VALUE:
            action = ('has_prop', key)
        else:
            action = ('prop', key, value)
        return Assertion(self._session, (*self._actions, action))

    def not_has_prop(self, key, value=NO_VALUE):
        if value is NO_VALUE:
            action = ('not_has_prop', key)
        else:
            action = ('not_prop', key, value)
        return Assertion(self._session, (*self._actions, action))

    def has_len(self, len):
        return Assertion(self._session, (*self._actions, ('has_len', len)))

    def has_cookie(self, key, value=NO_VALUE):
        if value is NO_VALUE:
            action = ('has_cookie', key)
        else:
            action = ('cookie', key, value)
        return Assertion(self._session, (*self._actions, action))

    def not_has_cookie(self, key, value=NO_VALUE):
        if value is NO_VALUE:
            action = ('not_has_cookie', key)
        else:
            action = ('not_cookie', key, value)
        return Assertion(self._session, (*self._actions, action))

    def has_url(self, url):
        return Assertion(self._session, (*self._actions, ('url', url)))

    def not_has_url(self, url):
        return Assertion(self._session, (*self._actions, ('not_url', url)))

    def click(self):
        return Assertion(self._session, (*self._actions, ('click',)))

    def input(self, value):
        return Assertion(self._session, (*self._actions, ('input', value)))
