from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict


class BranchAdminCreate(BaseModel):
    branch_id: int
    password: str
    name: str
    email: EmailStr
    phone: Optional[str] = None


class BranchAdminResponse(BaseModel):
    id: int
    branch_id: int
    branch_admin_id: Optional[str] = None
    name: str
    email: EmailStr
    phone: Optional[str] = None
    role: str
    status: str

    model_config = ConfigDict(from_attributes=True)


    