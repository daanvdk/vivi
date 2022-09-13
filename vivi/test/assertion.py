import asyncio
import re
from types import SimpleNamespace

from starlette.convertors import CONVERTOR_TYPES

from ..html import SafeText
from ..node import Node
from ..filter import parse_filter
from ..events import CallbackWrapper


UUID_CONVERTOR = CONVERTOR_TYPES['uuid']
NO_VALUE = object()
FILE_RE = re.compile(fr'/file/({UUID_CONVERTOR.regex})')


def dispatch(target, event_type, details):
    loop = asyncio.get_running_loop()

    if (
        target.type == 'element' and
        target.tag == 'input' and
        target.get('type') == 'file'
    ):
        if target.get('multiple', False):
            details['files'] = details.pop('value')
        else:
            details['file'] = details.pop('value')

    current_target = target
    while current_target is not None:
        try:
            callback = current_target[f'on{event_type}']
        except (ValueError, KeyError):
            callback = None

        args = {
            'prevent_default': False,
            'stop_propagation': False,
        }

        while isinstance(callback, CallbackWrapper):
            args[callback.key] = callback.value
            callback = callback.callback

        event = SimpleNamespace(
            type=event_type,
            target=target,
            current_target=current_target,
            **details,
        )

        if callback is not None:
            loop.call_soon(callback, event)
        if not args['prevent_default']:
            loop.call_soon(default_callback, event)
        if args['stop_propagation']:
            break

        current_target = current_target.parent


def default_callback(event):
    if (
        event.type == 'click' and
        event.current_target.type == 'element' and
        event.current_target.tag in ('input', 'button') and
        event.current_target.get('type') == 'submit'
    ):
        node = event.current_target.parent
        while node is not None:
            if node.type == 'element' and node.tag == 'form':
                dispatch(node, 'submit', {})
                break
            node = node.parent


