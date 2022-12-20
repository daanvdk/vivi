from pathlib import Path

from vivi import Vivi
from vivi.elements import component, h
from vivi.urls import link, router

from .counters_page import counters
from .greeter_page import greeter
from .io_page import io
from .cookies_page import cookies
from .file_upload_page import file_upload
from .chat_page import chat


@component
def examples():
    return h.html(
        h.head(h.link(rel='stylesheet', href='/static/main.css')),
        h.body(
            h.ul({'class': 'nav'})(
                h.li(link(to='/counters', add_active=True)('Counters')),
                h.li(link(to='/greeter', add_active=True)('Greeter')),
                h.li(link(to='/io', add_active=True)('IO')),
                h.li(link(to='/cookies', add_active=True)('Cookies')),
                h.li(link(to='/file-upload', add_active=True)('File Upload')),
                h.li(link(to='/chat', add_active=True)('Chat')),
            ),
            router(
                ('/', counters),
                ('/counters', counters),
                ('/greeter', greeter),
                ('/io', io),
                ('/cookies', cookies),
                ('/file-upload', file_upload),
                ('/chat', chat),
                not_found=h.p('Page not found.'),
            ),
        ),
    )


app = Vivi(
    examples,
    debug=True,
    static_path=Path(__file__).parent / 'static',
)
