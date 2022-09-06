import asyncio
from contextlib import contextmanager, asynccontextmanager
from functools import partial

from ..app import Vivi, mount
from ..paths import Paths
from ..html import html_refs
from .assertion import Assertion


@asynccontextmanager
async def noop_lifespan():
    yield


class TestSession(Assertion):

    __test__ = False

    def __init__(self, elem, *, url='/', cookies={}, timeout=3):
        super().__init__(self, ())

        if isinstance(elem, Vivi):
            lifespan = partial(elem.router.lifespan_context, elem)
            elem = elem._elem
        else:
            lifespan = noop_lifespan

        self._url = url
        self._prev = []
        self._next = []
        self._cookies = cookies.copy()
        self._files = {}
        self._timeout = timeout
        self._elem = elem
        self._lifespan = lifespan
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

    def _get_file_url(self, file_id):
        return f'/file/{file_id}'

    async def _run(self):
        lifespan_context = self._lifespan()
        await lifespan_context.__aenter__()
        try:
            return await self._run_base()
        finally:
            await lifespan_context.__aexit__(None, None, None)

    async def _run_base(self):
        self._queue = asyncio.Queue()
        self._change = asyncio.Event()

        cookie_paths = {}

        self._result, rerender, unmount = mount(
            self._queue, self._elem, self._cookies, cookie_paths, self._url,
            self._files, self._get_file_url,
        )
        html_refs(None, self._result, self._queue, self._subscriptions)

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
                html_refs(
                    old_result, self._result,
                    self._queue, self._subscriptions,
                )

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
    lifespan = sessions[0]._lifespan
    for session in sessions[1:]:
        assert session._lifespan is lifespan, (
            'sessions have different lifespans'
        )

    lifespan_context = lifespan()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(lifespan_context.__aenter__())

    for session in sessions:
        session._loop = loop
        session._run_fut = loop.create_task(session._run_base())

    try:
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

        loop.run_until_complete(lifespan_context.__aexit__(None, None, None))

        while loop._ready:
            loop.stop()
            loop.run_forever()

        loop.close()