class Assertion:

    def __init__(self, session, actions):
        self._session = session
        self._actions = actions

    def _get(self):
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
                assert nodes, 'node does not exist'

            elif action[0] == 'not_exists':
                assert not nodes, 'node exists'

            elif action[0] == 'has_text':
                _, expected = action
                actual = SafeText.join(node.text() for node in nodes)
                assert actual == expected, (
                    f'node has text {actual!r} instead of {expected!r}'
                )

            elif action[0] == 'not_has_text':
                _, expected = action
                actual = SafeText.join(node.text() for node in nodes)
                assert actual != expected, f'node has text {expected!r}'

            elif action[0] == 'has_tag':
                _, tag = action

                try:
                    node, = nodes
                except ValueError:
                    raise AssertionError(
                        'cannot check tag of multiple nodes'
                        if nodes else
                        'no node to check tag of'
                    )

                assert node.type == 'element' and node.tag == tag, (
                    f'node does not have tag {tag}'
                )

            elif action[0] == 'not_has_tag':
                _, tag = action

                try:
                    node, = nodes
                except ValueError:
                    raise AssertionError(
                        'cannot check tag of multiple nodes'
                        if nodes else
                        'no node to check tag of'
                    )

                assert node.type != 'element' or node.tag != tag, (
                    f'node has tag {tag}'
                )

            elif action[0] == 'has_prop':
                _, key = action

                try:
                    node, = nodes
                except ValueError:
                    raise AssertionError(
                        'cannot check props of multiple nodes'
                        if nodes else
                        'no node to check props of'
                    )

                assert node.type == 'element' and key in node, (
                    f'node does not have prop {key}'
                )

            elif action[0] == 'not_has_prop':
                _, key = action

                try:
                    node, = nodes
                except ValueError:
                    if nodes:
                        return 'cannot check props of multiple nodes'
                    else:
                        return 'no node to check props of'

                assert node.type != 'element' or key not in node, (
                    f'node does have prop {key}'
                )

            elif action[0] == 'prop':
                _, key, expected = action

                try:
                    node, = nodes
                except ValueError:
                    raise AssertionError(
                        'cannot check props of multiple nodes'
                        if nodes else
                        'no node to check props of'
                    )

                try:
                    actual = node[key]
                except (ValueError, KeyError):
                    raise AssertionError(f'node does not have prop {key}')
                else:
                    assert actual == expected, (
                        f'node prop {key} has value {actual!r} instead of '
                        f'{expected!r}'
                    )

            elif action[0] == 'not_prop':
                _, key, expected = action

                try:
                    node, = nodes
                except ValueError:
                    raise AssertionError(
                        'cannot check props of multiple nodes'
                        if nodes else
                        'no node to check props of'
                    )

                try:
                    actual = node[key]
                except (ValueError, KeyError):
                    pass
                else:
                    assert actual != expected, (
                        f'node prop {key} does have value {expected!r}'
                    )

            elif action[0] == 'has_len':
                _, expected = action
                actual = len(nodes)
                assert actual == expected, (
                    f'node has len {actual} instead of {expected}'
                )

            elif action[0] == 'has_cookie':
                _, key = action
                assert key in self._session._cookies, (
                    f'node does not have cookie {key}'
                )

            elif action[0] == 'not_has_cookie':
                _, key = action
                assert key not in self._session._cookies, (
                    f'session does have cookie {key}'
                )

            elif action[0] == 'cookie':
                _, key, expected = action
                try:
                    actual = self._session._cookies[key]
                except KeyError:
                    raise AssertionError(f'session does not have cookie {key}')
                else:
                    assert actual == expected, (
                        f'session cookie {key} has value {actual!r} instead '
                        f'of {expected!r}'
                    )

            elif action[0] == 'not_cookie':
                _, key, expected = action
                try:
                    actual = self._session._cookies[key]
                except KeyError:
                    pass
                else:
                    assert actual != expected, (
                        f'session cookie {key} has value {actual!r}'
                    )

            elif action[0] == 'url':
                _, expected = action
                assert self._session._url == expected, (
                    f'session has url {self._session._url!r} instead of '
                    f'{expected!r}'
                )

            elif action[0] == 'not_url':
                _, expected = action
                assert self._session_url != expected, (
                    f'session has url {expected!r}'
                )

            elif action[0] == 'has_file':
                _, file_id = action
                assert file_id in self._session._files, 'file does not exist'

            elif action[0] == 'not_has_file':
                _, file_id = action
                assert file_id not in self._session._files, 'file exists'

            elif action[0] == 'file':
                _, file_id, expected = action
                try:
                    file_path = self._session._files[file_id]
                except KeyError:
                    raise AssertionError('file does not exist')
                else:
                    actual = file_path.read_bytes()
                    assert actual == expected, (
                        f'file has content {actual!r} instead of {expected!r}'
                    )
                    del actual

            elif action[0] == 'file':
                _, file_id, expected = action
                try:
                    file_path = self._session._files[file_id]
                except KeyError:
                    pass
                else:
                    actual = file_path.read_bytes()
                    assert actual != expected, f'file has content {actual!r}'
                    del actual

            elif action[0] == 'click':
                self._event(nodes, 'click')

            elif action[0] == 'input':
                _, value = action
                self._event(nodes, 'input', value=value)

            else:
                raise ValueError(f'unknown action: {action[0]}')

        return nodes

    def _event(self, nodes, event_type, **details):
        try:
            target, = nodes
        except ValueError:
            raise AssertionError(
                f'cannot {event_type} on multiple nodes'
                if nodes else
                f'no node to {event_type}'
            ) from None

        target._subscribe(self._session._queue, self._session._subscriptions)
        dispatch(target, event_type, details)

    async def _aget(self):
        await asyncio.wait(
            [self._session._run_fut, self._session._mounted_fut],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if self._session._run_fut.done():
            try:
                self._session._run_fut.result()
            except Exception:
                raise
            else:
                raise RuntimeError('application unexpectedly stopped')

        timeout_fut = asyncio.create_task(
            asyncio.sleep(self._session._timeout)
        )
        while True:
            try:
                nodes = self._get()
            except AssertionError as e:
                reason = str(e)
            except Exception:
                if not timeout_fut.done():
                    timeout_fut.cancel()
                raise
            else:
                if not timeout_fut.done():
                    timeout_fut.cancel()
                return nodes

            change_fut = asyncio.create_task(self._session._change.wait())
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
                    raise RuntimeError('application unexpectedly stopped')

            if timeout_fut.done():
                if not change_fut.done():
                    change_fut.cancel()
                raise AssertionError(reason)

    def all(self, filter=NO_VALUE):
        __tracebackhide__ = True
        if filter is not NO_VALUE:
            self = self.find(filter)

        loop = self._session._loop
        asyncio.set_event_loop(loop)

        try:
            return loop.run_until_complete(self._aget())
        except AssertionError as e:
            raise AssertionError(str(e)) from None
        finally:
            self._session._update()

    def get(self, filter=NO_VALUE):
        __tracebackhide__ = True
        try:
            node, = self.all(filter)
        except ValueError:
            raise AssertionError('multiple nodes exist')
        return node

    def __bool__(self):
        __tracebackhide__ = True
        self.all()
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

    def has_tag(self, tag):
        return Assertion(self._session, (*self._actions, ('has_tag', tag)))

    def not_has_tag(self, tag):
        return Assertion(self._session, (*self._actions, ('not_has_tag', tag)))

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

    def has_file(self, file_url, content=NO_VALUE):
        try:
            match = FILE_RE.fullmatch(file_url)
            file_id = UUID_CONVERTOR.convert(match.group(1))
        except (AttributeError, ValueError):
            raise ValueError('not a valid file url') from None

        if content is NO_VALUE:
            action = ('has_file', file_id)
        else:
            action = ('file', file_id, content)
        return Assertion(self._session, (*self._actions, action))

    def not_has_file(self, file_url, content=NO_VALUE):
        try:
            match = FILE_RE.fullmatch(file_url)
            file_id = UUID_CONVERTOR.convert(match.group(1))
        except (AttributeError, ValueError):
            raise ValueError('not a valid file url') from None

        if content is NO_VALUE:
            action = ('not_has_file', file_id)
        else:
            action = ('not_file', file_id, content)
        return Assertion(self._session, (*self._actions, action))

    def click(self):
        return Assertion(self._session, (*self._actions, ('click',)))

    def input(self, value=NO_VALUE, **details):
        if value is NO_VALUE:
            value = SimpleNamespace(**details)
        elif details:
            raise ValueError(
                'kwargs are only accepted when no positional argument is '
                'provided'
            )
        return Assertion(self._session, (*self._actions, ('input', value)))
