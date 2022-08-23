from vivi.elements import component
from vivi.serve import serve


@component
def todos():
    return 'Hello, World!'


app = serve(todos)
