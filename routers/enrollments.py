from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from database import SessionLocal
from database_models import Enrollment, Course, User

from schemas.enrollment import (
    EnrollmentResponse,
    AdminEnrollmentResponse
)

from routers.auth import get_current_user


router = APIRouter(
    prefix="/enrollments"
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
# GET MY ENROLLMENTS
# STUDENT ONLY
# ==========================================

@router.get(
    "/my",
    response_model=list[EnrollmentResponse],
    tags=["Student Enrollments"]
)
def get_my_enrollments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # ==========================================
    # CHECK USER ROLE
    # ==========================================

    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can access their enrollments"
        )

    # ==========================================
    # GET USER ENROLLMENTS
    # ==========================================

    results = (
        db.query(
            Enrollment,
            Course
        )
        .join(
            Course,
            Enrollment.course_id == Course.id
        )
        .filter(
            Enrollment.user_id == current_user.id
        )
        .order_by(
            Enrollment.created_at.desc()
        )
        .all()
    )

    # ==========================================
    # RETURN ENROLLMENTS
    # ==========================================

    return [
        {
            "id": enrollment.id,
            "user_id": enrollment.user_id,
            "course_id": enrollment.course_id,
            "branch_id": enrollment.branch_id,

            "name": enrollment.name,
            "email": enrollment.email,
            "phone": enrollment.phone,

            "parent_name": enrollment.parent_name,
            "parent_phone": enrollment.parent_phone,

            "highest_qualification": enrollment.highest_qualification,
            "address": enrollment.address,

            # Stored course title
            "course_title": enrollment.course_title,

            "course_image": course.image,
            "course_duration": course.duration,

            "total_fee": enrollment.total_fee,
            "status": enrollment.status,

            "razorpay_order_id": enrollment.razorpay_order_id,
            "razorpay_payment_id": enrollment.razorpay_payment_id,

            "created_at": enrollment.created_at
        }

        for enrollment, course in results
    ]


# ==========================================
# GET BRANCH ENROLLMENTS
# BRANCH ADMIN ONLY
# ==========================================

@router.get(
    "/branch-admin/my-enrollments",
    response_model=list[AdminEnrollmentResponse],
    tags=["Branch Admin Enrollments"]
)
def get_branch_admin_enrollments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # ==========================================
    # CHECK BRANCH ADMIN ROLE
    # ==========================================

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    # ==========================================
    # CHECK BRANCH ASSIGNMENT
    # ==========================================

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    # ==========================================
    # GET ONLY THIS BRANCH'S ENROLLMENTS
    # ==========================================

    results = (
        db.query(
            Enrollment,
            User,
            Course
        )
        .join(
            User,
            Enrollment.user_id == User.id
        )
        .join(
            Course,
            Enrollment.course_id == Course.id
        )
        .filter(
            Enrollment.branch_id == current_user.branch_id
        )
        .order_by(
            Enrollment.created_at.desc()
        )
        .all()
    )

    # ==========================================
    # RETURN ENROLLMENT DETAILS
    # ==========================================

    return [
        {
            "enrollment_id": enrollment.id,
            "user_id": enrollment.user_id,
            "course_id": enrollment.course_id,
            "branch_id": enrollment.branch_id,

            "name": enrollment.name,
            "email": enrollment.email,
            "phone": enrollment.phone,

            "parent_name": enrollment.parent_name,
            "parent_phone": enrollment.parent_phone,

            "highest_qualification": enrollment.highest_qualification,
            "address": enrollment.address,

            # Stored course title
            "course_title": enrollment.course_title,

            "course_image": course.image,
            "course_duration": course.duration,

            "total_fee": enrollment.total_fee,
            "status": enrollment.status,

            "razorpay_order_id": enrollment.razorpay_order_id,
            "razorpay_payment_id": enrollment.razorpay_payment_id,

            "created_at": enrollment.created_at
        }

        for enrollment, student, course in results
    ]


# ==========================================
# GET COURSE ENROLLMENTS
# BRANCH ADMIN ONLY
# ==========================================

@router.get(
    "/branch-admin/course/{course_id}",
    response_model=list[AdminEnrollmentResponse],
    tags=["Branch Admin Enrollments"]
)
def get_branch_admin_course_enrollments(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # ==========================================
    # CHECK BRANCH ADMIN ROLE
    # ==========================================

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    # ==========================================
    # CHECK BRANCH ASSIGNMENT
    # ==========================================

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    # ==========================================
    # CHECK COURSE EXISTS AND BELONGS
    # TO ADMIN'S BRANCH
    # ==========================================

    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == current_user.branch_id
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found in your branch"
        )

    # ==========================================
    # GET ONLY THIS COURSE'S ENROLLMENTS
    # ==========================================

    results = (
        db.query(
            Enrollment,
            User,
            Course
        )
        .join(
            User,
            Enrollment.user_id == User.id
        )
        .join(
            Course,
            Enrollment.course_id == Course.id
        )
        .filter(
            Enrollment.branch_id == current_user.branch_id,
            Enrollment.course_id == course_id
        )
        .order_by(
            Enrollment.created_at.desc()
        )
        .all()
    )

    # ==========================================
    # RETURN ENROLLMENT DETAILS
    # ==========================================

    return [
        {
            "enrollment_id": enrollment.id,
            "user_id": enrollment.user_id,
            "course_id": enrollment.course_id,
            "branch_id": enrollment.branch_id,

            "name": enrollment.name,
            "email": enrollment.email,
            "phone": enrollment.phone,

            "parent_name": enrollment.parent_name,
            "parent_phone": enrollment.parent_phone,

            "highest_qualification": enrollment.highest_qualification,
            "address": enrollment.address,

            # Stored course title
            "course_title": enrollment.course_title,

            "course_image": course.image,
            "course_duration": course.duration,

            "total_fee": enrollment.total_fee,
            "status": enrollment.status,

            "razorpay_order_id": enrollment.razorpay_order_id,
            "razorpay_payment_id": enrollment.razorpay_payment_id,

            "created_at": enrollment.created_at
        }

        for enrollment, student, course in results
    ]


# ==========================================
# GET BRANCH COURSE PURCHASE SUMMARY
# BRANCH ADMIN ONLY
# ==========================================

@router.get(
    "/branch-admin/course-summary",
    tags=["Branch Admin Enrollments"]
)
def get_branch_admin_course_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # ==========================================
    # CHECK BRANCH ADMIN ROLE
    # ==========================================

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    # ==========================================
    # CHECK BRANCH ASSIGNMENT
    # ==========================================

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    # ==========================================
    # GET COURSES WITH PURCHASE COUNT
    # ==========================================

    results = (
        db.query(
            Course.id.label("course_id"),
            Course.title.label("course_title"),
            Course.image.label("course_image"),
            func.count(
                Enrollment.id
            ).label("purchase_count")
        )
        .outerjoin(
            Enrollment,
            and_(
                Enrollment.course_id == Course.id,
                Enrollment.status == "paid"
            )
        )
        .filter(
            Course.branch_id == current_user.branch_id
        )
        .group_by(
            Course.id,
            Course.title,
            Course.image
        )
        .order_by(
            Course.id.asc()
        )
        .all()
    )

    # ==========================================
    # RETURN COURSE SUMMARY
    # ==========================================

    return [
        {
            "course_id": row.course_id,
            "course_title": row.course_title,
            "course_image": row.course_image,
            "purchase_count": row.purchase_count
        }

        for row in results
    ]