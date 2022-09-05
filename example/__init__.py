import asyncio
import json
from mimetypes import guess_type, guess_extension
from pathlib import Path
from tempfile import NamedTemporaryFile

from vivi import Vivi
from vivi.elements import component, h, fragment
from vivi.hooks import (
    use_state, use_callback, use_future, use_cookie, use_set_cookie,
    use_unset_cookie, use_effect, use_file, use_memo,
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

    @use_callback()
    def ref(node):
        if node is not None:
            node.focus()

    return fragment(
        h.h1('Greeter'),
        h.input(value=name, oninput=oninput, ref=ref),
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
        value is not None and h.button(onclick=unset)('unset'),
    )


@component
def cookies():
    return fragment(
        cookie(name='foo'),
        cookie(name='bar'),
        cookie(name='baz'),
    )


@component
def file_upload():
    file_path, set_file_path = use_state()

    @use_effect(file_path)
    def cleanup_file_path():
        if file_path is not None:
            return file_path.unlink

    @use_callback(set_file_path)
    def oninput(e):
        suffix = guess_extension(e.file.content_type)
        f = NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            f.write(e.file.content)
        finally:
            f.close()
        set_file_path(Path(f.name))

    file_url = use_file(file_path)

    @use_memo(file_path)
    def content_type():
        if file_path is None:
            return None
        return guess_type(file_path)[0]

    return fragment(
        h.input(type='file', oninput=oninput),
        file_url is not None and (
            h.a(href=file_url, download=True)('Download'),
        ),
        content_type is not None and content_type.startswith('image/') and (
            h.img(src=file_url),
        ),
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
                h.li(link(to='/file-upload', add_active=True)('File Upload')),
            ),
            router(
                ('/', counters),
                ('/counters', counters),
                ('/greeter', greeter),
                ('/io', io),
                ('/cookies', cookies),
                ('/file-upload', file_upload),
                not_found=h.p('Page not found.'),
            ),
        ),
    )


app = Vivi(
    examples,
    debug=True,
    static_path=Path(__file__).parent / 'static',
)
