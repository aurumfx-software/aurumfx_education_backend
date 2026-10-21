from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, Enrollment, User
from routers.auth import get_current_super_admin, get_current_user


router = APIRouter(tags=["Student Management"])


class StudentStatusUpdate(BaseModel):
    status: Literal["Active", "Inactive"]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_student_enrollments(db: Session, branch_id: int | None):
    query = db.query(Enrollment.user_id)
    if branch_id is not None:
        query = query.filter(Enrollment.branch_id == branch_id)
    return query.distinct().subquery()


def list_students(
    db: Session,
    branch_id: int | None,
):
    student_enrollments = get_student_enrollments(db, branch_id)
    student_query = (
        db.query(User)
        .join(student_enrollments, User.id == student_enrollments.c.user_id)
        .filter(User.role == "user")
    )
    total_students, active_students, inactive_students = (
        db.query(
            func.count(User.id),
            func.sum(case((User.status == "Active", 1), else_=0)),
            func.sum(case((User.status == "Inactive", 1), else_=0)),
        )
        .join(student_enrollments, User.id == student_enrollments.c.user_id)
        .filter(User.role == "user")
        .one()
    )
    students = (
        student_query
        .order_by(User.name.asc(), User.id.asc())
        .all()
    )
    student_ids = [student.id for student in students]

    branch_rows = []
    if student_ids:
        branch_query = (
            db.query(Enrollment.user_id, Branch.id, Branch.name)
            .join(Branch, Branch.id == Enrollment.branch_id)
            .filter(Enrollment.user_id.in_(student_ids))
        )
        if branch_id is not None:
            branch_query = branch_query.filter(Enrollment.branch_id == branch_id)
        branch_rows = branch_query.distinct().all()

    branches_by_student: dict[int, list[dict]] = {}
    for enrolled_user_id, enrolled_branch_id, branch_name in branch_rows:
        branches_by_student.setdefault(enrolled_user_id, []).append(
            {"branch_id": enrolled_branch_id, "branch_name": branch_name}
        )

    return {
        "total_students": int(total_students or 0),
        "active_students": int(active_students or 0),
        "inactive_students": int(inactive_students or 0),
        "students": [
            {
                "student_id": student.id,
                "name": student.name,
                "email": student.email,
                "phone": student.phone,
                "status": student.status,
                "created_at": student.created_at,
                "branches": branches_by_student.get(student.id, []),
            }
            for student in students
        ],
    }


def update_student_status(
    db: Session,
    student_id: int,
    status: str,
    branch_id: int | None,
):
    student = (
        db.query(User)
        .join(Enrollment, Enrollment.user_id == User.id)
        .filter(User.id == student_id, User.role == "user")
    )
    if branch_id is not None:
        student = student.filter(Enrollment.branch_id == branch_id)
    student = student.first()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    student.status = status
    db.commit()
    db.refresh(student)
    return {
        "message": "Student status updated successfully",
        "student_id": student.id,
        "status": student.status,
    }


@router.get("/branch-admin/students")
def get_branch_admin_students(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "branch_admin":
        raise HTTPException(status_code=403, detail="Branch admin access required")
    if current_user.branch_id is None:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch",
        )

    return list_students(db, current_user.branch_id)


@router.patch("/branch-admin/students/{student_id}/status")
def set_branch_admin_student_status(
    student_id: int,
    status_update: StudentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "branch_admin":
        raise HTTPException(status_code=403, detail="Branch admin access required")
    if current_user.branch_id is None:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch",
        )

    return update_student_status(
        db,
        student_id,
        status_update.status,
        current_user.branch_id,
    )


@router.get("/super-admin/students")
def get_super_admin_students(
    branch_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    if branch_id is not None and not db.query(Branch.id).filter(
        Branch.id == branch_id
    ).first():
        raise HTTPException(status_code=404, detail="Branch not found")

    return list_students(db, branch_id)


@router.patch("/super-admin/students/{student_id}/status")
def set_super_admin_student_status(
    student_id: int,
    status_update: StudentStatusUpdate,
    branch_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    if branch_id is not None and not db.query(Branch.id).filter(
        Branch.id == branch_id
    ).first():
        raise HTTPException(status_code=404, detail="Branch not found")

    return update_student_status(db, student_id, status_update.status, branch_id)
