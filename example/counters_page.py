from vivi.elements import component, h, fragment
from vivi.hooks import use_state, use_callback


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
