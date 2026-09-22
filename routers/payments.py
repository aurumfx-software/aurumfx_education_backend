import os
import hmac
import hashlib
import requests

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Enrollment, Course, User

from routers.auth import get_current_user


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/payments",
    tags=["Student Payments"]
)


# ============================================================
# RAZORPAY CONFIGURATION
# ============================================================

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

RAZORPAY_API_URL = "https://api.razorpay.com/v1"


# ============================================================
# DATABASE DEPENDENCY
# ============================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class CreateOrderRequest(BaseModel):
    course_id: int


class VerifyPaymentRequest(BaseModel):
    enrollment_id: int
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# ============================================================
# CHECK RAZORPAY CONFIGURATION
# ============================================================

def check_razorpay_config():

    if not RAZORPAY_KEY_ID:
        raise HTTPException(
            status_code=500,
            detail="RAZORPAY_KEY_ID is not configured"
        )

    if not RAZORPAY_KEY_SECRET:
        raise HTTPException(
            status_code=500,
            detail="RAZORPAY_KEY_SECRET is not configured"
        )


# ============================================================
# CREATE ENROLLMENT + RAZORPAY ORDER
# ============================================================

@router.post(
    "/create-order"
)
def create_order(
    payment_data: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # ========================================================
    # ONLY STUDENTS
    # ========================================================

    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can make payments"
        )

    # ========================================================
    # CHECK RAZORPAY CONFIGURATION
    # ========================================================

    check_razorpay_config()

    # ========================================================
    # FIND ACTIVE COURSE
    # ========================================================

    course = (
        db.query(Course)
        .filter(
            Course.id == payment_data.course_id,
            Course.is_active == True
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )

    # ========================================================
    # CHECK COURSE BRANCH
    # ========================================================

    if not course.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Course is not assigned to a branch"
        )

    # ========================================================
    # CHECK EXISTING ENROLLMENT
    # ========================================================

    existing_enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.user_id == current_user.id,
            Enrollment.course_id == course.id
        )
        .first()
    )

    # ========================================================
    # ALREADY PAID
    # ========================================================

    if existing_enrollment:

        if existing_enrollment.status == "paid":
            raise HTTPException(
                status_code=400,
                detail="You are already enrolled in this course"
            )

        # If pending enrollment already exists,
        # reuse it instead of creating another enrollment.

        enrollment = existing_enrollment

    else:

        # ====================================================
        # CREATE NEW PENDING ENROLLMENT
        # ====================================================

        enrollment = Enrollment(
            user_id=current_user.id,
            course_id=course.id,

            # Store course snapshot
            course_title=course.title,

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
            status="pending",

            # Branch approval status
            course_status="pending",

            # Razorpay
            razorpay_order_id=None,
            razorpay_payment_id=None
        )

        db.add(enrollment)

    # ========================================================
    # FLUSH
    #
    # This gives us enrollment.id before committing.
    # ========================================================

    db.flush()

    # ========================================================
    # AMOUNT
    #
    # Razorpay expects amount in paise
    # ========================================================

    amount_paise = int(
        round(enrollment.total_fee * 100)
    )

    if amount_paise <= 0:

        db.rollback()

        raise HTTPException(
            status_code=400,
            detail="Invalid payment amount"
        )

    # ========================================================
    # CREATE RAZORPAY ORDER
    # ========================================================

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": f"ENR-{enrollment.id}",
        "notes": {
            "enrollment_id": str(enrollment.id),
            "user_id": str(current_user.id),
            "course_id": str(course.id),
            "course_title": course.title
        }
    }

    try:

        razorpay_response = requests.post(
            f"{RAZORPAY_API_URL}/orders",
            auth=(
                RAZORPAY_KEY_ID,
                RAZORPAY_KEY_SECRET
            ),
            json=payload,
            timeout=30
        )

    except requests.RequestException as e:

        db.rollback()

        raise HTTPException(
            status_code=502,
            detail=f"Unable to connect to Razorpay: {str(e)}"
        )

    # ========================================================
    # CHECK RAZORPAY RESPONSE
    # ========================================================

    if not razorpay_response.ok:

        db.rollback()

        try:
            error_data = razorpay_response.json()
        except Exception:
            error_data = razorpay_response.text

        print(
            "Razorpay Order Error:",
            error_data
        )

        raise HTTPException(
            status_code=502,
            detail="Razorpay failed to create order"
        )

    razorpay_data = razorpay_response.json()

    razorpay_order_id = razorpay_data.get("id")

    if not razorpay_order_id:

        db.rollback()

        raise HTTPException(
            status_code=502,
            detail="Razorpay did not return an order ID"
        )

    # ========================================================
    # SAVE RAZORPAY ORDER ID
    # ========================================================

    enrollment.razorpay_order_id = razorpay_order_id

    # Payment is still pending until verification
    enrollment.status = "pending"

    # Course approval is also pending
    enrollment.course_status = "pending"

    # ========================================================
    # COMMIT ENROLLMENT
    # ========================================================

    db.commit()

    db.refresh(enrollment)

    # ========================================================
    # RETURN ORDER DETAILS
    # ========================================================

    return {
        "success": True,

        "message": (
            "Enrollment and Razorpay order "
            "created successfully"
        ),

        "enrollment_id": enrollment.id,

        # Payment status
        "status": enrollment.status,

        # Branch approval status
        "course_status": enrollment.course_status,

        # Razorpay order
        "order_id": razorpay_order_id,

        # Amount
        "amount": enrollment.total_fee,
        "amount_paise": amount_paise,
        "currency": "INR",

        # Razorpay public key
        "razorpay_key_id": RAZORPAY_KEY_ID,

        # Course
        "course": {
            "id": course.id,
            "title": course.title,
            "image": course.image
        },

        # Student
        "student": {
            "name": current_user.name,
            "email": current_user.email,
            "phone": current_user.phone
        }
    }


