from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Enrollment, Course

from schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentResponse,
    AdminEnrollmentResponse,
    EnrollmentStatusUpdate
)

from routers.auth import (
    get_current_user,
    get_current_admin
)


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
    tags=["User"]
)
def create_enrollment(
    enrollment_data: EnrollmentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    # ==========================================
    # FIND COURSE
    # ==========================================

    course = db.query(Course).filter(
        Course.id == enrollment_data.course_id,
        Course.is_active == True
    ).first()

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )


    # ==========================================
    # CHECK IF ALREADY ENROLLED
    # ==========================================

    existing_enrollment = db.query(Enrollment).filter(
        Enrollment.user_id == current_user.id,
        Enrollment.course_id == course.id
    ).first()

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

        full_name=enrollment_data.full_name,
        email=enrollment_data.email,
        phone=enrollment_data.phone,

        parent_name=enrollment_data.parent_name,
        parent_phone=enrollment_data.parent_phone,

        highest_qualification=enrollment_data.highest_qualification,

        address=enrollment_data.address,
        payment_plan=enrollment_data.payment_plan,

        total_fee=course.price,
        status="pending"
    )

    db.add(new_enrollment)

    db.commit()

    db.refresh(new_enrollment)


    # ==========================================
    # RETURN ENROLLMENT + COURSE DETAILS
    # ==========================================

    return {
        "id": new_enrollment.id,
        "user_id": new_enrollment.user_id,
        "course_id": new_enrollment.course_id,

        "full_name": new_enrollment.full_name,
        "email": new_enrollment.email,
        "phone": new_enrollment.phone,

        "parent_name": new_enrollment.parent_name,
        "parent_phone": new_enrollment.parent_phone,

        "highest_qualification": (
            new_enrollment.highest_qualification
        ),

        "address": new_enrollment.address,
        "payment_plan": new_enrollment.payment_plan,

        "course_title": course.title,
        "course_image": course.image,
        "course_duration": course.duration,

        "total_fee": new_enrollment.total_fee,
        "status": new_enrollment.status,
        "enrolled_at": new_enrollment.enrolled_at
    }


# ==========================================
# GET MY ENROLLMENTS
# STUDENT ONLY
# ==========================================

@router.get(
    "/my",
    response_model=list[EnrollmentResponse],
    tags=["User"]
)
def get_my_enrollments(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    results = db.query(
        Enrollment,
        Course
    ).join(
        Course,
        Enrollment.course_id == Course.id
    ).filter(
        Enrollment.user_id == current_user.id
    ).all()


    return [
        {
            "id": enrollment.id,
            "user_id": enrollment.user_id,
            "course_id": enrollment.course_id,

            "full_name": enrollment.full_name,
            "email": enrollment.email,
            "phone": enrollment.phone,

            "parent_name": enrollment.parent_name,
            "parent_phone": enrollment.parent_phone,

            "highest_qualification": (
                enrollment.highest_qualification
            ),

            "address": enrollment.address,
            "payment_plan": enrollment.payment_plan,

            "course_title": course.title,
            "course_image": course.image,
            "course_duration": course.duration,

            "total_fee": enrollment.total_fee,
            "status": enrollment.status,
            "enrolled_at": enrollment.enrolled_at
        }

        for enrollment, course in results
    ]


# ==========================================
# GET USERS ENROLLED IN A COURSE
# ADMIN ONLY
# ==========================================

@router.get(
    "/admin/course/{course_id}",
    response_model=list[AdminEnrollmentResponse],
    tags=["Admin"]
)
def get_course_enrollments(
    course_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin)
):

    # ==========================================
    # CHECK COURSE EXISTS
    # ==========================================

    course = db.query(Course).filter(
        Course.id == course_id
    ).first()

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )


    # ==========================================
    # GET ENROLLMENTS FOR THIS COURSE
    # ==========================================

    enrollments = db.query(Enrollment).filter(
        Enrollment.course_id == course_id
    ).order_by(
        Enrollment.enrolled_at.desc()
    ).all()


    # ==========================================
    # RETURN STUDENT DETAILS
    # ==========================================

    return [
        {
            "enrollment_id": enrollment.id,
            "user_id": enrollment.user_id,

            "full_name": enrollment.full_name,
            "email": enrollment.email,
            "phone": enrollment.phone,

            "parent_name": enrollment.parent_name,
            "parent_phone": enrollment.parent_phone,

            "highest_qualification": (
                enrollment.highest_qualification
            ),

            "address": enrollment.address,
            "payment_plan": enrollment.payment_plan,

            "total_fee": enrollment.total_fee,
            "status": enrollment.status,
            "enrolled_at": enrollment.enrolled_at
        }

        for enrollment in enrollments
    ]






# ==========================================
# UPDATE ENROLLMENT STATUS
# ADMIN ONLY
# ==========================================

@router.put(
    "/admin/{enrollment_id}/status",
    tags=["Admin"]
)
def update_enrollment_status(
    enrollment_id: int,
    status_data: EnrollmentStatusUpdate,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_admin)
):

    # ==========================================
    # FIND ENROLLMENT
    # ==========================================

    enrollment = db.query(Enrollment).filter(
        Enrollment.id == enrollment_id
    ).first()

    if not enrollment:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    # ==========================================
    # ONLY APPROVED STATUS IS ALLOWED
    # ==========================================

    if status_data.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Status can only be changed to approved"
        )

    # ==========================================
    # UPDATE STATUS
    # ==========================================

    enrollment.status = "approved"

    db.commit()
    db.refresh(enrollment)

    return {
        "message": "Enrollment approved successfully",
        "enrollment_id": enrollment.id,
        "status": enrollment.status
    }
