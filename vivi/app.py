import asyncio
from itertools import islice
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.websockets import WebSocketDisconnect

from .hooks import _ctx, _url_provider
from .node import SafeText, node_get, node_parts, node_diff
from .paths import Paths


DOCTYPE = SafeText('<!doctype html>')
SCRIPT_BEFORE, SCRIPT_AFTER = (
    Path(__file__).parent.joinpath('app.js')
    .read_text().split('{{socket_url}}')
)


def wrap(result, script=None, prev_head=None):
    while isinstance(result, tuple) and result[0] is None and len(result) == 4:
        result = result[3]

    if not isinstance(result, tuple) or result[0] != 'html':
        result = ('html', {}, {0: 0}, ('body', {}, {0: 0}, result))

    head = None
    body = None

    stack = [islice(result, 3, None)]
    while stack:
        try:
            node = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue

        if isinstance(node, tuple) and node[0] is None:
            stack.append(islice(result, 3, None))
        elif isinstance(node, tuple) and node[0] == 'head':
            assert head is None
            head = node
        elif isinstance(node, tuple) and node[0] == 'body':
            assert body is None
            body = node
        else:
            raise ValueError(f'unexpected node in html: {node}')

    original_head = head

    if script is not None:
        if head is None:
            head = ('head', {}, {0: 0}, script)
        else:
            _, props, mapping, *children = head
            if head is prev_head:
                mapping = {i: i for i in range(len(children))}
            new_mapping = {0: 0}
            for index, prev_index in mapping.items():
                new_mapping[index + 1] = prev_index + 1
            head = ('head', {}, new_mapping, script, *children)

    if head is None:
        head = ('head', {}, {})
    if body is None:
        body = ('body', {}, {})

    result = (
        None, {}, {0: 0, 1: 1},
        DOCTYPE,
        ('html', result[1], {0: 0, 1: 1}, head, body),
    )
    return result, original_head


