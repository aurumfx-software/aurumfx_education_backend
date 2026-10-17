from pydantic import BaseModel, Field


class StudentStaffMessageCreate(BaseModel):
    course_id: int
    staff_id: int
    message: str = Field(min_length=1, max_length=5000)


class StudentStaffReplyCreate(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
