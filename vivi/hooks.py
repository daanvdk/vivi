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


def use_rerender():
    _ctx.static = False
    queue = _ctx.queue
    path = tuple(_ctx.path)
    return lambda: queue.put_nowait(('path', path))


def use_state(initial_value):
    ref = use_ref()
    ref.rerender = use_rerender()

    if not hasattr(ref, 'value'):
        if callable(initial_value):
            initial_value = initial_value()

        def set_value(value):
            if callable(value):
                value = value(ref.value)

            ref.value = value
            ref.rerender()

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

            if hasattr(ref, '__vivi_cleanup'):
                ref.__vivi_cleanup()
                del ref.__vivi_cleanup

            @loop.call_soon
            def wrapped_callback():
                cleanup = callback()
                if callable(cleanup):
                    ref.__vivi_cleanup = lambda: loop.call_soon(cleanup)

    return decorator
