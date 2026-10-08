from io import BytesIO
from typing import Protocol


class ThumbnailStoragePort(Protocol):
    """Output port: uploads thumbnail bytes to object storage and returns the URI."""

    def upload_file(self, file_stream: BytesIO, file_path: str, content_type: str = "image/jpeg") -> str: ...
