import asyncio
from unittest.mock import patch

from vivi.test import TestSession

from example import app


def test_counter():
    with TestSession(app, url='/counters') as session:
        counter_1 = session.find('div:eq(0)')
        counter_2 = session.find('div:eq(1)')

        assert counter_1.has_text('- count: 0 +')
        assert counter_2.has_text('- count: 10 +')

        assert counter_1.find('button:text("+")').click()

        assert counter_1.has_text('- count: 1 +')
        assert counter_2.has_text('- count: 10 +')

        for _ in range(3):
            assert counter_1.find('button:text("+")').click()
        for _ in range(5):
            assert counter_2.find('button:text("-")').click()
        for _ in range(2):
            assert counter_1.find('button:text("-")').click()

        assert counter_1.has_text('- count: 2 +')
        assert counter_2.has_text('- count: 5 +')


def test_greeter():
    with TestSession(app, url='/greeter') as session:
        input = session.find('input')
        output = session.find('div')

        assert input.has_prop('value', '')
        assert output.has_text('Hello, !')

        assert input.input('World')

        assert input.has_prop('value', 'World')
        assert output.has_text('Hello, World!')

        assert input.input('Vivi')

        assert input.has_prop('value', 'Vivi')
        assert output.has_text('Hello, Vivi!')


def test_io():
    with (
        patch('example.get_data') as get_data_mock,
        TestSession(app, url='/io') as session,
    ):
        queue = asyncio.Queue()
        get_data_mock.side_effect = queue.get

        output = session.find('div')
        button = session.find('button')

        assert output.has_text('no data fetched')
        assert button.not_has_prop('disabled', True)
        assert button.click()

        assert output.has_text('loading...')
        assert button.has_prop('disabled', True)

        get_data_mock.assert_called_once_with()
        get_data_mock.reset_mock()
        queue.put_nowait('foobar')

        assert output.has_text('"foobar"')
        assert button.not_has_prop('disabled', True)
        assert button.click()

        assert output.has_text('loading...')
        assert button.has_prop('disabled', True)

        get_data_mock.assert_called_once_with()
        queue.put_nowait('foobarbaz')

        assert output.has_text('"foobarbaz"')
        assert button.not_has_prop('disabled', True)


def test_cookies():
    with TestSession(app, url='/cookies', cookies={'foo': '123'}) as session:
        def check(cookie, cookie_value, input_value):
            root = session.find(f'h1:text("Cookie: {cookie}")').parent()

            if cookie_value is None:
                assert session.not_has_cookie(cookie)
                assert root.find('div').has_text('no value set')
                assert root.find('button:text("unset")').not_exists()
            else:
                assert session.has_cookie(cookie, cookie_value)
                assert root.find('div').has_text(
                    f'current_value: {cookie_value}'
                )
                assert root.find('button:text("unset")')

            assert root.find('input').has_prop('value', input_value)
            assert root.find('button:text("set")')

        check('foo', '123', '')
        check('bar', None, '')
        check('baz', None, '')

        bar = session.find('h1:text("Cookie: bar")').parent()
        assert bar.find('input').input('456')

        check('foo', '123', '')
        check('bar', None, '456')
        check('baz', None, '')

        assert bar.find('button:text("set")').click()

        check('foo', '123', '')
        check('bar', '456', '')
        check('baz', None, '')

        foo = session.find('h1:text("Cookie: foo")').parent()
        assert foo.find('button:text("unset")').click()

        check('foo', None, '')
        check('bar', '456', '')
        check('baz', None, '')


def test_file_upload():
    with TestSession(app, url='/file-upload') as session:
        assert session.find('div').has_text('No file uploaded yet.')

        assert session.find('input[type="file"]').input(
            content_type='text/plain',
            content=b'foobar',
        )
        assert session.find('div > *').has_len(1)
        link = (
            session.find('div > *')
            .has_tag('a')
            .has_prop('download', True)
            .has_text('Download')
            .get()
        )
        assert session.has_file(link['href'], b'foobar')

        assert session.find('input[type="file"]').input(
            content_type='image/png',
            content=b'barbaz',
        )
        assert session.find('div > *').has_len(2)
        link = (
            session.find('div > :eq(0)')
            .has_tag('a')
            .has_prop('download', True)
            .has_text('Download')
            .get()
        )
        img = (
            session.find('div > :eq(1)')
            .has_tag('img')
            .get()
        )
        assert session.has_file(link['href'], b'barbaz')
        assert link['href'] == img['src']


def test_navigation():
    with TestSession(app, url='/does-not-exist') as session:
        assert session.find('.active').not_exists()
        assert session.find('p').has_text('Page not found.')

        assert session.find('a[href="/counters"]').click()
        assert session.has_url('/counters')
        assert session.find('.active').has_prop('href', '/counters')
        assert session.find('h1').has_text('Counter 1Counter 2')

        assert session.find('a[href="/greeter"]').click()
        assert session.has_url('/greeter')
        assert session.find('.active').has_prop('href', '/greeter')
        assert session.find('h1').has_text('Greeter')

        session.prev()
        assert session.has_url('/counters')
        assert session.find('.active').has_prop('href', '/counters')
        assert session.find('h1').has_text('Counter 1Counter 2')

        session.prev()
        assert session.has_url('/does-not-exist')
        assert session.find('.active').not_exists()
        assert session.find('p').has_text('Page not found.')

        session.next()
        assert session.has_url('/counters')
        assert session.find('.active').has_prop('href', '/counters')
        assert session.find('h1').has_text('Counter 1Counter 2')
