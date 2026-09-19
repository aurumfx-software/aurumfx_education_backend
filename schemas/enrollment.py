from datetime import datetime
from pydantic import BaseModel


# ==========================================
# CREATE ENROLLMENT
# ==========================================

class EnrollmentCreate(BaseModel):
    course_id: int


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

    parent_name: str
    parent_phone: str

    highest_qualification: str
    address: str

    course_title: str
    course_image: str | None = None
    course_duration: str

    total_fee: float
    status: str

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

    parent_name: str
    parent_phone: str

    highest_qualification: str
    address: str

    course_title: str
    course_image: str | None = None
    course_duration: str

    total_fee: float
    status: str

    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None

    created_at: datetime