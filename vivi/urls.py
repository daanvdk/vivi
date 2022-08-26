from starlette.routing import compile_path

from .elements import component, h, fragment, Component
from .hooks import use_url, use_push_url, use_callback, use_ref
from .events import prevent_default


@component
def link(to, children, add_active=False, **props):
    url = use_url()
    push_url = use_push_url()

    current = url == to

    @use_callback(push_url, to, current)
    @prevent_default
    def onclick(e):
        if not current:
            push_url(to)

    if add_active and url == to:
        try:
            props['class'] = f'{props["class"]} active'
        except KeyError:
            props['class'] = 'active'

    return h.a(href=to, onclick=onclick, **props)(*children)


@component
def router(children=(), not_found=fragment):
    ref = use_ref(routes=[], url=None, index=None, values=None)
    url = use_url()

    first_change = None

    if url != ref.url:
        ref.url = url
        ref.index = None
        first_change = 0

    for index, (pattern, elem) in enumerate(children):
        try:
            prev_pattern, prev_regex, prev_converters, _ = ref.routes[index]
        except IndexError:
            if first_change is None:
                first_change = index
            regex, _, converters = compile_path(pattern)
            ref.routes.append((pattern, regex, converters, elem))
        else:
            if pattern == prev_pattern:
                regex = prev_regex
                converters = prev_converters
            else:
                if first_change is None:
                    first_change = index
                regex, _, converters = compile_path(pattern)
            ref.routes[index] = (pattern, regex, converters, elem)

    if len(ref.routes) > len(children):
        if first_change is None:
            first_change = len(children)
        ref.routes[len(children):] = []

    if (
        first_change is not None and
        (ref.index is None or ref.index >= first_change)
    ):
        for index in range(first_change, len(ref.routes)):
            _, regex, converters, elem = ref.routes[index]
            match = regex.match(url)
            if match is not None:
                ref.index = index
                ref.values = {
                    key: converters[key].convert(value)
                    for key, value in match.groupdict()
                }
                break
        else:
            ref.index = None
            ref.values = None

    if ref.index is None:
        return not_found
    else:
        elem = ref.routes[ref.index][3]
        if isinstance(elem, Component):
            elem = elem(**ref.values)
        return elem
