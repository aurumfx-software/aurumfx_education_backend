import logging
import uuid
from pathlib import PurePath

from fastapi import HTTPException, UploadFile

from utils.spaces import SPACES_BUCKET, spaces_client


MAX_STUDY_MATERIAL_PDF_BYTES = 10 * 1024 * 1024
logger = logging.getLogger(__name__)


async def upload_study_material_pdf(
    course_id: int,
    staff_id: int,
    upload: UploadFile,
) -> tuple[str, str]:
    filename = PurePath(upload.filename or "").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Study material must be a PDF file")
    if upload.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Study material must be a PDF file")

    content = await upload.read(MAX_STUDY_MATERIAL_PDF_BYTES + 1)
    if len(content) > MAX_STUDY_MATERIAL_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Study material PDF must be 10 MB or smaller",
        )
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid PDF",
        )

    object_key = (
        f"course-study-materials/{course_id}/{staff_id}/{uuid.uuid4()}.pdf"
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
            detail=f"Study material upload failed: {error}",
        )

    return object_key, filename


def study_material_download_url(object_key: str, filename: str) -> str:
    safe_filename = (
        PurePath(filename)
        .name.replace('"', "")
        .replace("\r", "")
        .replace("\n", "")
    )
    try:
        return spaces_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": SPACES_BUCKET,
                "Key": object_key,
                "ResponseContentType": "application/pdf",
                "ResponseContentDisposition": f'attachment; filename="{safe_filename}"',
            },
            ExpiresIn=900,
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to create study material download link: {error}",
        )


def delete_study_material_pdf(object_key: str) -> None:
    try:
        spaces_client.delete_object(Bucket=SPACES_BUCKET, Key=object_key)
    except Exception as error:
        logger.warning(
            "Unable to delete study material PDF %s: %s",
            object_key,
            error,
            exc_info=True,
        )
