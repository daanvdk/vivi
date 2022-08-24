import asyncio
from collections import Counter
from itertools import chain
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from .element import HTMLElement, Component, h, fragment
from .hooks import _ctx
from .node import SafeText, node_get, node_parts, node_diff


SCRIPT_BEFORE, SCRIPT_AFTER = Path(__file__).parent.joinpath('asgi.js').read_text().split('{{socket_url}}')


def wrap(result, socket_url=None):
    if not isinstance(result, tuple) or result[0] != 'html':
        result = ('html', {}, ('body', {}, result))

    if socket_url is not None:
        script = ('script', {}, SafeText(SCRIPT_BEFORE + socket_url + SCRIPT_AFTER))

        for i, child in enumerate(result[2:], 2):
            if isinstance(child, tuple) and child[0] == 'head':
                result = (*result[:i], (*child, script), *result[i + 1:])
                break
        else:
            result = (*result[:2], ('head', {}, script), *result[2:])

    return (None, {}, SafeText('<!doctype html>'), result)


class Vivi:

    def __init__(self, elem):
        self._elem = elem
        self._sessions = {}

    async def __call__(self, scope, receive, send):
        loop = asyncio.get_running_loop()

        if scope['type'] == 'http':
            queue = asyncio.Queue()
            url = scope['path']
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
                result = wrap(result)
            else:
                session_id = str(uuid4())
                self._sessions[session_id] = (state, result, queue, rerender_path, push_url, replace_url, url, url_paths)
                loop.call_later(5, lambda: self._sessions.pop(session_id, None))
                result = wrap(result, f'{scope["root_path"]}/{session_id}')

            await send({
                'type': 'http.response.start',
                'status': 200,
                'headers': [
                    (b'content-type', b'text/html; charset=utf-8'),
                    (b'connection', b'keep-alive'),
                ],
            })
            await send({
                'type': 'http.response.body',
                'body': ''.join(node_parts(result)).encode(),
            })

        elif scope['type'] == 'websocket':
            assert (await receive())['type'] == 'websocket.connect'

            session_id = scope['path'][1:]
            try:
                state, result, queue, rerender_path, push_url, replace_url, url, url_paths = self._sessions.pop(session_id)
            except KeyError:
                await send({'type': 'websocket.close'})
                return

            await send({'type': 'websocket.accept'})

            receive_fut = loop.create_task(receive())
            queue_fut = loop.create_task(queue.get())

            while True:
                await asyncio.wait(
                    [receive_fut, queue_fut],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if receive_fut.done():
                    message = receive_fut.result()
                    if message['type'] == 'websocket.disconnect':
                        self._elem._unmount(state, result)
                        return
                    assert message['type'] == 'websocket.receive'

                    event_type, *path, details = json.loads(
                        message['bytes']
                        if message['text'] is None else
                        message['text']
                    )

                    if event_type == 'pop_url':
                        assert not path
                        queue.put_nowait(('pop_url', details))
                    else:
                        target = node_get(wrap(result, f'{scope["root_path"]}/{session_id}'), path)
                        handler = target[1][f'on{event_type}']

                        event = SimpleNamespace(type=event_type, **details)
                        loop.call_soon(handler, event)

                    receive_fut = loop.create_task(receive())

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
                        old_result = wrap(result, f'{scope["root_path"]}/{session_id}')

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

                        new_result = wrap(result, f'{scope["root_path"]}/{session_id}')

                        actions.extend(node_diff(old_result, new_result))

                    if actions:
                        await send({
                            'type': 'websocket.send',
                            'text': json.dumps(actions, separators=(',', ':')),
                        })

                    queue_fut = loop.create_task(queue.get())

        elif scope['type'] == 'lifespan':
            assert (await receive())['type'] == 'lifespan.startup'
            await send({'type': 'lifespan.startup.complete'})

            assert (await receive())['type'] == 'lifespan.shutdown'
            await send({'type': 'lifespan.shutdown.complete'})

        else:
            raise ValueError(f'unknown scope type: {scope["type"]}')
