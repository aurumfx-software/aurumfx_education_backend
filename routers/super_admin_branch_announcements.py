import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Announcement, Branch, User
from routers.auth import get_current_super_admin
from schemas.announcement import AnnouncementResponse
from utils.spaces import SPACES_BUCKET, SPACES_PUBLIC_URL, spaces_client


router = APIRouter(
    prefix="/super-admin/announcements",
    tags=["Super Admin Announcements"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_active_branch(db: Session, branch_id: int) -> Branch:
    branch = (
        db.query(Branch)
        .filter(Branch.id == branch_id)
        .first()
    )
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    if branch.status != "Active":
        raise HTTPException(status_code=400, detail="Branch is inactive")
    return branch


def get_branch_announcement(
    db: Session,
    branch_id: int,
    announcement_id: int,
) -> Announcement:
    announcement = (
        db.query(Announcement)
        .filter(
            Announcement.id == announcement_id,
            Announcement.branch_id == branch_id,
        )
        .first()
    )
    if not announcement:
        raise HTTPException(
            status_code=404,
            detail="Announcement not found in this branch",
        )
    return announcement


async def upload_announcement_image(branch_id: int, image: UploadFile) -> str:
    file_name = (
        f"announcements/branch-{branch_id}-"
        f"{uuid.uuid4()}-{image.filename}"
    )
    try:
        file_content = await image.read()
        spaces_client.put_object(
            Bucket=SPACES_BUCKET,
            Key=file_name,
            Body=file_content,
            ContentType=image.content_type,
            ACL="public-read",
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Announcement image upload failed: {error}",
        )
    return f"{SPACES_PUBLIC_URL}/{file_name}"


def delete_announcement_image(image_url: str):
    if not SPACES_PUBLIC_URL or not image_url.startswith(SPACES_PUBLIC_URL):
        return
    image_key = image_url.replace(f"{SPACES_PUBLIC_URL}/", "", 1)
    try:
        spaces_client.delete_object(Bucket=SPACES_BUCKET, Key=image_key)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete announcement image: {error}",
        )


@router.get("/branches")
def get_active_branches(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branches = (
        db.query(Branch)
        .filter(Branch.status == "Active")
        .order_by(Branch.name.asc())
        .all()
    )
    return [
        {
            "branch_id": branch.id,
            "branch_name": branch.name,
            "location": branch.location,
        }
        for branch in branches
    ]


@router.get(
    "/branches/{branch_id}",
    response_model=list[AnnouncementResponse],
)
def list_branch_announcements(
    branch_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    return (
        db.query(Announcement)
        .filter(Announcement.branch_id == branch_id)
        .order_by(Announcement.created_at.desc())
        .all()
    )


@router.post(
    "/branches/{branch_id}",
    response_model=AnnouncementResponse,
)
async def create_branch_announcement(
    branch_id: int,
    title: str = Form(...),
    message: str = Form(...),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    image_url = await upload_announcement_image(branch_id, image) if image else None
    announcement = Announcement(
        branch_id=branch_id,
        title=title,
        message=message,
        image=image_url,
    )
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return announcement


@router.get(
    "/branches/{branch_id}/{announcement_id}",
    response_model=AnnouncementResponse,
)
def get_branch_announcement_by_id(
    branch_id: int,
    announcement_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    return get_branch_announcement(db, branch_id, announcement_id)


@router.put(
    "/branches/{branch_id}/{announcement_id}",
    response_model=AnnouncementResponse,
)
async def update_branch_announcement(
    branch_id: int,
    announcement_id: int,
    title: str = Form(...),
    message: str = Form(...),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    announcement = get_branch_announcement(db, branch_id, announcement_id)
    new_image_url = (
        await upload_announcement_image(branch_id, image) if image else None
    )
    old_image_url = announcement.image

    announcement.title = title
    announcement.message = message
    if new_image_url:
        announcement.image = new_image_url

    db.commit()
    db.refresh(announcement)
    if new_image_url and old_image_url:
        delete_announcement_image(old_image_url)
    return announcement


@router.delete("/branches/{branch_id}/{announcement_id}")
def delete_branch_announcement(
    branch_id: int,
    announcement_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    announcement = get_branch_announcement(db, branch_id, announcement_id)
    if announcement.image:
        delete_announcement_image(announcement.image)

    db.delete(announcement)
    db.commit()
    return {"message": "Announcement and image deleted successfully"}
