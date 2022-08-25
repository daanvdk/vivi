import asyncio
from collections import Counter
from itertools import chain
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.websockets import WebSocketDisconnect

from .hooks import _ctx
from .node import SafeText, node_get, node_parts, node_diff


SCRIPT_BEFORE, SCRIPT_AFTER = Path(__file__).parent.joinpath('app.js').read_text().split('{{socket_url}}')


def wrap(result, script=None):
    if not isinstance(result, tuple) or result[0] != 'html':
        result = ('html', {}, ('body', {}, result))

    if script is not None:
        for i, child in enumerate(result[2:], 2):
            if isinstance(child, tuple) and child[0] == 'head':
                result = (*result[:i], (*child, script), *result[i + 1:])
                break
        else:
            result = (*result[:2], ('head', {}, script), *result[2:])

    return (None, {}, SafeText('<!doctype html>'), result)


class Vivi(Starlette):

    def __init__(self, elem, *, debug=False, static_path=None, static_route='/static'):
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

        super().__init__(debug=debug, routes=routes)

        self._elem = elem
        self._sessions = {}

    async def _http(self, request):
        queue = asyncio.Queue()
        url = request['path']
        url_paths = Counter()

        def rerender_path(path):
            queue.put_nowait(('path', path))

        def push_url(url):
            queue.put_nowait(('push_url', url))

        def replace_url(url):
            queue.put_nowait(('replace_url', url))

        _ctx.static = True
        _ctx.rerender_path = rerender_path
        _ctx.push_url = push_url
        _ctx.replace_url = replace_url
        _ctx.url = url
        _ctx.url_paths = url_paths
        _ctx.path = []
        try:
            state, result = self._elem._render(*self._elem._init())
            static = _ctx.static
        finally:
            del _ctx.static
            del _ctx.rerender_path
            del _ctx.push_url
            del _ctx.replace_url
            del _ctx.url
            del _ctx.url_paths
            del _ctx.path

        if static:
            self._elem._unmount(state, result)
            result = wrap(result)
        else:
            session_id = uuid4()
            script = ('script', {}, SafeText(
                SCRIPT_BEFORE +
                json.dumps(request.url_for('websocket', session_id=session_id)) +
                SCRIPT_AFTER
            ))
            self._sessions[session_id] = (state, result, script, queue, rerender_path, push_url, replace_url, url, url_paths)

            def session_timeout():
                try:
                    state, result, *_ = self._sessions.pop(session_id)
                except KeyError:
                    return
                self._elem._unmount(state, result)

            loop = asyncio.get_running_loop()
            loop.call_later(5, session_timeout)

            result = wrap(result, script)

        return Response(
            ''.join(node_parts(result)),
            media_type='text/html',
            headers={'connection': 'keep-alive'},
        )

    async def _websocket(self, socket):
        loop = asyncio.get_running_loop()

        session_id = socket.path_params['session_id']
        try:
            state, result, script, queue, rerender_path, push_url, replace_url, url, url_paths = self._sessions.pop(session_id)
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
                    self._elem._unmount(state, result)
                    return

                if event_type == 'pop_url':
                    assert not path
                    queue.put_nowait(('pop_url', details))
                else:
                    target = node_get(wrap(result, script), path)
                    handler = target[1][f'on{event_type}']

                    event = SimpleNamespace(type=event_type, **details)
                    loop.call_soon(handler, event)

                receive_fut = loop.create_task(socket.receive_json())

            elif queue_fut.done():
                changes = [queue_fut.result()]
                while not queue.empty():
                    changes.append(queue.get_nowait())

                actions = []
                paths = set()
                for change in changes:
                    if change[0] == 'path':
                        _, path = change
                        paths.add(path)
                    elif change[0] in ('pop_url', 'push_url', 'replace_url'):
                        change_type, url = change
                        paths.update(url_paths)
                        if change_type != 'pop_url':
                            actions.append(change)
                    else:
                        raise ValueError(f'unknown change: {change[0]}')

                if paths:
                    old_result = wrap(result, script)

                    _ctx.static = False
                    _ctx.rerender_path = rerender_path
                    _ctx.push_url = push_url
                    _ctx.replace_url = replace_url
                    _ctx.url = url
                    _ctx.url_paths = url_paths
                    try:
                        for path in sorted(paths, reverse=True):
                            _ctx.path = list(path)
                            state, result = self._elem._rerender(path, state, result)
                    finally:
                        del _ctx.static
                        del _ctx.rerender_path
                        del _ctx.push_url
                        del _ctx.replace_url
                        del _ctx.url
                        del _ctx.url_paths
                        del _ctx.path

                    new_result = wrap(result, script)

                    actions.extend(node_diff(old_result, new_result))

                if actions:
                    await socket.send_text(json.dumps(actions, separators=(',', ':')))

                queue_fut = loop.create_task(queue.get())
