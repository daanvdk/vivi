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


def mount(queue, elem, cookies, cookie_paths, url, eager=None):
    contexts = {}

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

    elem_with_url = _url_provider(elem, value=url)
    state, result = elem_with_url._init()
    static = True

    def rerender(url, paths, eager=None):
        nonlocal elem_with_url, state, result, static

        elem_with_url = _url_provider(elem, value=url)

        _ctx.static = True
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
        _ctx.eager = eager
        try:
            state, result = elem_with_url._render(state, result)
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
            del _ctx.eager

        return result

    def unmount():
        nonlocal elem_with_url, state, result
        elem_with_url._unmount(state, result)

    result = rerender(url, Paths(), eager)
    if static:
        unmount()
        return result, None, None
    else:
        return result, rerender, unmount


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
        cookies = request.cookies
        cookie_paths = {}

        eager = set()
        result, rerender, unmount = mount(
            queue, self._elem, cookies, cookie_paths, url,
            eager=eager,
        )

        if rerender is None:
            result, _ = wrap(result)
        else:
            async def next_render(eager=None):
                nonlocal url

                changes = [await queue.get()]
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

                return actions, rerender(url, paths, eager)

            init_actions = []
            while eager:
                actions, result = await next_render(eager)
                init_actions.extend(actions)

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
                queue,
                script,
                head,
                base_result,
                init_actions,
                next_render,
                unmount,
            )

            def session_timeout():
                try:
                    unmount = self._sessions.pop(session_id)[-1]
                except KeyError:
                    return
                unmount()

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
                queue,
                script,
                head,
                result,
                init_actions,
                next_render,
                unmount,
            ) = self._sessions.pop(session_id)
        except KeyError:
            await socket.close()
            return

        await socket.accept()

        if init_actions:
            await socket.send_text(json.dumps(
                init_actions,
                separators=(',', ':'),
            ))

        receive_fut = loop.create_task(socket.receive_json())
        render_fut = loop.create_task(next_render())

        while True:
            await asyncio.wait(
                [receive_fut, render_fut],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if receive_fut.done():
                try:
                    event_type, *path, details = receive_fut.result()
                except WebSocketDisconnect:
                    render_fut.cancel()
                    unmount()
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

            elif render_fut.done():
                old_result, _ = wrap(result, script)
                actions, result = render_fut.result()
                new_result, head = wrap(result, script, head)
                actions.extend(node_diff(old_result, new_result))

                if actions:
                    await socket.send_text(json.dumps(
                        actions,
                        separators=(',', ':'),
                    ))

                render_fut = loop.create_task(next_render())
