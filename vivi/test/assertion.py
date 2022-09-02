import asyncio
from types import SimpleNamespace

from ..html import SafeText
from ..node import Node
from ..filter import parse_filter


NO_VALUE = object()


class Assertion:

    def __init__(self, session, actions):
        self._session = session
        self._actions = actions

    def _holds(self):
        actions = self._actions
        if not actions or actions[-1][0] == 'find':
            actions = (*actions, ('exists',))

        nodes = [Node((), self._session._result)]
        for action in actions:
            if action[0] == 'find':
                _, filter = action
                nodes = list(filter(nodes))

            elif action[0] == 'parent':
                nodes = [
                    node.parent
                    for node in nodes
                    if node.parent is not None
                ]

            elif action[0] == 'exists':
                if not nodes:
                    return 'node does not exist'

            elif action[0] == 'not_exists':
                if nodes:
                    return 'node exists'

            elif action[0] == 'has_text':
                _, expected = action
                actual = SafeText.join(node.text() for node in nodes)
                if actual != expected:
                    return f'node has text {actual!r} instead of {expected!r}'

            elif action[0] == 'not_has_text':
                _, expected = action
                if SafeText.join(node.text() for node in nodes) == expected:
                    return f'node has text {expected!r}'

            elif action[0] == 'has_prop':
                _, key = action

                try:
                    node, = nodes
                except ValueError:
                    if nodes:
                        return 'cannot check props of multiple nodes'
                    else:
                        return 'no node to check props of'

                if node.type != 'element' or key not in node:
                    return f'node does not have prop {key}'

            elif action[0] == 'not_has_prop':
                _, key = action

                try:
                    node, = nodes
                except ValueError:
                    if nodes:
                        return 'cannot check props of multiple nodes'
                    else:
                        return 'no node to check props of'

                if node.type == 'element' and key in node:
                    return f'node does have prop {key}'

            elif action[0] == 'prop':
                _, key, expected = action

                try:
                    node, = nodes
                except ValueError:
                    if nodes:
                        return 'cannot check props of multiple nodes'
                    else:
                        return 'no node to check props of'

                try:
                    actual = node[key]
                except (ValueError, KeyError):
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
                    node, = nodes
                except ValueError:
                    if nodes:
                        return 'cannot check props of multiple nodes'
                    else:
                        return 'no node to check props of'

                try:
                    actual = node[key]
                except (ValueError, KeyError):
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
            node, = nodes
        except ValueError:
            if nodes:
                return f'cannot {event_type} on multiple nodes'
            else:
                return f'no node to {event_type}'

        try:
            handler = node[f'on{event_type}']
            assert callable(handler)
        except (ValueError, KeyError, AssertionError):
            return f'node is not {event_type}able'

        node._subscribe(self._session._queue, self._session._subscriptions)

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
        filter = parse_filter(filter)
        return Assertion(self._session, (*self._actions, ('find', filter)))

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
