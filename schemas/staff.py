from datetime import datetime
from pydantic import BaseModel


# ==========================================
# CREATE STAFF
# ==========================================

class StaffCreate(BaseModel):
    name: str
    email: str
    password: str
    phone: str
    course_id: int
    address: str


# ==========================================
# UPDATE STAFF
# ==========================================

class StaffUpdate(BaseModel):
    name: str
    email: str
    password: str | None = None
    phone: str
    course_id: int
    address: str


# ==========================================
# STAFF RESPONSE
# ==========================================

class StaffResponse(BaseModel):
    id: int
    user_id: int
    branch_id: int

    name: str
    email: str
    phone: str

    course_id: int
    course_name: str

    address: str | None = None

    status: str

    created_at: datetime