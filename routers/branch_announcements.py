import uuid

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
from database_models import Announcement, Branch

from schemas.announcement import AnnouncementResponse

from routers.auth import get_current_user

from utils.spaces import (
    spaces_client,
    SPACES_BUCKET,
    SPACES_PUBLIC_URL
)


router = APIRouter(
    prefix="/branch-announcements"
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
# BRANCH ADMIN AUTHENTICATION
# ==========================================

def get_current_branch_admin(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # ==========================================
    # CHECK ROLE
    # ==========================================

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    # ==========================================
    # CHECK USER STATUS
    # ==========================================

    if current_user.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Branch admin account is inactive"
        )

    # ==========================================
    # CHECK BRANCH
    # ==========================================

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    branch = (
        db.query(Branch)
        .filter(
            Branch.id == current_user.branch_id
        )
        .first()
    )

    if not branch:
        raise HTTPException(
            status_code=404,
            detail="Branch not found"
        )

    # ==========================================
    # CHECK BRANCH STATUS
    # ==========================================

    if branch.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Branch is inactive"
        )

    return current_user


# ==========================================
# CREATE ANNOUNCEMENT
# BRANCH ADMIN ONLY
# ==========================================

@router.post(
    "/",
    response_model=AnnouncementResponse,
    tags=["Branch Admin Announcements"]
)
async def create_branch_announcement(

    title: str = Form(...),

    message: str = Form(...),

    image: UploadFile | None = File(None),

    db: Session = Depends(get_db),

    branch_admin=Depends(get_current_branch_admin)
):

    image_url = None

    # ==========================================
    # UPLOAD IMAGE
    # ==========================================

    if image:

        file_name = (
            f"announcements/"
            f"branch-{branch_admin.branch_id}-"
            f"{uuid.uuid4()}-{image.filename}"
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
        branch_id=branch_admin.branch_id,
        title=title,
        message=message,
        image=image_url
    )

    db.add(new_announcement)

    db.commit()

    db.refresh(new_announcement)

    return new_announcement


# ==========================================
# GET ALL ANNOUNCEMENTS
# OWN BRANCH ONLY
# ==========================================

@router.get(
    "/",
    response_model=list[AnnouncementResponse],
    tags=["Branch Admin Announcements"]
)
def get_branch_announcements(

    db: Session = Depends(get_db),

    branch_admin=Depends(get_current_branch_admin)
):

    announcements = (
        db.query(Announcement)
        .filter(
            Announcement.branch_id == branch_admin.branch_id
        )
        .order_by(
            Announcement.created_at.desc()
        )
        .all()
    )

    return announcements


# ==========================================
# GET ANNOUNCEMENT BY ID
# OWN BRANCH ONLY
# ==========================================

@router.get(
    "/{announcement_id}",
    response_model=AnnouncementResponse,
    tags=["Branch Admin Announcements"]
)
def get_branch_announcement(

    announcement_id: int,

    db: Session = Depends(get_db),

    branch_admin=Depends(get_current_branch_admin)
):

    announcement = (
        db.query(Announcement)
        .filter(
            Announcement.id == announcement_id,
            Announcement.branch_id == branch_admin.branch_id
        )
        .first()
    )

    if not announcement:

        raise HTTPException(
            status_code=404,
            detail="Announcement not found in your branch"
        )

    return announcement


# ==========================================
# UPDATE ANNOUNCEMENT
# OWN BRANCH ONLY
# ==========================================

@router.put(
    "/{announcement_id}",
    response_model=AnnouncementResponse,
    tags=["Branch Admin Announcements"]
)
async def update_branch_announcement(

    announcement_id: int,

    title: str = Form(...),

    message: str = Form(...),

    image: UploadFile | None = File(None),

    db: Session = Depends(get_db),

    branch_admin=Depends(get_current_branch_admin)
):

    # ==========================================
    # FIND ANNOUNCEMENT
    # OWN BRANCH ONLY
    # ==========================================

    announcement = (
        db.query(Announcement)
        .filter(
            Announcement.id == announcement_id,
            Announcement.branch_id == branch_admin.branch_id
        )
        .first()
    )

    if not announcement:

        raise HTTPException(
            status_code=404,
            detail="Announcement not found in your branch"
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
            f"announcements/"
            f"branch-{branch_admin.branch_id}-"
            f"{uuid.uuid4()}-{image.filename}"
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
# OWN BRANCH ONLY
# ==========================================

@router.delete(
    "/{announcement_id}",
    tags=["Branch Admin Announcements"]
)
def delete_branch_announcement(

    announcement_id: int,

    db: Session = Depends(get_db),

    branch_admin=Depends(get_current_branch_admin)
):

    # ==========================================
    # FIND ANNOUNCEMENT
    # OWN BRANCH ONLY
    # ==========================================

    announcement = (
        db.query(Announcement)
        .filter(
            Announcement.id == announcement_id,
            Announcement.branch_id == branch_admin.branch_id
        )
        .first()
    )

    if not announcement:

        raise HTTPException(
            status_code=404,
            detail="Announcement not found in your branch"
        )

    # ==========================================
    # DELETE IMAGE
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
    # DELETE ANNOUNCEMENT
    # ==========================================

    db.delete(announcement)

    db.commit()

    return {
        "message": "Announcement and image deleted successfully"
    }