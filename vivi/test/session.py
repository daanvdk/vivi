import asyncio
from contextlib import contextmanager

from ..app import mount
from ..paths import Paths
from ..html import html_refs
from ..node import Node
from .assertion import Assertion


class TestSession(Assertion):

    __test__ = False

    def __init__(self, elem, *, url='/', cookies={}, timeout=3):
        super().__init__(self, ())

        self._url = url
        self._prev = []
        self._next = []
        self._cookies = cookies.copy()
        self._timeout = timeout
        self._elem = elem
        self._subscriptions = set()

    def start(self, loop=None):
        if loop is None:
            loop = asyncio.new_event_loop()

        self._loop = loop
        self._run_fut = loop.create_task(self._run())
        self._update()

    def stop(self):
        self._run_fut.cancel()
        self._loop.stop()
        self._loop.run_forever()
        self._loop.close()

        del self._loop
        del self._run_fut

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    async def _run(self):
        self._queue = asyncio.Queue()
        self._change = asyncio.Event()

        cookie_paths = {}

        self._result, rerender, unmount = mount(
            self._queue, self._elem, self._cookies, cookie_paths, self._url,
        )
        for ref, path in html_refs(None, self._result):
            self._loop.call_soon(ref, Node.from_path(
                self._result, path, self._queue, self._subscriptions,
            ))

        if rerender is None:
            return

        try:
            while True:
                changes = [await self._queue.get()]
                while not self._queue.empty():
                    changes.append(self._queue.get_nowait())

                paths = Paths()
                for change in changes:
                    if change[0] == 'path':
                        _, path = change
                        paths[path] = None
                    elif change[0] == 'prev_url':
                        self._next.append(self._url)
                        self._url = self._prev.pop()
                    elif change[0] == 'next_url':
                        self._prev.append(self._url)
                        self._url = self._next.pop()
                    elif change[0] in 'push_url':
                        self._prev.append(self._url)
                        _, self._url = change
                        self._next.clear()
                    elif change[0] in 'replace_url':
                        _, self._url = change
                    elif change[0] == 'set_cookie':
                        _, key, value = change
                        self._cookies[key] = value
                        for path in cookie_paths.get(key, []):
                            paths[path] = None
                    elif change[0] == 'unset_cookie':
                        _, key = change
                        del self._cookies[key]
                        for path in cookie_paths.get(key, []):
                            paths[path] = None
                    elif change[0] == 'focus':
                        pass
                    else:
                        raise ValueError(f'unknown change: {change[0]}')

                old_result = self._result
                self._result = rerender(self._url, paths)

                for callback in list(self._subscriptions):
                    callback(self._result)
                for ref, path in html_refs(old_result, self._result):
                    self._loop.call_soon(ref, Node.from_path(
                        self._result, path, self._queue, self._subscriptions,
                    ))

                self._change.set()
                self._change.clear()
        finally:
            unmount()

    def prev(self):
        self._queue.put_nowait(('prev_url',))
        self._update()

    def next(self):
        self._queue.put_nowait(('next_url',))
        self._update()

    def _update(self):
        asyncio.set_event_loop(self._loop)
        while self._loop._ready:
            self._loop.stop()
            self._loop.run_forever()
        if self._run_fut.done():
            self._run_fut.result()


@contextmanager
def run_together(self, *sessions):
    loop = asyncio.new_event_loop()

    for session in sessions:
        session._loop = loop
        session._run_fut = loop.create_task(session._run())

    try:
        asyncio.set_event_loop(loop)
        while loop._ready:
            loop.stop()
            loop.run_forever()

        yield sessions
    finally:
        for session in reversed(sessions):
            if not session._run_fut.done():
                session._run_fut.cancel()
            del session._loop
            del session._run_fut

        loop.stop()
        loop.run_forever()
        loop.close()
