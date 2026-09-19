from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Enrollment, Course, User

from schemas.enrollment import (
    EnrollmentCreate,
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
# CREATE ENROLLMENT
# STUDENT ONLY
# ==========================================

@router.post(
    "/",
    response_model=EnrollmentResponse,
    tags=["Student Enrollments"]
)
def create_enrollment(
    enrollment_data: EnrollmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # ==========================================
    # CHECK USER ROLE
    # ==========================================

    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can create enrollments"
        )

    # ==========================================
    # FIND ACTIVE COURSE
    # ==========================================

    course = (
        db.query(Course)
        .filter(
            Course.id == enrollment_data.course_id,
            Course.is_active == True
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )

    # ==========================================
    # CHECK COURSE BRANCH
    # ==========================================

    if not course.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Course is not assigned to a branch"
        )

    # ==========================================
    # CHECK IF ALREADY ENROLLED
    # ==========================================

    existing_enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.user_id == current_user.id,
            Enrollment.course_id == course.id
        )
        .first()
    )

    if existing_enrollment:
        raise HTTPException(
            status_code=400,
            detail="You are already enrolled in this course"
        )

    # ==========================================
    # CREATE ENROLLMENT
    # ==========================================

    new_enrollment = Enrollment(
        user_id=current_user.id,
        course_id=course.id,
        branch_id=course.branch_id,

        # Student details
        name=current_user.name,
        email=current_user.email,
        phone=current_user.phone,
        parent_name=current_user.parent_name,
        parent_phone=current_user.parent_phone,
        highest_qualification=current_user.highest_qualification,
        address=current_user.address,

        # Course fee
        total_fee=course.price,

        # Payment status
        status="pending"
    )

    db.add(new_enrollment)

    db.commit()

    db.refresh(new_enrollment)

    # ==========================================
    # RETURN ENROLLMENT DETAILS
    # ==========================================

    return {
        "id": new_enrollment.id,
        "user_id": new_enrollment.user_id,
        "course_id": new_enrollment.course_id,
        "branch_id": new_enrollment.branch_id,

        "name": new_enrollment.name,
        "email": new_enrollment.email,
        "phone": new_enrollment.phone,

        "parent_name": new_enrollment.parent_name,
        "parent_phone": new_enrollment.parent_phone,

        "highest_qualification": new_enrollment.highest_qualification,
        "address": new_enrollment.address,

        "course_title": course.title,
        "course_image": course.image,
        "course_duration": course.duration,

        "total_fee": new_enrollment.total_fee,
        "status": new_enrollment.status,

        "razorpay_order_id": new_enrollment.razorpay_order_id,
        "razorpay_payment_id": new_enrollment.razorpay_payment_id,

        "created_at": new_enrollment.created_at
    }


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

            "highest_qualification": (
                enrollment.highest_qualification
            ),

            "address": enrollment.address,

            "course_title": course.title,
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

            "highest_qualification": (
                enrollment.highest_qualification
            ),

            "address": enrollment.address,

            "course_title": course.title,
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
    # CHECK COURSE EXISTS AND BELONGS TO ADMIN'S BRANCH
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

            "highest_qualification": (
                enrollment.highest_qualification
            ),

            "address": enrollment.address,

            "course_title": course.title,
            "course_image": course.image,
            "course_duration": course.duration,

            "total_fee": enrollment.total_fee,
            "status": enrollment.status,

            "razorpay_order_id": (
                enrollment.razorpay_order_id
            ),

            "razorpay_payment_id": (
                enrollment.razorpay_payment_id
            ),

            "created_at": enrollment.created_at
        }

        for enrollment, student, course in results
    ]
