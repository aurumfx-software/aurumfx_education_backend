from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    User,
    Branch,
    Course,
    Staff,
    Enrollment,
    EnrollmentInstallment,
)

from routers.auth import get_current_user


router = APIRouter(
    prefix="/branch-admin/dashboard",
    tags=["Branch Admin Dashboard"]
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
# BRANCH ADMIN DASHBOARD
# ==========================================

@router.get("")
def get_branch_admin_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # --------------------------------------
    # CHECK BRANCH ADMIN
    # --------------------------------------

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    branch_id = current_user.branch_id

    # --------------------------------------
    # GET BRANCH
    # --------------------------------------

    branch = (
        db.query(Branch)
        .filter(
            Branch.id == branch_id
        )
        .first()
    )

    if not branch:
        raise HTTPException(
            status_code=404,
            detail="Branch not found"
        )

    total_courses = (
        db.query(func.count(Course.id))
        .filter(Course.branch_id == branch_id, Course.is_active == True)
        .scalar()
    ) or 0
    total_students = (
        db.query(func.count(func.distinct(Enrollment.user_id)))
        .filter(Enrollment.branch_id == branch_id)
        .scalar()
    ) or 0
    total_enrollments = (
        db.query(func.count(Enrollment.id))
        .filter(Enrollment.branch_id == branch_id)
        .scalar()
    ) or 0
    total_staff = (
        db.query(func.count(Staff.id))
        .filter(Staff.branch_id == branch_id, Staff.status == "Active")
        .scalar()
    ) or 0
    today_enrollments = (
        db.query(func.count(Enrollment.id))
        .filter(
            Enrollment.branch_id == branch_id,
            func.date(Enrollment.created_at) == date.today(),
        )
        .scalar()
    ) or 0
    today_new_students = (
        db.query(func.count(func.distinct(Enrollment.user_id)))
        .filter(
            Enrollment.branch_id == branch_id,
            func.date(Enrollment.created_at) == date.today(),
        )
        .scalar()
    ) or 0

    course_stats = (
        db.query(
            Enrollment.course_id.label("course_id"),
            func.count(Enrollment.id).label("enrollment_count"),
            func.count(func.distinct(Enrollment.user_id)).label("student_count"),
            func.count(
                func.distinct(
                    case(
                        (Enrollment.total_paid > 0, Enrollment.user_id),
                        else_=None,
                    )
                )
            ).label("students_with_payment"),
            func.count(
                func.distinct(
                    case(
                        (Enrollment.balance_amount <= 0, Enrollment.user_id),
                        else_=None,
                    )
                )
            ).label("fully_paid_students"),
            func.count(
                func.distinct(
                    case(
                        (Enrollment.balance_amount > 0, Enrollment.user_id),
                        else_=None,
                    )
                )
            ).label("students_with_balance"),
        )
        .filter(Enrollment.branch_id == branch_id)
        .group_by(Enrollment.course_id)
        .all()
    )
    course_stats_by_id = {row.course_id: row for row in course_stats}
    courses = (
        db.query(Course)
        .filter(Course.branch_id == branch_id, Course.is_active == True)
        .order_by(Course.title.asc())
        .all()
    )
    course_enrollments = []
    for course in courses:
        stats = course_stats_by_id.get(course.id)
        course_enrollments.append(
            {
                "course_id": course.id,
                "course_title": course.title,
                "total_enrollments": stats.enrollment_count if stats else 0,
                "total_students": stats.student_count if stats else 0,
                "students_with_payment": (
                    stats.students_with_payment if stats else 0
                ),
                "fully_paid_students": (
                    stats.fully_paid_students if stats else 0
                ),
                "students_with_balance": (
                    stats.students_with_balance if stats else 0
                ),
            }
        )

    today = date.today()
    due_rows = (
        db.query(Enrollment, Course, EnrollmentInstallment)
        .join(Course, Course.id == Enrollment.course_id)
        .join(
            EnrollmentInstallment,
            EnrollmentInstallment.enrollment_id == Enrollment.id,
        )
        .filter(
            Enrollment.branch_id == branch_id,
            EnrollmentInstallment.due_date <= today,
            EnrollmentInstallment.paid_amount < EnrollmentInstallment.amount,
        )
        .order_by(
            EnrollmentInstallment.due_date.asc(),
            Enrollment.name.asc(),
        )
        .all()
    )
    due_by_user = {}
    for enrollment, course, installment in due_rows:
        student = due_by_user.setdefault(
            enrollment.user_id,
            {
                "student_id": enrollment.user_id,
                "name": enrollment.name,
                "phone": enrollment.phone,
                "parent_name": enrollment.parent_name,
                "parent_phone": enrollment.parent_phone,
                "email": enrollment.email,
                "due_enrollments": {},
                "total_due_amount": 0,
            },
        )
        due_enrollment = student["due_enrollments"].setdefault(
            enrollment.id,
            {
                "enrollment_id": enrollment.id,
                "course_id": course.id,
                "course_title": course.title,
                "due_installments": [],
            },
        )
        remaining_amount = round(
            installment.amount - installment.paid_amount, 2
        )
        due_enrollment["due_installments"].append(
            {
                "installment_id": installment.id,
                "installment_number": installment.installment_number,
                "amount": installment.amount,
                "paid_amount": installment.paid_amount,
                "remaining_amount": remaining_amount,
                "due_date": installment.due_date,
                "status": installment.status,
            }
        )
        student["total_due_amount"] = round(
            student["total_due_amount"] + remaining_amount, 2
        )

    due_students = []
    for student in due_by_user.values():
        student["due_enrollments"] = list(student["due_enrollments"].values())
        due_students.append(student)

    fully_paid_students = (
        db.query(func.count(func.distinct(Enrollment.user_id)))
        .filter(
            Enrollment.branch_id == branch_id,
            Enrollment.balance_amount <= 0,
        )
        .scalar()
    ) or 0
    students_with_balance = (
        db.query(func.count(func.distinct(Enrollment.user_id)))
        .filter(
            Enrollment.branch_id == branch_id,
            Enrollment.balance_amount > 0,
        )
        .scalar()
    ) or 0
    due_installment_count = sum(
        len(enrollment_data["due_installments"])
        for student in due_students
        for enrollment_data in student["due_enrollments"]
    )
    total_due_amount = round(
        sum(student["total_due_amount"] for student in due_students),
        2,
    )

    return {
        "branch_name": branch.name,
        "branch_location": branch.location,
        "branch_email": branch.email,
        "branch_phone": branch.phone,
        "overview": {
            "total_courses": total_courses,
            "total_students": total_students,
            "total_enrollments": total_enrollments,
            "total_staff": total_staff,
            "today_enrollments": today_enrollments,
            "today_new_students": today_new_students,
            "fully_paid_students": fully_paid_students,
            "students_with_balance": students_with_balance,
            "due_students": len(due_students),
            "due_installments": due_installment_count,
            "total_due_amount": total_due_amount,
        },
        "course_enrollments": course_enrollments,
        "due_students": due_students,
    }

