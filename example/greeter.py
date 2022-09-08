from vivi.elements import component, h, fragment
from vivi.hooks import use_state, use_callback
from vivi.events import prevent_default


@component
def greeter():
    name, set_name = use_state('')

    @use_callback(set_name)
    @prevent_default
    def oninput(e):
        set_name(e.value)

    @use_callback()
    def ref(node):
        if node is not None:
            node.focus()

    return fragment(
        h.h1('Greeter'),
        h.input(value=name, oninput=oninput, ref=ref),
        h.div('Hello, ', name, '!'),
    )
