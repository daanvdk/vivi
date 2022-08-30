import asyncio
import json
from pathlib import Path

from vivi import Vivi
from vivi.elements import component, h, fragment
from vivi.hooks import (
    use_state, use_callback, use_future, use_cookie, use_set_cookie,
    use_unset_cookie,
)
from vivi.events import prevent_default
from vivi.urls import link, router


@component
def counter(initial_count=0):
    count, set_count = use_state(initial_count)

    @use_callback(set_count)
    def increment(e):
        set_count(lambda count: count + 1)

    @use_callback(set_count)
    def decrement(e):
        set_count(lambda count: count - 1)

    return h.div(
        h.button(onclick=decrement)('-'),
        f' count: {count} ',
        h.button(onclick=increment)('+'),
    )


@component
def counters():
    return fragment(
        h.h1('Counter 1'),
        counter,
        h.h1('Counter 2'),
        counter(initial_count=10),
    )


@component
def greeter():
    name, set_name = use_state('')

    @use_callback(set_name)
    @prevent_default
    def oninput(e):
        set_name(e.value)

    return fragment(
        h.h1('Greeter'),
        h.input(autofocus=True, value=name, oninput=oninput),
        h.div('Hello, ', name, '!'),
    )


async def get_data():
    await asyncio.sleep(5)
    return {'foo': 'bar'}


@component
def io():
    data_fut, set_data_fut = use_state(None)
    data = use_future(data_fut)

    @use_callback(set_data_fut)
    def onclick(e):
        loop = asyncio.get_running_loop()
        set_data_fut(loop.create_task(get_data()))

    return fragment(
        h.h1('IO'),
        h.div(
            'no data fetched'
            if data_fut is None else
            'loading...'
            if data is None else
            h.code(json.dumps(data))
        ),
        h.button(
            onclick=onclick,
            disabled=data_fut is not None and data is None,
        )('get data'),
    )


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
        None if value is None else h.button(onclick=unset)('unset'),
    )


@component
def cookies():
    return fragment(
        cookie(name='foo'),
        cookie(name='bar'),
        cookie(name='baz'),
    )


@component
def examples():
    return h.html(
        h.head(h.link(rel='stylesheet', href='/static/main.css')),
        h.body(
            h.ul(
                h.li(link(to='/counters', add_active=True)('Counters')),
                h.li(link(to='/greeter', add_active=True)('Greeter')),
                h.li(link(to='/io', add_active=True)('IO')),
                h.li(link(to='/cookies', add_active=True)('Cookies')),
            ),
            router(
                ('/', counters),
                ('/counters', counters),
                ('/greeter', greeter),
                ('/io', io),
                ('/cookies', cookies),
                not_found=h.p('Page not found.'),
            ),
        ),
    )


app = Vivi(
    examples,
    debug=True,
    static_path=Path(__file__).parent / 'static',
)
