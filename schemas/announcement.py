from datetime import datetime
from pydantic import BaseModel


class AnnouncementCreate(BaseModel):
    title: str
    message: str


class AnnouncementResponse(BaseModel):
    id: int
    title: str
    message: str
    image: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True