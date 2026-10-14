import logging
import uuid
from pathlib import PurePath

from fastapi import HTTPException, UploadFile

from utils.spaces import SPACES_BUCKET, spaces_client


MAX_ASSIGNMENT_PDF_BYTES = 10 * 1024 * 1024
logger = logging.getLogger(__name__)


async def upload_assignment_pdf(
    student_id: int,
    assignment_id: int,
    upload: UploadFile,
) -> tuple[str, str]:
    filename = PurePath(upload.filename or "").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Submission must be a PDF file")
    if upload.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Submission must be a PDF file")

    content = await upload.read(MAX_ASSIGNMENT_PDF_BYTES + 1)
    if len(content) > MAX_ASSIGNMENT_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Assignment PDF must be 10 MB or smaller",
        )
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF")

    object_key = (
        f"assignment-submissions/{student_id}/{assignment_id}/{uuid.uuid4()}.pdf"
    )
    try:
        spaces_client.put_object(
            Bucket=SPACES_BUCKET,
            Key=object_key,
            Body=content,
            ContentType="application/pdf",
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Assignment PDF upload failed: {error}",
        )

    return object_key, filename


def assignment_pdf_url(object_key: str | None) -> str | None:
    if not object_key:
        return None
    try:
        return spaces_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": SPACES_BUCKET, "Key": object_key},
            ExpiresIn=900,
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to create a private assignment PDF link: {error}",
        )


def delete_assignment_pdf(object_key: str | None) -> None:
    if not object_key:
        return
    try:
        spaces_client.delete_object(Bucket=SPACES_BUCKET, Key=object_key)
    except Exception as error:
        logger.warning(
            "Unable to delete replaced assignment PDF %s: %s",
            object_key,
            error,
            exc_info=True,
        )
