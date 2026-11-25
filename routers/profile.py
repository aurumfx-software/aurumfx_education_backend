from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Form,
    UploadFile,
    File
)

from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, Course, Enrollment, User

from routers.auth import get_current_user
from routers.enrollments import (
    enrollment_payment_history,
    enrollment_payment_review_summary,
    enrollment_payment_summary,
    serialize_enrollment_payment_history,
)

from utils.spaces import (
    spaces_client,
    SPACES_BUCKET,
    SPACES_PUBLIC_URL
)


router = APIRouter(
    prefix="/profile"
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
# GET USER PROFILE
# USER ONLY
# ==========================================

@router.get(
    "/",
    tags=["Student Profile"]
)
def get_user_profile(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    user = db.query(User).filter(
        User.id == current_user.id
    ).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    enrollment_rows = (
        db.query(Enrollment, Course, Branch)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Branch, Branch.id == Enrollment.branch_id)
        .filter(Enrollment.user_id == user.id)
        .order_by(Enrollment.created_at.desc(), Enrollment.id.desc())
        .all()
    )
    enrollments = []
    for enrollment, course, branch in enrollment_rows:
        payment_rows = enrollment_payment_history(db, enrollment)
        enrollments.append(
            {
                "enrollment_id": enrollment.id,
                "course_id": course.id,
                "course_title": enrollment.course_title or course.title,
                "branch_id": branch.id,
                "branch_name": branch.name,
                "total_fee": enrollment.total_fee,
                "payment_status": enrollment.status,
                "course_status": enrollment.course_status,
                "branch_approval_status": enrollment.branch_approval_status,
                "super_admin_approval_status": (
                    enrollment.super_admin_approval_status
                ),
                **enrollment_payment_summary(db, enrollment),
                **enrollment_payment_review_summary(
                    db, enrollment, payment_rows
                ),
                "payments": serialize_enrollment_payment_history(
                    db, enrollment, payment_rows
                ),
                "razorpay_order_id": enrollment.razorpay_order_id,
                "razorpay_payment_id": enrollment.razorpay_payment_id,
                "created_at": enrollment.created_at,
            }
        )

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "parent_name": user.parent_name,
        "parent_phone": user.parent_phone,
        "highest_qualification": user.highest_qualification,
        "address": user.address,
        "profile_image": user.profile_image,
        "enrollments": enrollments,
    }


# ==========================================
# UPDATE USER PROFILE
# USER ONLY
# ==========================================

@router.put(
    "/",
    tags=["Student Profile"]
)
async def update_user_profile(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    parent_name: str = Form(...),
    parent_phone: str = Form(...),
    highest_qualification: str = Form(...),
    address: str = Form(...),

    image: UploadFile | None = File(None),

    db: Session = Depends(get_db),

    current_user=Depends(get_current_user)
):

    user = db.query(User).filter(
        User.id == current_user.id
    ).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )


    # ==========================================
    # UPDATE USER DATA
    # ==========================================

    user.name = name
    user.email = email
    user.phone = phone

    user.parent_name = parent_name
    user.parent_phone = parent_phone

    user.highest_qualification = (
        highest_qualification
    )

    user.address = address


    # ==========================================
    # UPLOAD PROFILE IMAGE
    # ==========================================

    if image:

        file_name = (
            f"profiles/{user.id}-{image.filename}"
        )

        file_content = await image.read()

        spaces_client.put_object(
            Bucket=SPACES_BUCKET,
            Key=file_name,
            Body=file_content,
            ContentType=image.content_type,
            ACL="public-read"
        )

        user.profile_image = (
            f"{SPACES_PUBLIC_URL}/{file_name}"
        )


    # ==========================================
    # SAVE CHANGES
    # ==========================================

    db.commit()

    db.refresh(user)


    # ==========================================
    # RETURN UPDATED PROFILE
    # ==========================================

    return {
        "message": "Profile updated successfully",

        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,

        "parent_name": user.parent_name,
        "parent_phone": user.parent_phone,

        "highest_qualification": (
            user.highest_qualification
        ),

        "address": user.address,

        "profile_image": user.profile_image
    }