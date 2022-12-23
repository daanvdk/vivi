import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from inspect import signature
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from .context import create_context
from .shared import create_shared


CONTEXT = ContextVar('context')


def use_ref(**kwargs):
    ctx = CONTEXT.get()

    if isinstance(ctx.refs, list):
        ref = SimpleNamespace(**kwargs)
        ctx.refs.append(ref)
    else:
        try:
            ref = next(ctx.refs)
        except StopIteration:
            raise ValueError('more refs used than previous render') from None
    return ref


def use_state(initial_value=None):
    ctx = CONTEXT.get()

    ref = use_ref()
    ctx.static = False
    ref.path = tuple(ctx.path)
    ref.rerender_path = ctx.rerender_path

    if not hasattr(ref, 'value'):
        if callable(initial_value):
            initial_value = initial_value()

        def set_value(value):
            if callable(value):
                value = value(ref.value)

            ref.value = value
            ref.rerender_path(ref.path)

        ref.value = initial_value
        ref.set_value = set_value

    return ref.value, ref.set_value


def use_memo(*key):
    def decorator(callback):
        ref = use_ref()
        if not hasattr(ref, 'key') or ref.key != key:
            ref.key = key
            ref.value = callback()
        return ref.value
    return decorator


def use_callback(*key):
    def decorator(callback):
        return use_memo(*key)(lambda: callback)
    return decorator


def use_effect(*key, immediate=False):
    def decorator(callback):
        ref = use_ref()
        if not hasattr(ref, 'key') or ref.key != key:
            loop = asyncio.get_running_loop()

            ref.key = key

            if hasattr(ref, '_vivi_cleanup'):
                ref._vivi_cleanup()
                del ref._vivi_cleanup

            def wrapped_callback():
                cleanup = callback()
                if callable(cleanup):
                    if immediate:
                        ref._vivi_cleanup = cleanup
                    else:
                        ref._vivi_cleanup = lambda: loop.call_soon(cleanup)

            if immediate:
                wrapped_callback()
            else:
                loop.call_soon(wrapped_callback)

        return callback
    return decorator


_url_provider, use_url = create_context()


def use_push_url():
    ctx = CONTEXT.get()
    ctx.static = False
    return ctx.push_url


def use_replace_url():
    ctx = CONTEXT.get()
    ctx.static = False
    return ctx.replace_url


def use_future(fut, loading=object(), *, eager=False):
    ctx = CONTEXT.get()

    ref = use_ref(fut=None, eager=None)
    ref.path = tuple(ctx.path)
    ref.rerender_path = ctx.rerender_path

    if hasattr(ref, '_vivi_cleanup'):
        ref._vivi_cleanup()
        del ref._vivi_cleanup

    if fut is not None and not fut.done():
        ctx.static = False
        if eager and ctx.eager is not None:
            ref.eager = ctx.eager
            ref.eager.add(fut)

            def cleanup():
                ref.eager.remove(ref.fut)
                ref.eager = None

            ref._vivi_cleanup = cleanup

    if fut is not ref.fut:
        ref.fut = fut
        if fut is not None and not fut.done():
            @fut.add_done_callback
            def on_fut_done(fut):
                if fut is ref.fut:
                    ref.rerender_path(ref.path)

    if fut is not None and fut.done():
        return fut.result()
    else:
        return loading


use_future.LOADING = signature(use_future).parameters['loading'].default


NO_DEFAULT = object()


def use_cookie(key, default=NO_DEFAULT):
    ctx = CONTEXT.get()
    ref = use_ref()

    if not hasattr(ref, 'key') or ref.key != key:
        ref.key = key

        if hasattr(ref, '_vivi_cleanup'):
            ref._vivi_cleanup()

        cookie_paths = ctx.cookie_paths
        path = tuple(ctx.path)

        cookie_paths.setdefault(key, set()).add(path)

        def cleanup():
            paths = cookie_paths[key]
            paths.remove(path)
            if not paths:
                del cookie_paths[key]

        ref._vivi_cleanup = cleanup

    try:
        return ctx.cookies[key]
    except KeyError:
        if default is NO_DEFAULT:
            raise
        else:
            return default


def use_set_cookie():
    ctx = CONTEXT.get()
    ctx.static = False
    return ctx.set_cookie


def use_unset_cookie():
    ctx = CONTEXT.get()
    ctx.static = False
    return ctx.unset_cookie


def use_file(path):
    ctx = CONTEXT.get()
    ref = use_ref()

    try:
        path = Path(path).absolute()
    except Exception:
        pass

    if getattr(ref, 'path', None) != path:
        if hasattr(ref, 'path'):
            ref._vivi_cleanup()
            del ref.path
            del ref.url
            del ref._vivi_cleanup

        if path is not None:
            if not isinstance(path, Path) or not path.is_file():
                raise ValueError('path is not a file')

            files = ctx.files
            file_id = uuid4()
            files[file_id] = path

            def cleanup():
                del files[file_id]

            ref.path = path
            ref.url = ctx.get_url('file', file_id=file_id)
            ref._vivi_cleanup = cleanup

    return getattr(ref, 'url', None)


def use_static(path):
    ctx = CONTEXT.get()
    return ctx.get_url('static', path=path)


def use_path(path):
    ctx = CONTEXT.get()
    return ctx.get_url('http', path=path)


@asynccontextmanager
async def _pubsub_manager():
    loop = asyncio.get_event_loop()

    channels = {}

    def publish(channel, message):
        try:
            subscriptions = channels[channel]
        except KeyError:
            return
        for callback in subscriptions.values():
            loop.call_soon(callback, message)

    def subscribe(channel, callback):
        try:
            subscriptions = channels[channel]
        except KeyError:
            subscriptions = {}
            channels[channel] = subscriptions

        subscription_id = object()
        subscriptions[subscription_id] = callback

        def unsubscribe():
            del subscriptions[subscription_id]
            if not subscriptions:
                del channels[channel]

        return unsubscribe

    yield publish, subscribe


_shared_pubsub, _use_pubsub = create_shared(_pubsub_manager)


def use_publish():
    publish, _ = _use_pubsub()
    return publish


def use_subscribe(channel, *, ignore=False):
    def decorator(callback):
        _, subscribe = _use_pubsub()

        @use_effect(channel, ignore, subscribe, callback, immediate=True)
        def subscribe_callback():
            if ignore:
                return
            return subscribe(channel, callback)

        return callback
    return decorator


async def use_messages(channel):
    _, subscribe = _use_pubsub()
    queue = asyncio.Queue()
    unsubscribe = subscribe(channel, queue.put_nowait)
    try:
        while True:
            yield await queue.get()
    finally:
        unsubscribe()
