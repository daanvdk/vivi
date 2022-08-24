from vivi import Vivi
from vivi.element import component, h, fragment, link
from vivi.hooks import use_url


@component
def navigation():
    url = use_url()

    return fragment(
        h.ul(
            h.li(link(to='/foo')('foo')),
            h.li(link(to='/bar')('bar')),
            h.li(link(to='/baz')('baz')),
        ),
        h.p(
            'This is the foo page.'
            if url == '/foo' else
            'This is the bar page.'
            if url == '/bar' else
            'This is the baz page.'
            if url == '/baz' else
            f'Page not found: {url}',
        ),
    )


app = Vivi(navigation)
