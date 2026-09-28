from datetime import datetime
from pydantic import BaseModel, Field


# ==========================================
# CREATE STAFF
# ==========================================

class StaffCreate(BaseModel):
    name: str
    email: str
    password: str
    phone: str
    course_id: int | None = None
    course_ids: list[int] | None = None
    address: str
    salary: float


# ==========================================
# UPDATE STAFF
# ==========================================

class StaffUpdate(BaseModel):
    name: str
    email: str
    password: str | None = None
    phone: str
    course_id: int | None = None
    course_ids: list[int] | None = None
    address: str
    salary: float


# ==========================================
# STAFF RESPONSE
# ==========================================

class StaffResponse(BaseModel):
    id: int
    user_id: int
    branch_id: int
    staff_code: str | None = None

    name: str
    email: str
    phone: str

    course_id: int
    course_name: str
    course_ids: list[int] = Field(default_factory=list)
    course_names: list[str] = Field(default_factory=list)

    address: str | None = None

    salary: float

    status: str

    created_at: datetime