from vivi.elements import component, h, fragment
from vivi.hooks import (
    use_state, use_callback, use_effect, use_publish, use_subscribe,
)
from vivi.events import prevent_default


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
    publish = use_publish()
    events, set_events = use_state(())
    message, set_message = use_state('')

    @use_effect(name)
    def on_name():
        publish('joined', name)
        return lambda: publish('left', name)

    @use_subscribe('message')
    @use_callback(set_events)
    def on_message(message):
        set_events(lambda events: (*events, ('message', *message)))

    @use_subscribe('joined')
    @use_callback(set_events, name)
    def on_joined(name):
        set_events(lambda events: (*events, ('joined', name)))

    @use_subscribe('left')
    @use_callback(set_events)
    def on_left(name):
        set_events(lambda events: (*events, ('left', name)))

    @use_callback(set_message)
    @prevent_default
    def oninput(e):
        set_message(e.value)

    @use_callback(publish, name, message)
    @prevent_default
    def send(e):
        publish('message', (name, message))
        set_message('')

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
