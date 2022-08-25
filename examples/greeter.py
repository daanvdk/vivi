from vivi import Vivi
from vivi.elements import component, fragment, h
from vivi.hooks import use_state, use_callback
from vivi.events import prevent_default


@component
def greeter():
    name, set_name = use_state('')

    @use_callback(set_name)
    @prevent_default
    def oninput(e):
        set_name(e.value)

    return fragment(
        h.input(autofocus=True, value=name, oninput=oninput),
        h.div('Hello, ', name, '!'),
    )


app = Vivi(greeter, debug=True)
