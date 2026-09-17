from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, User

from schemas.branch import (
    BranchCreate,
    BranchResponse
)

from schemas.branch_admin import (
    BranchAdminCreate,
    BranchAdminResponse
)

from routers.auth import get_current_super_admin

from utils.password import hash_password


router = APIRouter(
    prefix="/super-admin/branches"
)


# ==========================================
# DATABASE DEPENDENCY
# ==========================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ==========================================
# CREATE BRANCH
# ==========================================

@router.post(
    "/",
    response_model=BranchResponse,
    tags=["Super Admin Branches creating Api"]
)
def create_branch(
    branch: BranchCreate,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

    # Check whether branch already exists

    existing_branch = (
        db.query(Branch)
        .filter(Branch.name == branch.name)
        .first()
    )

    if existing_branch:
        raise HTTPException(
            status_code=400,
            detail="Branch with this name already exists"
        )

    # Create branch

    new_branch = Branch(
        name=branch.name,
        location=branch.location,
        phone=branch.phone,
        email=branch.email,
        is_active=True
    )

    db.add(new_branch)

    db.commit()

    db.refresh(new_branch)

    return new_branch


# ==========================================
# CREATE BRANCH ADMIN
# ==========================================

@router.post(
    "/admins",
    response_model=BranchAdminResponse,
    tags=["Super Admins Branch admin Creating Api"]
)
def create_branch_admin(
    admin: BranchAdminCreate,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

    # ==========================================
    # CHECK BRANCH
    # ==========================================

    branch = (
        db.query(Branch)
        .filter(Branch.id == admin.branch_id)
        .first()
    )

    if not branch:
        raise HTTPException(
            status_code=404,
            detail="Branch not found"
        )

    # ==========================================
    # CHECK BRANCH STATUS
    # ==========================================

    if not branch.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot create admin for an inactive branch"
        )

    # ==========================================
    # CHECK BRANCH ADMIN ID
    # ==========================================

    existing_admin = (
        db.query(User)
        .filter(
            User.branch_admin_id == admin.branch_admin_id
        )
        .first()
    )

    if existing_admin:
        raise HTTPException(
            status_code=400,
            detail="Branch admin ID already exists"
        )

    # ==========================================
    # CHECK EMAIL
    # ==========================================

    existing_email = (
        db.query(User)
        .filter(User.email == admin.email)
        .first()
    )

    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # ==========================================
    # HASH PASSWORD
    # ==========================================

    hashed_password = hash_password(
        admin.password
    )

    # ==========================================
    # CREATE BRANCH ADMIN
    # ==========================================

    new_admin = User(
        name=admin.name,
        email=admin.email,
        phone=admin.phone,

        branch_admin_id=admin.branch_admin_id,

        password_hash=hashed_password,

        role="branch_admin",

        branch_id=admin.branch_id,

        is_active=True
    )

    # ==========================================
    # SAVE
    # ==========================================

    db.add(new_admin)

    db.commit()

    db.refresh(new_admin)

    return new_admin