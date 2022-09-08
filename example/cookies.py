from vivi.elements import component, h, fragment
from vivi.hooks import (
    use_cookie, use_state, use_set_cookie, use_unset_cookie, use_callback,
)
from vivi.events import prevent_default


@component
def cookie(name):
    value = use_cookie(name, None)
    new_value, set_new_value = use_state('')
    set_cookie = use_set_cookie()
    unset_cookie = use_unset_cookie()

    @use_callback(set_new_value)
    @prevent_default
    def oninput(e):
        set_new_value(e.value)

    @use_callback(set_cookie, name, new_value, set_new_value)
    @prevent_default
    def set(e):
        set_cookie(name, new_value)
        set_new_value('')

    @use_callback(unset_cookie, name)
    @prevent_default
    def unset(e):
        unset_cookie(name)

    return h.div(
        h.h1(f'Cookie: {name}'),
        h.div('no value set' if value is None else f'current_value: {value}'),
        h.input(value=new_value, oninput=oninput),
        h.button(onclick=set)('set'),
        value is not None and h.button(onclick=unset)('unset'),
    )


@component
def cookies():
    return fragment(
        cookie(name='foo'),
        cookie(name='bar'),
        cookie(name='baz'),
    )
