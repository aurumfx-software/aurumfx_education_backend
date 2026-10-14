from datetime import datetime

from pydantic import BaseModel, Field


class CourseAnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    message: str = Field(min_length=1)
    event_at: datetime | None = None


class CourseAnnouncementUpdate(CourseAnnouncementCreate):
    pass


class CourseAnnouncementResponse(BaseModel):
    id: int
    course_id: int
    course_title: str
    staff_id: int
    staff_name: str
    title: str
    message: str
    event_at: datetime | None
    created_at: datetime | None
