from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Course, CourseStudyMaterial, Enrollment, User
from routers.auth import get_current_user
from utils.study_material_files import study_material_download_url


router = APIRouter(
    prefix="/student/study-materials",
    tags=["Student Study Materials"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_student(current_user: User):
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="Student access required")
    if current_user.status != "Active":
        raise HTTPException(status_code=403, detail="Student account is inactive")


def get_approved_course_ids(db: Session, student_id: int):
    return (
        select(Enrollment.course_id)
        .where(
            Enrollment.user_id == student_id,
            Enrollment.course_status == "approved",
        )
        .distinct()
    )


def serialize_material(material: CourseStudyMaterial, course: Course):
    return {
        "id": material.id,
        "title": material.title,
        "description": material.description,
        "filename": material.filename,
        "created_at": material.created_at,
        "download_url": study_material_download_url(
            material.file_key,
            material.filename,
        ),
        "course": {
            "course_id": course.id,
            "course_title": course.title,
            "branch_id": course.branch_id,
        },
    }


@router.get("")
def get_my_study_materials(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_student(current_user)
    approved_course_ids = get_approved_course_ids(db, current_user.id)
    rows = (
        db.query(CourseStudyMaterial, Course)
        .join(Course, Course.id == CourseStudyMaterial.course_id)
        .filter(
            CourseStudyMaterial.course_id.in_(approved_course_ids),
            Course.is_active == True,
        )
        .order_by(
            Course.title.asc(),
            CourseStudyMaterial.created_at.desc(),
            CourseStudyMaterial.id.desc(),
        )
        .all()
    )
    return {
        "total": len(rows),
        "materials": [
            serialize_material(material, course)
            for material, course in rows
        ],
    }


@router.get("/courses/{course_id}")
def get_course_study_materials(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_student(current_user)
    approved_course_ids = get_approved_course_ids(db, current_user.id)
    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.id.in_(approved_course_ids),
            Course.is_active == True,
        )
        .first()
    )
    if not course:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to study materials for this course",
        )

    materials = (
        db.query(CourseStudyMaterial)
        .filter(CourseStudyMaterial.course_id == course.id)
        .order_by(
            CourseStudyMaterial.created_at.desc(),
            CourseStudyMaterial.id.desc(),
        )
        .all()
    )
    return {
        "course": {
            "course_id": course.id,
            "course_title": course.title,
            "branch_id": course.branch_id,
        },
        "total": len(materials),
        "materials": [
            serialize_material(material, course)
            for material in materials
        ],
    }


@router.get("/{material_id}/download")
def download_study_material(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_student(current_user)
    approved_course_ids = get_approved_course_ids(db, current_user.id)
    row = (
        db.query(CourseStudyMaterial, Course)
        .join(Course, Course.id == CourseStudyMaterial.course_id)
        .filter(
            CourseStudyMaterial.id == material_id,
            CourseStudyMaterial.course_id.in_(approved_course_ids),
            Course.is_active == True,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Study material not found")

    material, _course = row
    download_url = study_material_download_url(
        material.file_key,
        material.filename,
    )
    return RedirectResponse(url=download_url, status_code=307)
