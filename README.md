# Vivi
A server side component based web framework.

```python
from vivi import Vivi
from vivi.hooks import use_state, use_callback
from vivi.events import prevent_default
from vivi.elements import component, fragment, h


@component
def hello_world():
    name, set_name = use_state()

    @use_callback(set_name)
    @prevent_default
    def oninput(e):
        set_name(e.value)

    return fragment(
        h.label('Name:'),
        h.input(value=name, oninput=oninput),
        h.p(f'Hello, {name}!'),
    )


app = Vivi(hello_world)
```
