import asyncio
import json

from vivi import Vivi
from vivi.elements import component, h, fragment
from vivi.hooks import use_state, use_callback, use_future
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
            json.dumps(data)
        ),
        h.button(
            onclick=onclick,
            disabled=data_fut is not None and data is None,
        )('get data'),
    )


@component
def examples():
    return fragment(
        h.ul(
            h.li(link(to='/counters')('Counters')),
            h.li(link(to='/greeter')('Greeter')),
            h.li(link(to='/io')('IO')),
        ),
        router(
            ('/', counters),
            ('/counters', counters),
            ('/greeter', greeter),
            ('/io', io),
            not_found=h.p('Page not found.'),
        ),
    )


app = Vivi(examples, debug=True)