# ============================================================
# VERIFY RAZORPAY PAYMENT
# ============================================================

@router.post(
    "/verify"
)
def verify_payment(
    payment_data: VerifyPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # ========================================================
    # ONLY STUDENTS
    # ========================================================

    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can verify payments"
        )

    # ========================================================
    # CHECK RAZORPAY CONFIGURATION
    # ========================================================

    check_razorpay_config()

    # ========================================================
    # FIND ENROLLMENT
    # ========================================================

    enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.id == payment_data.enrollment_id,
            Enrollment.user_id == current_user.id
        )
        .first()
    )

    if not enrollment:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    # ========================================================
    # ALREADY PAID
    # ========================================================

    if enrollment.status == "paid":

        return {
            "success": True,
            "message": "Payment already verified",

            "status": "paid",

            "course_status": enrollment.course_status,

            "enrollment_id": enrollment.id,

            "razorpay_order_id": enrollment.razorpay_order_id,

            "razorpay_payment_id": enrollment.razorpay_payment_id
        }

    # ========================================================
    # CHECK ENROLLMENT ORDER ID
    # ========================================================

    if not enrollment.razorpay_order_id:

        raise HTTPException(
            status_code=400,
            detail="No Razorpay order found for this enrollment"
        )

    # ========================================================
    # VERIFY ORDER ID
    # ========================================================

    if (
        enrollment.razorpay_order_id
        != payment_data.razorpay_order_id
    ):

        raise HTTPException(
            status_code=400,
            detail="Razorpay order ID does not match"
        )

    # ========================================================
    # CREATE SIGNATURE
    # ========================================================

    generated_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),

        (
            payment_data.razorpay_order_id
            + "|"
            + payment_data.razorpay_payment_id
        ).encode("utf-8"),

        hashlib.sha256
    ).hexdigest()

    # ========================================================
    # VERIFY SIGNATURE
    # ========================================================

    if not hmac.compare_digest(
        generated_signature,
        payment_data.razorpay_signature
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid Razorpay payment signature"
        )

    # ========================================================
    # PAYMENT VERIFIED
    # ========================================================

    enrollment.razorpay_payment_id = (
        payment_data.razorpay_payment_id
    )

    # Payment becomes paid
    enrollment.status = "paid"

    # Course remains pending until
    # branch admin approves it
    enrollment.course_status = "pending"

    # ========================================================
    # SAVE
    # ========================================================

    db.commit()

    db.refresh(enrollment)

    # ========================================================
    # SUCCESS
    # ========================================================

    return {
        "success": True,

        "message": "Payment verified successfully",

        "enrollment_id": enrollment.id,

        # Payment status
        "status": enrollment.status,

        # Branch approval status
        "course_status": enrollment.course_status,

        "razorpay_order_id": enrollment.razorpay_order_id,

        "razorpay_payment_id": enrollment.razorpay_payment_id
    }