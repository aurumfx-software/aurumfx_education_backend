import json
import os
import uuid

from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, Course, User
from routers.auth import get_current_super_admin
from routers.courses import (
    validate_installment_details,
    validate_installment_terms,
)
from schemas.course import BranchAdminCourseResponse
from schemas.super_admin_course import SuperAdminCourseCreateResult
from utils.spaces import SPACES_BUCKET, spaces_client


router = APIRouter(
    prefix="/super-admin/courses",
    tags=["Super Admin Courses"],
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


def parse_course_data(
    title: str,
    description: str,
    price: float,
    duration: str,
    category: str,
    level: str,
    start_date: date,
    end_date: date,
    curriculum: str,
    installment_schedule: str,
    installment_count: int,
    installment_terms: str,
):
    if price <= 0:
        raise HTTPException(status_code=400, detail="Course price must be greater than 0")
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date")

    try:
        curriculum_data = json.loads(curriculum)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid curriculum JSON")

    schedule, count = validate_installment_details(
        installment_schedule=installment_schedule,
        installment_count=installment_count,
    )
    terms = validate_installment_terms(
        installment_terms=installment_terms,
        installment_count=count,
        course_price=price,
        start_date=start_date,
        end_date=end_date,
    )
    return {
        "title": title,
        "description": description,
        "price": price,
        "duration": duration,
        "category": category,
        "level": level,
        "start_date": start_date,
        "end_date": end_date,
        "curriculum": curriculum_data,
        "installment_schedule": schedule,
        "installment_count": count,
        "installment_terms": terms,
    }


def upload_course_image(image: UploadFile) -> str:
    extension = os.path.splitext(image.filename or "")[1]
    file_name = f"courses/{uuid.uuid4()}{extension}"
    try:
        spaces_client.upload_fileobj(
            image.file,
            SPACES_BUCKET,
            file_name,
            ExtraArgs={
                "ContentType": image.content_type,
                "ACL": "public-read",
            },
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Image upload failed: {error}",
        )
    return f"{os.getenv('SPACES_PUBLIC_URL')}/{file_name}"


def upload_course_image_copy(
    branch_id: int,
    filename: str,
    content_type: str | None,
    content: bytes,
) -> str:
    extension = os.path.splitext(filename)[1]
    file_name = f"courses/branch-{branch_id}/{uuid.uuid4()}{extension}"
    try:
        spaces_client.put_object(
            Bucket=SPACES_BUCKET,
            Key=file_name,
            Body=content,
            ContentType=content_type,
            ACL="public-read",
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Image upload failed for branch {branch_id}: {error}",
        )
    return f"{os.getenv('SPACES_PUBLIC_URL')}/{file_name}"


def delete_course_image(image_url: str | None):
    public_url = os.getenv("SPACES_PUBLIC_URL")
    if not public_url or not image_url or not image_url.startswith(public_url):
        return

    key = image_url.replace(f"{public_url}/", "", 1)
    try:
        spaces_client.delete_object(Bucket=SPACES_BUCKET, Key=key)
    except Exception as error:
        print(f"Error deleting course image from Spaces: {error}")


@router.get("/branches")
def get_branches(
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
    response_model=list[BranchAdminCourseResponse],
)
def get_branch_courses(
    branch_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    return (
        db.query(Course)
        .filter(Course.branch_id == branch_id, Course.is_active == True)
        .order_by(Course.title.asc())
        .all()
    )


@router.get(
    "/branches/{branch_id}/{course_id}",
    response_model=BranchAdminCourseResponse,
)
def get_branch_course(
    branch_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == branch_id,
            Course.is_active == True,
        )
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found in this branch")
    return course


@router.post(
    "/branches/bulk",
    response_model=list[SuperAdminCourseCreateResult],
)
def create_course_for_branches(
    branch_ids: list[int] | None = Form(default=None),
    all_branches: bool = Form(default=False),
    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    duration: str = Form(...),
    category: str = Form(...),
    level: str = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    curriculum: str = Form(...),
    installment_schedule: str = Form("monthly"),
    installment_count: int = Form(0),
    installment_terms: str = Form("[]"),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    if all_branches and branch_ids:
        raise HTTPException(
            status_code=400,
            detail="Provide branch_ids or set all_branches, not both",
        )

    if all_branches:
        target_branches = (
            db.query(Branch)
            .filter(Branch.status == "Active")
            .order_by(Branch.name.asc())
            .all()
        )
    else:
        selected_ids = list(dict.fromkeys(branch_ids or []))
        if not selected_ids:
            raise HTTPException(
                status_code=400,
                detail="Select at least one branch or set all_branches=true",
            )
        target_branches = (
            db.query(Branch)
            .filter(
                Branch.id.in_(selected_ids),
                Branch.status == "Active",
            )
            .all()
        )
        if len(target_branches) != len(selected_ids):
            raise HTTPException(
                status_code=404,
                detail="One or more selected branches were not found or are inactive",
            )
        branches_by_id = {branch.id: branch for branch in target_branches}
        target_branches = [branches_by_id[branch_id] for branch_id in selected_ids]

    if not target_branches:
        raise HTTPException(
            status_code=400,
            detail="There are no active branches to create this course in",
        )

    course_data = parse_course_data(
        title,
        description,
        price,
        duration,
        category,
        level,
        start_date,
        end_date,
        curriculum,
        installment_schedule,
        installment_count,
        installment_terms,
    )
    image_content = image.file.read()
    uploaded_images = []
    courses = []

    try:
        for branch in target_branches:
            image_url = upload_course_image_copy(
                branch_id=branch.id,
                filename=image.filename or "course-image",
                content_type=image.content_type,
                content=image_content,
            )
            uploaded_images.append(image_url)
            courses.append(
                Course(
                    **course_data,
                    branch_id=branch.id,
                    image=image_url,
                    is_active=True,
                )
            )

        db.add_all(courses)
        db.commit()
    except HTTPException:
        db.rollback()
        for image_url in uploaded_images:
            delete_course_image(image_url)
        raise
    except Exception as error:
        db.rollback()
        for image_url in uploaded_images:
            delete_course_image(image_url)
        raise HTTPException(
            status_code=500,
            detail=f"Course creation failed: {error}",
        )

    for course in courses:
        db.refresh(course)

    branches_by_id = {branch.id: branch for branch in target_branches}
    return [
        {
            "branch_id": course.branch_id,
            "branch_name": branches_by_id[course.branch_id].name,
            "course": course,
        }
        for course in courses
    ]


@router.post(
    "/branches/{branch_id}",
    response_model=BranchAdminCourseResponse,
)
def create_branch_course(
    branch_id: int,
    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    duration: str = Form(...),
    category: str = Form(...),
    level: str = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    curriculum: str = Form(...),
    installment_schedule: str = Form("monthly"),
    installment_count: int = Form(0),
    installment_terms: str = Form("[]"),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    course_data = parse_course_data(
        title,
        description,
        price,
        duration,
        category,
        level,
        start_date,
        end_date,
        curriculum,
        installment_schedule,
        installment_count,
        installment_terms,
    )
    course_data["branch_id"] = branch_id
    course_data["image"] = upload_course_image(image)
    course_data["is_active"] = True

    course = Course(**course_data)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.put(
    "/branches/{branch_id}/{course_id}",
    response_model=BranchAdminCourseResponse,
)
def update_branch_course(
    branch_id: int,
    course_id: int,
    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    duration: str = Form(...),
    category: str = Form(...),
    level: str = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    curriculum: str = Form(...),
    installment_schedule: str = Form("monthly"),
    installment_count: int = Form(0),
    installment_terms: str = Form("[]"),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == branch_id,
            Course.is_active == True,
        )
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found in this branch")

    course_data = parse_course_data(
        title,
        description,
        price,
        duration,
        category,
        level,
        start_date,
        end_date,
        curriculum,
        installment_schedule,
        installment_count,
        installment_terms,
    )
    new_image_url = upload_course_image(image) if image else None
    old_image_url = course.image

    for field, value in course_data.items():
        setattr(course, field, value)
    if new_image_url:
        course.image = new_image_url

    db.commit()
    db.refresh(course)
    if new_image_url:
        delete_course_image(old_image_url)
    return course


@router.delete("/branches/{branch_id}/{course_id}")
def delete_branch_course(
    branch_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == branch_id,
        )
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found in this branch")

    delete_course_image(course.image)
    db.delete(course)
    db.commit()
    return {"message": "Course deleted successfully"}
