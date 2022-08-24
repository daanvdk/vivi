import asyncio
from types import SimpleNamespace


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


def use_state(initial_value):
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


def use_url():
    ref = use_ref()

    if hasattr(ref, '_vivi_cleanup'):
        ref._vivi_cleanup()

    path = tuple(_ctx.path)
    url_paths = _ctx.url_paths
    url_paths[path] += 1

    def cleanup():
        url_paths[path] -= 1
        if url_paths[path] == 0:
            del url_paths[path]

    ref._vivi_cleanup = cleanup

    return _ctx.url


def use_push_url():
    _ctx.static = False
    return _ctx.push_url


def use_replace_url():
    _ctx.static = False
    return _ctx.replace_url
