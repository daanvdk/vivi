import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from .context import create_context


_ctx = SimpleNamespace()


def use_ref(**kwargs):
    if isinstance(_ctx.refs, list):
        ref = SimpleNamespace(**kwargs)
        _ctx.refs.append(ref)
    else:
        try:
            ref = next(_ctx.refs)
        except StopIteration:
            raise ValueError('more refs used than previous render') from None
    return ref


def use_state(initial_value=None):
    ref = use_ref()
    _ctx.static = False
    ref.path = tuple(_ctx.path)
    ref.rerender_path = _ctx.rerender_path

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


def use_effect(*key):
    def decorator(callback):
        ref = use_ref()
        if not hasattr(ref, 'key') or ref.key != key:
            loop = asyncio.get_running_loop()

            ref.key = key

            if hasattr(ref, '_vivi_cleanup'):
                ref._vivi_cleanup()
                del ref._vivi_cleanup

            @loop.call_soon
            def wrapped_callback():
                cleanup = callback()
                if callable(cleanup):
                    ref._vivi_cleanup = lambda: loop.call_soon(cleanup)

    return decorator


_url_provider, use_url = create_context()


def use_push_url():
    _ctx.static = False
    return _ctx.push_url


def use_replace_url():
    _ctx.static = False
    return _ctx.replace_url


def use_future(fut, sentinel=None, *, eager=False):
    ref = use_ref(fut=None, eager=None)

    ref.path = tuple(_ctx.path)
    ref.rerender_path = _ctx.rerender_path

    if hasattr(ref, '_vivi_cleanup'):
        ref._vivi_cleanup()
        del ref._vivi_cleanup

    if fut is not None and not fut.done():
        _ctx.static = False
        if eager and _ctx.eager is not None:
            ref.eager = _ctx.eager
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
        return sentinel


NO_DEFAULT = object()


def use_cookie(key, default=NO_DEFAULT):
    ref = use_ref()

    if not hasattr(ref, 'key') or ref.key != key:
        ref.key = key

        if hasattr(ref, '_vivi_cleanup'):
            ref._vivi_cleanup()

        cookie_paths = _ctx.cookie_paths
        path = tuple(_ctx.path)

        cookie_paths.setdefault(key, set()).add(path)

        def cleanup():
            paths = cookie_paths[key]
            paths.remove(path)
            if not paths:
                del cookie_paths[key]

        ref._vivi_cleanup = cleanup

    try:
        return _ctx.cookies[key]
    except KeyError:
        if default is NO_DEFAULT:
            raise
        else:
            return default


def use_set_cookie():
    _ctx.static = False
    return _ctx.set_cookie


def use_unset_cookie():
    _ctx.static = False
    return _ctx.unset_cookie


def use_file(path):
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

            files = _ctx.files
            file_id = uuid4()
            files[file_id] = path

            def cleanup():
                del files[file_id]

            ref.path = path
            ref.url = _ctx.get_file_url(file_id)
            ref._vivi_cleanup = cleanup

    return getattr(ref, 'url', None)
