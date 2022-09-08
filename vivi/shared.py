from contextlib import asynccontextmanager

from .context import create_context


class Shared:

    def __init__(self, provider, cm, args, kwargs):
        self._provider = provider
        self._cm = cm
        self._args = args
        self._kwargs = kwargs

    @asynccontextmanager
    async def __call__(self):
        async with self._cm(*self._args, **self._kwargs) as value:
            yield self._provider(value=value)


def create_shared(cm, *args, **kwargs):
    provider, use_shared = create_context()
    return Shared(provider, cm, args, kwargs), use_shared
