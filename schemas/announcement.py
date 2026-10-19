from datetime import datetime
from typing import Literal

from pydantic import BaseModel


AnnouncementAudience = Literal["students", "staff", "branch_admin", "all", "both"]
BranchAdminAnnouncementAudience = Literal["students", "staff", "both"]


class AnnouncementCreate(BaseModel):
    title: str
    message: str
    audience: AnnouncementAudience = "both"


class AnnouncementResponse(BaseModel):
    id: int
    branch_id: int | None = None
    title: str
    message: str
    audience: AnnouncementAudience = "both"
    image: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True