from datetime import date, datetime

from pydantic import BaseModel


class StaffAttendanceCreate(BaseModel):
    staff_id: int
    date: date
    status: str


class StaffAttendanceUpdate(BaseModel):
    status: str


class StaffAttendanceResponse(BaseModel):
    id: int
    staff_id: int
    branch_id: int
    date: date
    status: str
    marked_by: int
    marked_at: datetime | None = None