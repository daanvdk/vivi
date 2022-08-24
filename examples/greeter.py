from vivi import Vivi
from vivi.element import component, fragment, h
from vivi.hooks import use_state, use_callback


@component
def greeter():
    name, set_name = use_state('World')

    @use_callback(set_name)
    def oninput(e):
        set_name(e.value)

    return fragment(
        h.input(value=name, oninput=oninput),
        h.div('Hello, ', name, '!'),
    )


app = Vivi(greeter)
