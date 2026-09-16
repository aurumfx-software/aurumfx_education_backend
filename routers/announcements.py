from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Form,
    UploadFile,
    File
)

from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Announcement

from schemas.announcement import AnnouncementResponse

from routers.auth import get_current_admin

from utils.spaces import spaces_client, SPACES_BUCKET, SPACES_PUBLIC_URL


router = APIRouter(
    prefix="/announcements"
)


# ==========================================
# DATABASE DEPENDENCY
# ==========================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ==========================================
# CREATE ANNOUNCEMENT
# ADMIN ONLY
# ==========================================

@router.post(
    "/",
    response_model=AnnouncementResponse,
    tags=["Admin"]
)
async def create_announcement(
    title: str = Form(...),
    message: str = Form(...),
    image: UploadFile | None = File(None),

    db: Session = Depends(get_db),

    current_admin=Depends(get_current_admin)
):

    image_url = None

    # ==========================================
    # UPLOAD IMAGE
    # ==========================================

    if image:

        file_extension = image.filename.split(".")[-1]

        file_name = (
            f"announcements/{title.replace(' ', '-').lower()}"
            f"-{image.filename}"
        )

        file_content = await image.read()

        spaces_client.put_object(
            Bucket=SPACES_BUCKET,
            Key=file_name,
            Body=file_content,
            ContentType=image.content_type,
            ACL="public-read"
        )

        image_url = (
            f"{SPACES_PUBLIC_URL}/{file_name}"
        )

    # ==========================================
    # CREATE ANNOUNCEMENT
    # ==========================================

    new_announcement = Announcement(
        title=title,
        message=message,
        image=image_url
    )

    db.add(new_announcement)

    db.commit()

    db.refresh(new_announcement)

    return new_announcement


# ==========================================
# GET ANNOUNCEMENTS
# STUDENT + ADMIN
# ==========================================

@router.get(
    "/",
    response_model=list[AnnouncementResponse],
    tags=["Admin"]
)
def get_announcements(
    db: Session = Depends(get_db)
):

    announcements = db.query(
        Announcement
    ).order_by(
        Announcement.created_at.desc()
    ).all()

    return announcements



# ==========================================
# UPDATE ANNOUNCEMENT
# ADMIN ONLY
# ==========================================

@router.put(
    "/{announcement_id}",
    response_model=AnnouncementResponse,
    tags=["Admin"]
)
async def update_announcement(
    announcement_id: int,
    title: str = Form(...),
    message: str = Form(...),
    image: UploadFile | None = File(None),

    db: Session = Depends(get_db),

    current_admin=Depends(get_current_admin)
):

    announcement = db.query(Announcement).filter(
        Announcement.id == announcement_id
    ).first()

    if not announcement:
        raise HTTPException(
            status_code=404,
            detail="Announcement not found"
        )

    # Update text
    announcement.title = title
    announcement.message = message

    # Upload new image only if provided
    if image:

        file_name = (
            f"announcements/{announcement_id}-{image.filename}"
        )

        file_content = await image.read()

        spaces_client.put_object(
            Bucket=SPACES_BUCKET,
            Key=file_name,
            Body=file_content,
            ContentType=image.content_type,
            ACL="public-read"
        )

        announcement.image = (
            f"{SPACES_PUBLIC_URL}/{file_name}"
        )

    db.commit()
    db.refresh(announcement)

    return announcement



# ==========================================
# DELETE ANNOUNCEMENT
# ADMIN ONLY
# ==========================================

@router.delete(
    "/{announcement_id}",
    tags=["Admin"]
)
def delete_announcement(
    announcement_id: int,

    db: Session = Depends(get_db),

    current_admin=Depends(get_current_admin)
):

    # ==========================================
    # FIND ANNOUNCEMENT
    # ==========================================

    announcement = db.query(Announcement).filter(
        Announcement.id == announcement_id
    ).first()

    if not announcement:
        raise HTTPException(
            status_code=404,
            detail="Announcement not found"
        )

    # ==========================================
    # DELETE IMAGE FROM DIGITALOCEAN SPACES
    # ==========================================

    if announcement.image:

        image_key = announcement.image.split(
            f"{SPACES_PUBLIC_URL}/"
        )[-1]

        try:
            spaces_client.delete_object(
                Bucket=SPACES_BUCKET,
                Key=image_key
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete announcement image: {str(e)}"
            )

    # ==========================================
    # DELETE ANNOUNCEMENT FROM DATABASE
    # ==========================================

    db.delete(announcement)

    db.commit()

    return {
        "message": "Announcement and image deleted successfully"
    }
