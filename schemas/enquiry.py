from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class EnquiryCreate(BaseModel):
    name: str
    email: str
    branch_id: int = Field(gt=0)
    phone: Optional[str] = None
    course: Optional[str] = None
    qualification: Optional[str] = None
    message: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)



class EnquiryStatusUpdate(BaseModel):
    status: str


class EnquiryResponse(BaseModel):
    id: int
    branch_id: int | None = None
    branch_name: str | None = None
    name: str
    email: str
    phone: Optional[str] = None
    course: Optional[str] = None
    qualification: Optional[str] = None
    message: Optional[str] = None
    status: str
    branch_admin_status: str = "pending"
    branch_admin_read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)




