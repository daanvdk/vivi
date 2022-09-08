from contextlib import asynccontextmanager
from types import SimpleNamespace

from vivi.elements import component, h, fragment
from vivi.hooks import use_state, use_callback, use_effect
from vivi.events import prevent_default
from vivi.shared import create_shared


class ChatUser:

    def __init__(self, chat, name):
        self._chat = chat
        self._name = name

    def exit(self):
        del self._chat._users[self._name]

        for callbacks in self._chat._users.values():
            callbacks.on_left(self._name)

        self._chat = None

    def send(self, message):
        for callbacks in self._chat._users.values():
            callbacks.on_message(self._name, message)


class Chat:

    def __init__(self):
        self._users = {}

    def enter(self, name, on_message, on_joined, on_left):
        if name in self._users:
            raise ValueError('name already in use')

        self._users[name] = SimpleNamespace(
            on_message=on_message,
            on_joined=on_joined,
            on_left=on_left,
        )

        for callbacks in self._users.values():
            callbacks.on_joined(name)

        return ChatUser(self, name)


@asynccontextmanager
async def chat_manager():
    yield Chat()


shared_chat, use_chat = create_shared(chat_manager)


def focus(node):
    node.focus()


@component
def name_form(on_submit, error):
    name, set_name = use_state('')

    @use_callback(set_name)
    @prevent_default
    def oninput(e):
        set_name(e.value)

    @use_callback(name, on_submit)
    @prevent_default
    def onsubmit(e):
        on_submit(name)

    return h.form(onsubmit=onsubmit)(
        error and h.p(error),
        h.label('Name:'),
        h.input(name='name', value=name, oninput=oninput, ref=focus),
        h.button(type='submit')('Submit'),
    )


@component
def chat_room(name, on_error):
    chat = use_chat()
    user, set_user = use_state()
    events, set_events = use_state(())
    message, set_message = use_state('')

    @use_callback(set_events)
    def on_message(name, message):
        set_events(lambda events: (*events, ('message', name, message)))

    @use_callback(set_events)
    def on_joined(name):
        set_events(lambda events: (*events, ('joined', name)))

    @use_callback(set_events)
    def on_left(name):
        set_events(lambda events: (*events, ('left', name)))

    @use_effect(chat, name, on_message)
    def enter_chat():
        try:
            user = chat.enter(name, on_message, on_joined, on_left)
        except Exception as e:
            set_user(None)
            on_error(str(e))
        else:
            set_user(user)
            return user.exit

    @use_callback(set_message)
    @prevent_default
    def oninput(e):
        set_message(e.value)

    @use_callback(user, message)
    @prevent_default
    def send(e):
        user.send(message)
        set_message('')

    if user is None:
        return 'Joining...'

    event_elems = []
    for event in events:
        if event[0] == 'message':
            _, name_, message_ = event
            event_elems.append(h.li(h.b(name_), ': ', message_))
        elif event[0] == 'joined':
            _, name_ = event
            event_elems.append(h.li(h.i(h.b(name_), ' joined.')))
        elif event[0] == 'left':
            _, name_ = event
            event_elems.append(h.li(h.i(h.b(name_), ' left.')))
        else:
            raise ValueError(f'unknown message type: {event[0]}')

    return fragment(
        h.ul({'class': 'chat'})(event_elems),
        h.form(onsubmit=send)(
            h.label('Message:'),
            h.input(name='message', value=message, oninput=oninput, ref=focus),
            h.button(type='submit')('Send'),
        ),
    )


@component
def chat():
    name, set_name = use_state(None)
    error, set_error = use_state(None)

    @use_callback(set_name)
    def on_submit(name):
        set_name(name)

    @use_callback(set_name, set_error)
    def on_error(error):
        set_name(None)
        set_error(error)

    if name is None:
        return name_form(on_submit=on_submit, error=error)
    else:
        return chat_room(name=name, on_error=on_error)
