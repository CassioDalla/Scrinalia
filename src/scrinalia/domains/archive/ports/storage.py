from io import BytesIO
from typing import Protocol


class ThumbnailStoragePort(Protocol):
    """Output port: uploads thumbnail bytes to object storage and returns the URI."""

    def ensure_bucket(self) -> None:
        """Makes the destination writable before the first upload, or refuses with a sentence."""
        raise NotImplementedError

    def upload_file(self, file_stream: BytesIO, file_path: str, content_type: str = "image/jpeg") -> str:
        raise NotImplementedError
