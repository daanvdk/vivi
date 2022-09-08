from mimetypes import guess_extension, guess_type
from pathlib import Path
from tempfile import NamedTemporaryFile

from vivi.elements import component, fragment, h
from vivi.hooks import use_state, use_effect, use_callback, use_file, use_memo


@component
def file_upload():
    file_path, set_file_path = use_state()

    @use_effect(file_path)
    def cleanup_file_path():
        if file_path is not None:
            return file_path.unlink

    @use_callback(set_file_path)
    def oninput(e):
        suffix = guess_extension(e.file.content_type)
        f = NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            f.write(e.file.content)
        finally:
            f.close()
        set_file_path(Path(f.name))

    file_url = use_file(file_path)

    @use_memo(file_path)
    def content_type():
        if file_path is None:
            return None
        return guess_type(file_path)[0]

    return fragment(
        h.input(type='file', oninput=oninput),
        h.div(
            file_url is None and 'No file uploaded yet.',
            file_url is not None and (
                h.a(href=file_url, download=True)('Download'),
            ),
            (
                content_type is not None and
                content_type.startswith('image/') and
                h.img(src=file_url)
            ),
        ),
    )
