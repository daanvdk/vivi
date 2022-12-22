from contextlib import asynccontextmanager
import sys
from types import SimpleNamespace


class Shared:

    def __init__(self, key, cm, args, kwargs):
        self._key = key
        self._cm = cm
        self._args = args
        self._kwargs = kwargs

    @asynccontextmanager
    async def __call__(self, shared_values):
        from .hooks import CONTEXT

        cm = self._cm(*self._args, **self._kwargs)

        token = CONTEXT.set(SimpleNamespace(shared=shared_values))
        try:
            value = await cm.__aenter__()
        finally:
            CONTEXT.reset(token)

        shared_values[self._key] = value
        try:
            yield
        finally:
            del shared_values[self._key]

            token = CONTEXT.set(SimpleNamespace(shared=shared_values))
            try:
                await cm.__aexit__(*sys.exc_info())
            finally:
                CONTEXT.reset(token)


def create_shared(cm, *args, **kwargs):
    key = object()

    def use_shared():
        from .hooks import CONTEXT
        ctx = CONTEXT.get()
        return ctx.shared[key]

    return Shared(key, cm, args, kwargs), use_shared
