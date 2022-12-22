from .paths import Paths


def create_context(initial_value=None):
    from .elements import component, fragment
    from .hooks import CONTEXT, use_ref

    key = object()

    def get_context():
        ctx = CONTEXT.get()
        try:
            res = ctx.contexts[key]
        except KeyError:
            if callable(initial_value):
                value = initial_value()
            else:
                value = initial_value
            res = (value, Paths(), Paths())
            ctx.contexts[key] = res
        return res

    @component
    def context_provider(value, children=()):
        ctx = CONTEXT.get()
        initial_value, providers, receivers = get_context()
        path = tuple(ctx.path)

        if path not in providers or providers[path] is not value:
            providers[path] = value
            ctx.rerender_paths.update(
                (path, None)
                for path in receivers.children(path, providers)
            )

        ref = use_ref()
        if not hasattr('ref', '_vivi_cleanup'):
            def cleanup():
                del providers[path]

            ref._vivi_cleanup = cleanup

        return fragment(*children)

    context_provider._vivi_context_key = key

    def use_context():
        ctx = CONTEXT.get()
        initial_value, providers, receivers = get_context()
        path = tuple(ctx.path)

        ref = use_ref()
        if not hasattr(ref, '_vivi_cleanup'):
            receivers[path] = receivers.get(path, 0) + 1

            def cleanup():
                receivers[path] -= 1
                if not receivers[path]:
                    del receivers[path]

            ref._vivi_cleanup = cleanup

        try:
            parent = providers.closest_parent(path)
        except KeyError:
            return initial_value
        else:
            return providers[parent]

    return context_provider, use_context
