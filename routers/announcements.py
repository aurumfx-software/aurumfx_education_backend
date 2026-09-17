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

from routers.auth import get_current_super_admin

from utils.spaces import (
    spaces_client,
    SPACES_BUCKET,
    SPACES_PUBLIC_URL
)


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
# SUPER ADMIN ONLY
# ==========================================

@router.post(
    "/",
    response_model=AnnouncementResponse,
    tags=["Super Admin"]
)
async def create_announcement(
    title: str = Form(...),
    message: str = Form(...),
    image: UploadFile | None = File(None),

    db: Session = Depends(get_db),

    current_admin=Depends(get_current_super_admin)
):

    image_url = None

    # ==========================================
    # UPLOAD IMAGE
    # ==========================================

    if image:

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
# PUBLIC
# ==========================================

@router.get(
    "/",
    response_model=list[AnnouncementResponse],
    tags=["Super Admin"]
)
def get_announcements(
    db: Session = Depends(get_db)
):

    announcements = (
        db.query(Announcement)
        .order_by(
            Announcement.created_at.desc()
        )
        .all()
    )

    return announcements


# ==========================================
# UPDATE ANNOUNCEMENT
# SUPER ADMIN ONLY
# ==========================================

@router.put(
    "/{announcement_id}",
    response_model=AnnouncementResponse,
    tags=["Super Admin"]
)
async def update_announcement(
    announcement_id: int,

    title: str = Form(...),
    message: str = Form(...),
    image: UploadFile | None = File(None),

    db: Session = Depends(get_db),

    current_admin=Depends(get_current_super_admin)
):

    # ==========================================
    # FIND ANNOUNCEMENT
    # ==========================================

    announcement = (
        db.query(Announcement)
        .filter(
            Announcement.id == announcement_id
        )
        .first()
    )

    if not announcement:

        raise HTTPException(
            status_code=404,
            detail="Announcement not found"
        )

    # ==========================================
    # UPDATE TEXT
    # ==========================================

    announcement.title = title
    announcement.message = message


    # ==========================================
    # UPDATE IMAGE IF PROVIDED
    # ==========================================

    if image:

        # ------------------------------------------
        # DELETE OLD IMAGE
        # ------------------------------------------

        if announcement.image:

            old_key = announcement.image.replace(
                f"{SPACES_PUBLIC_URL}/",
                ""
            )

            try:

                spaces_client.delete_object(
                    Bucket=SPACES_BUCKET,
                    Key=old_key
                )

            except Exception as e:

                print(
                    f"Error deleting old announcement image: {e}"
                )


        # ------------------------------------------
        # UPLOAD NEW IMAGE
        # ------------------------------------------

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


    # ==========================================
    # SAVE CHANGES
    # ==========================================

    db.commit()

    db.refresh(announcement)

    return announcement


# ==========================================
# DELETE ANNOUNCEMENT
# SUPER ADMIN ONLY
# ==========================================

@router.delete(
    "/{announcement_id}",
    tags=["Super Admin"]
)
def delete_announcement(
    announcement_id: int,

    db: Session = Depends(get_db),

    current_admin=Depends(get_current_super_admin)
):

    # ==========================================
    # FIND ANNOUNCEMENT
    # ==========================================

    announcement = (
        db.query(Announcement)
        .filter(
            Announcement.id == announcement_id
        )
        .first()
    )

    if not announcement:

        raise HTTPException(
            status_code=404,
            detail="Announcement not found"
        )


    # ==========================================
    # DELETE IMAGE FROM DIGITALOCEAN SPACES
    # ==========================================

    if announcement.image:

        image_key = announcement.image.replace(
            f"{SPACES_PUBLIC_URL}/",
            ""
        )

        try:

            spaces_client.delete_object(
                Bucket=SPACES_BUCKET,
                Key=image_key
            )

        except Exception as e:

            raise HTTPException(
                status_code=500,
                detail=(
                    "Failed to delete announcement image: "
                    f"{str(e)}"
                )
            )


    # ==========================================
    # DELETE ANNOUNCEMENT FROM DATABASE
    # ==========================================

    db.delete(announcement)

    db.commit()

    return {
        "message": "Announcement and image deleted successfully"
    }