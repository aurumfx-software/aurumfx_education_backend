from datetime import datetime, date, time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    User,
    Branch,
    Course,
    Staff,
    Enrollment
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

    # --------------------------------------
    # TOTAL ACTIVE COURSES
    # --------------------------------------

    total_courses = (
        db.query(func.count(Course.id))
        .filter(
            Course.branch_id == branch_id,
            Course.is_active == True
        )
        .scalar()
    ) or 0

    # --------------------------------------
    # TOTAL STUDENTS
    #
    # All unique students enrolled
    # in this branch, regardless of
    # payment or approval status
    # --------------------------------------

    total_students = (
        db.query(
            func.count(
                func.distinct(Enrollment.user_id)
            )
        )
        .filter(
            Enrollment.branch_id == branch_id
        )
        .scalar()
    ) or 0

    # --------------------------------------
    # TOTAL PAID STUDENTS
    #
    # Unique students whose enrollment
    # is paid AND approved
    # --------------------------------------

    total_paid_students = (
        db.query(
            func.count(
                func.distinct(Enrollment.user_id)
            )
        )
        .filter(
            Enrollment.branch_id == branch_id,
            Enrollment.status == "paid",
            Enrollment.course_status == "approved"
        )
        .scalar()
    ) or 0

    # --------------------------------------
    # TOTAL ACTIVE STAFF
    # --------------------------------------

    total_staff = (
        db.query(func.count(Staff.id))
        .filter(
            Staff.branch_id == branch_id,
            Staff.status == "Active"
        )
        .scalar()
    ) or 0

    # --------------------------------------
    # TOTAL PROFIT
    #
    # Only paid AND approved enrollments
    # --------------------------------------

    total_profit = (
        db.query(
            func.coalesce(
                func.sum(Enrollment.total_fee),
                0
            )
        )
        .filter(
            Enrollment.branch_id == branch_id,
            Enrollment.status == "paid",
            Enrollment.course_status == "approved"
        )
        .scalar()
    ) or 0

    # --------------------------------------
    # RESPONSE
    # --------------------------------------

    return {
        "branch_name": branch.name,
        "branch_location": branch.location,
        "branch_email": branch.email,
        "branch_phone": branch.phone,

        "total_courses": total_courses,
        "total_students": total_students,
        "total_paid_students": total_paid_students,
        "total_staff": total_staff,
        "total_profit": float(total_profit)
    }


# ==========================================
# BRANCH ADMIN TODAY'S PROFIT
# ==========================================

@router.get(
    "/today-profit",
    tags=["Branch Admin Today's Profit"]
)
def get_today_profit(
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
    # TODAY'S DATE
    # --------------------------------------

    today = date.today()

    start_of_day = datetime.combine(
        today,
        time.min
    )

    end_of_day = datetime.combine(
        today,
        time.max
    )

    # --------------------------------------
    # TODAY'S PROFIT
    #
    # Only paid AND approved enrollments
    # created today
    # --------------------------------------

    today_profit = (
        db.query(
            func.coalesce(
                func.sum(Enrollment.total_fee),
                0
            )
        )
        .filter(
            Enrollment.branch_id == branch_id,
            Enrollment.status == "paid",
            Enrollment.course_status == "approved",
            Enrollment.created_at >= start_of_day,
            Enrollment.created_at <= end_of_day
        )
        .scalar()
    ) or 0

    # --------------------------------------
    # RESPONSE
    # --------------------------------------

    return {
        "date": today.isoformat(),
        "today_profit": float(today_profit)
    }