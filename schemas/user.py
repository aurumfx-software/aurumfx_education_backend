from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict, model_validator


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: Optional[str] = None

    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    highest_qualification: Optional[str] = None
    address: Optional[str] = None


class UserLogin(BaseModel):
    email: str | None = None
    staff_code: str | None = None
    password: str

    @model_validator(mode="after")
    def require_login_identifier(self):
        if not self.email and not self.staff_code:
            raise ValueError("email or staff_code is required")
        return self

    
class BranchAdminLogin(BaseModel):
    email: str | None = None
    branch_admin_id: str | None = None
    password: str

    @model_validator(mode="after")
    def require_login_identifier(self):
        if not self.email and not self.branch_admin_id:
            raise ValueError("email or branch_admin_id is required")
        if self.email and self.branch_admin_id:
            raise ValueError("provide email or branch_admin_id, not both")
        return self


class SuperAdminLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: Optional[str] = None

    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None
    highest_qualification: Optional[str] = None
    address: Optional[str] = None
    profile_image: Optional[str] = None

    role: str

    status: str

    created_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True
    )


class Changepassword(BaseModel):
    current_password: str
    new_password: str