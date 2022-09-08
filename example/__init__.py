from pathlib import Path

from vivi import Vivi
from vivi.elements import component, h
from vivi.urls import link, router

from .counters import counters
from .greeter import greeter
from .io import io
from .cookies import cookies
from .file_upload import file_upload


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
