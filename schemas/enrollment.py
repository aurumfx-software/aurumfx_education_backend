from datetime import datetime
from pydantic import BaseModel


class EnrollmentCreate(BaseModel):
    course_id: int
    full_name: str
    email: str
    phone: str
    parent_name: str
    parent_phone: str
    highest_qualification: str
    address: str
    payment_plan: str


class EnrollmentResponse(BaseModel):
    id: int
    user_id: int
    course_id: int

    full_name: str
    email: str
    phone: str

    parent_name: str
    parent_phone: str

    highest_qualification: str
    address: str
    payment_plan: str

    course_title: str
    course_image: str | None = None
    course_duration: str

    total_fee: float
    status: str
    enrolled_at: datetime

    class Config:
        from_attributes = True


class AdminEnrollmentResponse(BaseModel):
    enrollment_id: int
    user_id: int

    full_name: str
    email: str
    phone: str

    parent_name: str
    parent_phone: str

    highest_qualification: str
    address: str
    payment_plan: str

    total_fee: float
    status: str
    enrolled_at: datetime