from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Form,
    UploadFile,
    File
)

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Announcement, Enrollment, Staff, User
from routers.auth import get_current_super_admin, get_current_user
from routers.staff_portal import get_current_staff_record
from schemas.announcement import AnnouncementAudience, AnnouncementResponse

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
    audience: AnnouncementAudience = Form("all"),
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
        audience=audience,
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
        .filter(
            Announcement.branch_id.is_(None),
            Announcement.audience.in_(("students", "all", "both")),
        )
        .order_by(
            Announcement.created_at.desc()
        )
        .all()
    )

    return announcements


@router.get(
    "/admin/global",
    response_model=list[AnnouncementResponse],
    tags=["Super Admin"],
)
def get_global_announcements_for_super_admin(
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin),
):
    return (
        db.query(Announcement)
        .filter(Announcement.branch_id.is_(None))
        .order_by(Announcement.created_at.desc(), Announcement.id.desc())
        .all()
    )


@router.get(
    "/student/branch",
    response_model=list[AnnouncementResponse],
    tags=["Student Announcements"],
)
def get_student_branch_announcements(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="Student access required")

    branch_ids = (
        select(Enrollment.branch_id)
        .where(
            Enrollment.user_id == current_user.id,
            Enrollment.course_status == "approved",
        )
        .distinct()
    )
    return (
        db.query(Announcement)
        .filter(
            or_(
                Announcement.branch_id.is_(None),
                Announcement.branch_id.in_(branch_ids),
            ),
            Announcement.audience.in_(("students", "all", "both")),
        )
        .order_by(Announcement.created_at.desc(), Announcement.id.desc())
        .all()
    )


@router.get(
    "/staff/branch",
    response_model=list[AnnouncementResponse],
    tags=["Staff Announcements"],
)
def get_staff_branch_announcements(
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    return (
        db.query(Announcement)
        .filter(
            or_(
                Announcement.branch_id.is_(None),
                Announcement.branch_id == staff.branch_id,
            ),
            Announcement.audience.in_(("staff", "all", "both")),
        )
        .order_by(Announcement.created_at.desc(), Announcement.id.desc())
        .all()
    )


@router.get(
    "/branch-admin/branch",
    response_model=list[AnnouncementResponse],
    tags=["Branch Admin Announcements"],
)
def get_branch_admin_announcements(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role != "branch_admin":
        raise HTTPException(status_code=403, detail="Branch admin access required")
    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch",
        )

    return (
        db.query(Announcement)
        .filter(
            or_(
                Announcement.branch_id.is_(None),
                Announcement.branch_id == current_user.branch_id,
            ),
            Announcement.audience.in_(("branch_admin", "all", "both")),
        )
        .order_by(Announcement.created_at.desc(), Announcement.id.desc())
        .all()
    )


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
    audience: AnnouncementAudience | None = Form(None),
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
    if audience is not None:
        announcement.audience = audience


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