class CallbackWrapper:

    def __init__(self, callback, key, value):
        self.callback = callback
        self.key = key
        self.value = value

    def __eq__(self, other):
        return (
            isinstance(other, CallbackWrapper) and
            other.callback == self.callback and
            other.key == self.key and
            other.value == self.value
        )

    def __call__(self, *args, **kwargs):
        return self.callback(*args, **kwargs)


def prevent_default(callback):
    return CallbackWrapper(callback, 'prevent_default', True)


def stop_propagation(callback):
    return CallbackWrapper(callback, 'stop_propagation', True)


def stop_immediate_propagation(callback):
    return CallbackWrapper(callback, 'stop_immediate_propagation', True)
