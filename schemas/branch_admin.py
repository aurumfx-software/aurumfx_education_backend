from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict


# ==========================================
# CREATE BRANCH ADMIN
# ==========================================

class BranchAdminCreate(BaseModel):
    branch_id: int
    branch_admin_id: str
    password: str

    name: str
    email: EmailStr
    phone: Optional[str] = None


# ==========================================
# BRANCH ADMIN RESPONSE
# ==========================================

class BranchAdminResponse(BaseModel):
    id: int
    branch_id: int
    branch_admin_id: str

    name: str
    email: EmailStr
    phone: Optional[str] = None

    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)