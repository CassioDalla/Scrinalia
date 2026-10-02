import time
from io import BytesIO

import requests
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from core.database import get_db
from core.logger import logger
from core.storage import S3Storage
from domains.archive.models import ArchiveDocument


def download_image_to_memory(url: str) -> BytesIO | None:
    """
    Performs the HTTP download disguised as a user browser and processes
    the image bytes, converting everything to an optimized JPEG standard.

    Args:
        url (str): The direct public link to the original image.

    Returns:
        BytesIO | None: Memory buffer containing the JPEG image, or None on failure.
    """

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))

            # Converts PNG/GIF images with transparency to safe RGB
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            output_buffer = BytesIO()
            img.save(output_buffer, format="JPEG", quality=100, subsampling=0)

            # Returns the read pointer to the beginning of the file
            output_buffer.seek(0)

            return output_buffer
        else:
            logger.warning(f"⚠️ HTTP error {response.status_code} accessing: {url}")
            return None
    except Exception as e:
        logger.error(f"❌ Network failure downloading {url}: {e}")
        return None


def execute(db: Session) -> None:
    """
    Asynchronous orchestrator responsible for migrating images from an ephemeral
    external link to a secure Object Storage (e.g. MinIO/S3).

    Scans the Fact table for documents that have the original link but
    whose local storage URI is still empty.
    """
    logger.info("📸 Starting the Thumbnails Worker...")

    storage = S3Storage()

    # Fetches images that have not yet been uploaded AND that have not failed permanently
    query = select(ArchiveDocument).where(
        ArchiveDocument.original_thumbnail_url.is_not(None)
        & ArchiveDocument.storage_thumbnail_uri.is_(None)
        & ~ArchiveDocument.execution_log.has_key("thumbnail_failed")
    )

    pending_documents = db.scalars(query).yield_per(50)

    processed = 0
    successes = 0

    for doc in pending_documents:
        try:
            with db.begin_nested():
                target_url = doc.original_thumbnail_url

                if not target_url:
                    continue

                file_name = f"thumb_{doc.description_id}.jpg"
                bucket_path = f"thumbnails/{file_name}"

                image_bytes = download_image_to_memory(target_url)

                if image_bytes:
                    final_uri = storage.upload_file(file_stream=image_bytes, file_path=bucket_path)
                    doc.storage_thumbnail_uri = final_uri
                    successes += 1
                else:
                    # On download failure, stamps it in the JSONB so it is not retried on the next loop
                    new_log = dict(doc.execution_log)
                    new_log["thumbnail_failed"] = "True"
                    doc.execution_log = new_log
                    flag_modified(doc, "execution_log")

                processed += 1

                if processed % 50 == 0:
                    logger.info(f"⏳ Progress: {processed} images analyzed...")

                time.sleep(0.5)

        except Exception as e:
            logger.error(f"❌ Catastrophic error in document {doc.description_id}: {e}")
            continue

    db.commit()
    logger.success(f"✅ Thumbnails Worker finished! {successes} images saved successfully out of {processed} attempts.")


if __name__ == "__main__":
    with get_db() as db:
        execute(db)
