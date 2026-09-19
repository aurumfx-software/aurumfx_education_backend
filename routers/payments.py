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


router = APIRouter(
    prefix="/payments",
    tags=["Payments"]
)


# ==========================================
# RAZORPAY CONFIGURATION
# ==========================================

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

RAZORPAY_API_URL = "https://api.razorpay.com/v1"


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
# REQUEST SCHEMAS
# ==========================================

class CreateOrderRequest(BaseModel):
    enrollment_id: int


class VerifyPaymentRequest(BaseModel):
    enrollment_id: int
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# ==========================================
# CHECK RAZORPAY CONFIGURATION
# ==========================================

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


# ==========================================
# CREATE RAZORPAY ORDER
# ==========================================

@router.post("/create-order")
def create_order(
    payment_data: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # ==========================================
    # ONLY STUDENTS
    # ==========================================

    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can make payments"
        )

    # ==========================================
    # CHECK RAZORPAY CONFIGURATION
    # ==========================================

    check_razorpay_config()

    # ==========================================
    # FIND ENROLLMENT
    # ==========================================

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

    # ==========================================
    # CHECK PAYMENT STATUS
    # ==========================================

    if enrollment.status == "paid":
        raise HTTPException(
            status_code=400,
            detail="This course has already been paid for"
        )

    # ==========================================
    # FIND COURSE
    # ==========================================

    course = (
        db.query(Course)
        .filter(
            Course.id == enrollment.course_id
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )

    # ==========================================
    # AMOUNT
    # Razorpay expects paise
    # ==========================================

    amount_paise = int(
        round(enrollment.total_fee * 100)
    )

    if amount_paise <= 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid payment amount"
        )

    # ==========================================
    # CREATE RAZORPAY ORDER
    # ==========================================

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

        raise HTTPException(
            status_code=502,
            detail=f"Unable to connect to Razorpay: {str(e)}"
        )

    # ==========================================
    # CHECK RAZORPAY RESPONSE
    # ==========================================

    if not razorpay_response.ok:

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

        raise HTTPException(
            status_code=502,
            detail="Razorpay did not return an order ID"
        )

    # ==========================================
    # SAVE ORDER ID
    # ==========================================

    enrollment.razorpay_order_id = razorpay_order_id
    enrollment.status = "pending"

    db.commit()
    db.refresh(enrollment)

    # ==========================================
    # RETURN ORDER DETAILS
    # ==========================================

    return {
        "success": True,
        "message": "Razorpay order created successfully",

        "enrollment_id": enrollment.id,

        "order_id": razorpay_order_id,

        "amount": enrollment.total_fee,

        "amount_paise": amount_paise,

        "currency": "INR",

        "razorpay_key_id": RAZORPAY_KEY_ID,

        "course": {
            "id": course.id,
            "title": course.title,
            "image": course.image
        },

        "student": {
            "name": current_user.name,
            "email": current_user.email,
            "phone": current_user.phone
        }
    }


# ==========================================
# VERIFY RAZORPAY PAYMENT
# ==========================================

@router.post("/verify")
def verify_payment(
    payment_data: VerifyPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # ==========================================
    # ONLY STUDENTS
    # ==========================================

    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can verify payments"
        )

    # ==========================================
    # CHECK RAZORPAY CONFIGURATION
    # ==========================================

    check_razorpay_config()

    # ==========================================
    # FIND ENROLLMENT
    # ==========================================

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

    # ==========================================
    # ALREADY PAID
    # ==========================================

    if enrollment.status == "paid":

        return {
            "success": True,
            "message": "Payment already verified",
            "status": "paid"
        }

    # ==========================================
    # VERIFY ORDER ID
    # ==========================================

    if not enrollment.razorpay_order_id:

        raise HTTPException(
            status_code=400,
            detail="No Razorpay order found for this enrollment"
        )

    if (
        enrollment.razorpay_order_id
        != payment_data.razorpay_order_id
    ):

        raise HTTPException(
            status_code=400,
            detail="Razorpay order ID does not match"
        )

    # ==========================================
    # CREATE SIGNATURE
    # ==========================================

    generated_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),

        (
            payment_data.razorpay_order_id
            + "|"
            + payment_data.razorpay_payment_id
        ).encode("utf-8"),

        hashlib.sha256
    ).hexdigest()

    # ==========================================
    # VERIFY SIGNATURE
    # ==========================================

    if not hmac.compare_digest(
        generated_signature,
        payment_data.razorpay_signature
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid Razorpay payment signature"
        )

    # ==========================================
    # PAYMENT VERIFIED
    # ==========================================

    enrollment.razorpay_payment_id = (
        payment_data.razorpay_payment_id
    )

    enrollment.status = "paid"

    db.commit()
    db.refresh(enrollment)

    # ==========================================
    # SUCCESS
    # ==========================================

    return {
        "success": True,
        "message": "Payment verified successfully",
        "enrollment_id": enrollment.id,
        "status": enrollment.status,
        "razorpay_order_id": enrollment.razorpay_order_id,
        "razorpay_payment_id": enrollment.razorpay_payment_id
    }