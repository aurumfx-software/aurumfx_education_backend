from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class EnquiryCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    parents_phone: Optional[str] = Field(default=None, alias="parentsPhone")
    course: Optional[str] = None
    qualification: Optional[str] = None
    message: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)



class EnquiryStatusUpdate(BaseModel):
    status: str


class EnquiryResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: Optional[str] = None
    parents_phone: Optional[str] = None
    course: Optional[str] = None
    qualification: Optional[str] = None
    message: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)