class Vivi(Starlette):

    def __init__(
        self, elem, *,
        debug=False,
        static_path=None,
        static_route='/static',
        on_startup=[],
        on_shutdown=[],
    ):
        routes = []

        if static_path is not None:
            routes.append(Mount(
                static_route,
                app=StaticFiles(directory=static_path),
            ))

        routes.append(Route(
            '/{path:path}',
            endpoint=self._http,
            methods=['GET'],
            name='http',
        ))
        routes.append(WebSocketRoute(
            '/{session_id:uuid}',
            endpoint=self._websocket,
            name='websocket',
        ))

        super().__init__(
            debug=debug,
            routes=routes,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
        )

        self._elem = elem
        self._sessions = {}

    async def _http(self, request):
        queue = asyncio.Queue()
        url = request['path']
        contexts = {}
        cookies = request.cookies
        cookie_paths = {}

        def rerender_path(path):
            queue.put_nowait(('path', path))

        def push_url(url):
            queue.put_nowait(('push_url', url))

        def replace_url(url):
            queue.put_nowait(('replace_url', url))

        def set_cookie(key, value):
            queue.put_nowait(('set_cookie', key, value))

        def unset_cookie(key):
            queue.put_nowait(('unset_cookie', key))

        elem = _url_provider(self._elem, value=url)

        _ctx.static = True
        _ctx.rerender_path = rerender_path
        _ctx.push_url = push_url
        _ctx.replace_url = replace_url
        _ctx.set_cookie = set_cookie
        _ctx.unset_cookie = unset_cookie
        _ctx.contexts = contexts
        _ctx.cookies = cookies
        _ctx.cookie_paths = cookie_paths
        _ctx.rerender_paths = Paths()
        _ctx.path = []
        try:
            state, result = elem._render(*elem._init())
            static = _ctx.static
        finally:
            del _ctx.static
            del _ctx.rerender_path
            del _ctx.push_url
            del _ctx.replace_url
            del _ctx.set_cookie
            del _ctx.unset_cookie
            del _ctx.contexts
            del _ctx.cookies
            del _ctx.cookie_paths
            del _ctx.rerender_paths
            del _ctx.path

        if static:
            self._elem._unmount(state, result)
            result, _ = wrap(result)
        else:
            session_id = uuid4()
            script = ('script', {}, {0: 0}, SafeText(
                SCRIPT_BEFORE +
                json.dumps(
                    request.url_for('websocket', session_id=session_id)
                ) +
                SCRIPT_AFTER
            ))
            base_result = result
            result, head = wrap(result, script)

            self._sessions[session_id] = (
                state,
                base_result,
                head,
                script,
                queue,
                rerender_path,
                push_url,
                replace_url,
                set_cookie,
                unset_cookie,
                url,
                contexts,
                cookies,
                cookie_paths,
            )

            def session_timeout():
                try:
                    state, result, *_ = self._sessions.pop(session_id)
                except KeyError:
                    return
                elem._unmount(state, result)

            loop = asyncio.get_running_loop()
            loop.call_later(5, session_timeout)

        return Response(
            ''.join(node_parts(result)),
            media_type='text/html',
            headers={'connection': 'keep-alive'},
        )

    async def _websocket(self, socket):
        loop = asyncio.get_running_loop()

        session_id = socket.path_params['session_id']
        try:
            (
                state,
                result,
                head,
                script,
                queue,
                rerender_path,
                push_url,
                replace_url,
                set_cookie,
                unset_cookie,
                url,
                contexts,
                cookies,
                cookie_paths,
            ) = self._sessions.pop(session_id)
        except KeyError:
            await socket.close()
            return

        await socket.accept()

        receive_fut = loop.create_task(socket.receive_json())
        queue_fut = loop.create_task(queue.get())

        while True:
            await asyncio.wait(
                [receive_fut, queue_fut],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if receive_fut.done():
                try:
                    event_type, *path, details = receive_fut.result()
                except WebSocketDisconnect:
                    elem = _url_provider(self._elem, value=url)
                    wrapped_result, _ = wrap(result, script, head)
                    elem._unmount(state, wrapped_result)
                    return

                if event_type == 'pop_url':
                    assert not path
                    queue.put_nowait(('pop_url', details))
                else:
                    target = node_get(wrap(result, script)[0], path)
                    handler = target[1][f'on{event_type}']

                    event = SimpleNamespace(type=event_type, **details)
                    loop.call_soon(handler, event)

                receive_fut = loop.create_task(socket.receive_json())

            elif queue_fut.done():
                changes = [queue_fut.result()]
                while not queue.empty():
                    changes.append(queue.get_nowait())

                actions = []
                paths = Paths()
                for change in changes:
                    if change[0] == 'path':
                        _, path = change
                        paths[path] = None
                    elif change[0] in ('pop_url', 'push_url', 'replace_url'):
                        change_type, url = change
                        if change_type != 'pop_url':
                            actions.append(change)
                    elif change[0] == 'set_cookie':
                        _, key, value = change
                        cookies[key] = value
                        for path in cookie_paths.get(key, []):
                            paths[path] = None
                        actions.append(change)
                    elif change[0] == 'unset_cookie':
                        _, key = change
                        del cookies[key]
                        for path in cookie_paths.get(key, []):
                            paths[path] = None
                        actions.append(change)
                    else:
                        raise ValueError(f'unknown change: {change[0]}')

                old_result, _ = wrap(result, script)

                elem = _url_provider(self._elem, value=url)

                _ctx.static = False
                _ctx.rerender_path = rerender_path
                _ctx.push_url = push_url
                _ctx.replace_url = replace_url
                _ctx.set_cookie = set_cookie
                _ctx.unset_cookie = unset_cookie
                _ctx.contexts = contexts
                _ctx.cookies = cookies
                _ctx.cookie_paths = cookie_paths
                _ctx.rerender_paths = paths
                _ctx.path = []
                try:
                    state, result = elem._render(state, result)
                finally:
                    del _ctx.static
                    del _ctx.rerender_path
                    del _ctx.push_url
                    del _ctx.replace_url
                    del _ctx.set_cookie
                    del _ctx.unset_cookie
                    del _ctx.contexts
                    del _ctx.cookies
                    del _ctx.cookie_paths
                    del _ctx.rerender_paths
                    del _ctx.path

                new_result, head = wrap(result, script, head)

                actions.extend(node_diff(old_result, new_result))

                if actions:
                    await socket.send_text(json.dumps(
                        actions,
                        separators=(',', ':'),
                    ))

                queue_fut = loop.create_task(queue.get())
