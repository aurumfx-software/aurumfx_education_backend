from datetime import date

from pydantic import BaseModel


class BranchAdminAttendanceCreate(BaseModel):
    date: date
    status: str


class BranchAdminAttendanceUpdate(BaseModel):
    status: str