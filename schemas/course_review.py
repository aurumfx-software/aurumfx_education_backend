from datetime import datetime

from pydantic import BaseModel, Field


class CourseReviewCreate(BaseModel):
    course_id: int
    review: str = Field(min_length=1, max_length=2000)
    rating: int | None = Field(default=None, ge=1, le=5)


class CourseReviewResponse(BaseModel):
    id: int
    student_id: int
    student_name: str
    course_id: int
    course_title: str
    branch_id: int
    branch_name: str
    review: str
    rating: int | None
    created_at: datetime | None
