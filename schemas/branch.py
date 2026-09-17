from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict


class BranchCreate(BaseModel):
    name: str
    location: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None


class BranchResponse(BaseModel):
    id: int
    name: str
    location: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    status: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True
    )