import json
import re

from starlette.testclient import TestClient

from example import app


def test_counter():
    with TestClient(app) as client:
        res = client.get('/counters')
        assert res.status_code == 200
        assert res.headers['content-type'] == 'text/html; charset=utf-8'

        before_script, socket_url, after_script = re.fullmatch(
            (
                r'(.*)<script>.*?'
                r'new WebSocket\(("(?:[^"\\]|\\.)*")\)'
                r'.*?</script>(.*)'
            ),
            res.content.decode(),
            re.S | re.M,
        ).groups()

        assert before_script == '<!doctype html><html><head>'
        assert after_script == (
            '<link rel="stylesheet" href="/static/main.css"></link>'
            '</head>'
            '<body>'
            '<ul class="nav">'
            '<li>'
            '<a href="/counters" onclick="call(event, true, false)" '
            'class="active">'
            'Counters'
            '</a>'
            '</li>'
            '<li>'
            '<a href="/greeter" onclick="call(event, true, false)">'
            'Greeter'
            '</a>'
            '</li>'
            '<li>'
            '<a href="/io" onclick="call(event, true, false)">IO</a>'
            '</li>'
            '<li>'
            '<a href="/cookies" onclick="call(event, true, false)">'
            'Cookies'
            '</a>'
            '</li>'
            '<li>'
            '<a href="/file-upload" onclick="call(event, true, false)">'
            'File Upload'
            '</a>'
            '</li>'
            '<li>'
            '<a href="/chat" onclick="call(event, true, false)">'
            'Chat'
            '</a>'
            '</li>'
            '</ul>'
            '<h1>Counter 1</h1>'
            '<div>'
            '<button onclick="call(event, false, false)">-</button>'
            ' count: 0 '
            '<button onclick="call(event, false, false)">+</button>'
            '</div>'
            '<h1>Counter 2</h1>'
            '<div>'
            '<button onclick="call(event, false, false)">-</button>'
            ' count: 10 '
            '<button onclick="call(event, false, false)">+</button>'
            '</div>'
            '</body>'
            '</html>'
        )

        socket_url = json.loads(socket_url)
        assert socket_url.startswith('ws://testserver/')
        socket_path = socket_url[len('ws://testserver'):]

        with client.websocket_connect(socket_path) as socket:
            # Increment first counter
            socket.send_json(['click', 1, 1, 2, 2, {}])
            assert socket.receive_json() == [
                ['replace', 1, 1, 2, 1, ' count: 1 '],
            ]
            # Go to greeter page
            socket.send_json(["click", 1, 1, 0, 1, 0, {}])
            assert socket.receive_json() == [
                ['push_url', '/greeter'],
                ['unset', 1, 1, 0, 0, 0, 'class'],
                ['set', 1, 1, 0, 1, 0, 'class', 'active'],
                ['replace', 1, 1, 1, ['h1', {}, 'Greeter']],
                ['replace', 1, 1, 2, ['input', {
                    'oninput': 'call(event, true, false)',
                    'value': '',
                }]],
                ['replace', 1, 1, 3, ['div', {}, 'Hello, !']],
                ['remove', 1, 1, 4],
            ]
            assert socket.receive_json() == [
                ['focus', 1, 1, 2],
            ]
            # Type world
            socket.send_json(["input", 1, 1, 2, {'value': 'World'}])
            assert socket.receive_json() == [
                ['set', 1, 1, 2, 'value', 'World'],
                ['replace', 1, 1, 3, 0, 'Hello, World!'],
            ]
