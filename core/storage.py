from io import BytesIO

import boto3
from botocore.client import Config
from pydantic import SecretStr

from core.config import settings
from core.logger import logger


def _reveal(secret: SecretStr | None) -> str | None:
    """Unwraps a SecretStr for the S3 client, which expects plain credentials."""
    return secret.get_secret_value() if secret is not None else None


class S3Storage:
    def __init__(self) -> None:
        self.bucket = settings.S3_BUCKET_NAME

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=_reveal(settings.S3_ACCESS_KEY),
            aws_secret_access_key=_reveal(settings.S3_SECRET_KEY),
            config=Config(signature_version="s3v4"),
        )

    def upload_file(self, file_stream: BytesIO, file_path: str, content_type: str = "image/jpeg") -> str:
        try:
            self.client.upload_fileobj(file_stream, self.bucket, file_path, ExtraArgs={"ContentType": content_type})
            return f"s3://{self.bucket}/{file_path}"
        except Exception as e:
            logger.error(f"❌ Error uploading file to S3: {e}")
            raise
