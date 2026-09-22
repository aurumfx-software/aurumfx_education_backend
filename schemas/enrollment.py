from datetime import datetime
from pydantic import BaseModel


# ==========================================
# STUDENT ENROLLMENT RESPONSE
# ==========================================

class EnrollmentResponse(BaseModel):
    id: int
    user_id: int
    course_id: int
    branch_id: int

    name: str
    email: str
    phone: str

    parent_name: str | None = None
    parent_phone: str | None = None

    highest_qualification: str | None = None
    address: str | None = None

    course_title: str
    course_image: str | None = None
    course_duration: str

    total_fee: float

    # Payment status
    status: str

    # Branch approval status
    course_status: str

    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None

    created_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# BRANCH ADMIN ENROLLMENT RESPONSE
# ==========================================

class AdminEnrollmentResponse(BaseModel):
    enrollment_id: int
    user_id: int
    course_id: int
    branch_id: int

    name: str
    email: str
    phone: str

    parent_name: str | None = None
    parent_phone: str | None = None

    highest_qualification: str | None = None
    address: str | None = None

    course_title: str
    course_image: str | None = None
    course_duration: str

    total_fee: float

    # Payment status
    status: str

    # Branch approval status
    course_status: str

    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None

    created_at: datetime