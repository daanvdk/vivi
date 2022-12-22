import asyncio
from contextlib import AsyncExitStack

from ..app import Vivi, mount
from ..paths import Paths
from ..html import html_refs
from .assertion import Assertion


URLS = {
    'http': lambda path: path,
    'static': lambda path: '/static/' + path.lstrip('/'),
    'file': lambda file_id: '/file/' + str(file_id),
}


class TestSession(Assertion):

    __test__ = False

    def __init__(self, elem, *, url='/', cookies={}, timeout=3):
        super().__init__(self, ())

        if isinstance(elem, Vivi):
            shared = elem._shared
            elem = elem._elem
        else:
            shared = ()

        self._url = url
        self._prev = []
        self._next = []
        self._cookies = cookies.copy()
        self._files = {}
        self._timeout = timeout
        self._elem = elem
        self._shared = shared
        self._subscriptions = set()

    def start(self, loop=None):
        if loop is None:
            loop = asyncio.new_event_loop()

        self._loop = loop
        self._run_fut = loop.create_task(self._run())
        self._mounted_fut = loop.create_future()
        self._root = None
        self._shared_values = {}
        self._forks = []
        self._update()

    def stop(self):
        self._run_fut.cancel()
        try:
            self._loop.run_until_complete(self._run_fut)
        except asyncio.CancelledError:
            pass

        if self._root is None:
            for fork in self._forks:
                fork.stop()
            del self._forks

            while self._loop._ready:
                self._loop.stop()
                self._loop.run_forever()
            self._loop.close()

        del self._loop
        del self._run_fut
        del self._mounted_fut
        del self._root
        del self._shared_values

    def fork(self):
        while self._root is not None:
            self = self._root

        session = TestSession(
            self._elem,
            url=self._url,
            cookies=self._cookies.copy(),
            timeout=self._timeout,
        )
        session._shared_values = self._shared_values
        session._loop = self._loop
        session._run_fut = self._loop.create_task(session._base_run())
        session._mounted_fut = self._loop.create_future()
        session._root = self
        session._shared_values = self._shared_values
        session._update()
        self._forks.append(session)
        return session

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def _get_url(self, name, **params):
        return URLS[name](**params)

    async def _run(self):
        async with AsyncExitStack() as stack:
            for shared in self._shared:
                await stack.enter_async_context(shared(self._shared_values))
            await self._base_run()

    async def _base_run(self):
        self._queue = asyncio.Queue()
        self._change = asyncio.Event()

        cookie_paths = {}

        self._result, rerender, unmount = mount(
            self._queue, self._elem,
            self._cookies, cookie_paths,
            self._url, self._shared_values,
            self._files, self._get_url,
        )
        self._mounted_fut.set_result(None)
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
