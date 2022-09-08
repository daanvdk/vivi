import asyncio
import json

from vivi.elements import component, fragment, h
from vivi.hooks import use_state, use_future, use_callback


async def get_data():
    await asyncio.sleep(5)
    return {'foo': 'bar'}


@component
def io():
    data_fut, set_data_fut = use_state(None)
    data = use_future(data_fut)

    @use_callback(set_data_fut)
    def onclick(e):
        set_data_fut(asyncio.create_task(get_data()))

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
