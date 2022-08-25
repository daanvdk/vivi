from .paths import Paths


def create_context(initial_value=None):
    from .elements import component, fragment
    from .hooks import _ctx, use_ref

    key = object()

    def get_context():
        try:
            res = _ctx.contexts[key]
        except KeyError:
            if callable(initial_value):
                value = initial_value()
            else:
                value = initial_value
            res = (value, Paths(), Paths())
            _ctx.contexts[key] = res
        return res

    @component
    def context_provider(value, children=()):
        initial_value, providers, receivers = get_context()
        path = tuple(_ctx.path)

        if path not in providers or providers[path] is not value:
            providers[path] = value
            _ctx.rerender_paths.update(
                (path, None)
                for path in receivers.children(path, providers)
            )

        ref = use_ref()
        if not hasattr('ref', '_vivi_cleanup'):
            def cleanup():
                del providers[path]

            ref._vivi_cleanup = cleanup

        return fragment(*children)

    def use_context():
        initial_value, providers, receivers = get_context()
        path = tuple(_ctx.path)

        ref = use_ref()
        if not hasattr(ref, '_vivi_cleanup'):
            receivers[path] = None

            def cleanup():
                del receivers[path]

            ref._vivi_cleanup = cleanup

        try:
            parent = providers.closest_parent(path)
        except KeyError:
            return initial_value
        else:
            return providers[parent]

    return context_provider, use_context
