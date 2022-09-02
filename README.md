<h1 align="center">
    <img src="https://raw.githubusercontent.com/daanvdk/vivi/master/logo.svg" alt="Vivi" />
</h1>
<p align="center">
    <img src="https://img.shields.io/github/workflow/status/daanvdk/vivi/CI" alt="CI Status" />
    <a href="https://codecov.io/gh/daanvdk/vivi"><img src="https://img.shields.io/codecov/c/gh/daanvdk/vivi" alt="Coverage" /></a>
    <a href="https://pypi.org/project/vivi"><img src="https://img.shields.io/pypi/v/vivi" alt="Version" /></a>
</p>

A server side component based web framework.

```python
from vivi import Vivi
from vivi.hooks import use_state, use_callback
from vivi.events import prevent_default
from vivi.elements import component, fragment, h


@component
def hello_world():
    name, set_name = use_state('World')

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
