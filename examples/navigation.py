from vivi import Vivi
from vivi.elements import component, h, fragment
from vivi.urls import link, router


@component
def navigation():
    return fragment(
        h.ul(
            h.li(link(to='/foo')('foo')),
            h.li(link(to='/bar')('bar')),
            h.li(link(to='/baz')('baz')),
        ),
        router(
            ('/foo', h.p('This is the foo page')),
            ('/bar', h.p('This is the bar page')),
            ('/baz', h.p('This is the baz page')),
            not_found=h.p('Page not found.'),
        ),
    )


app = Vivi(navigation, debug=True)
