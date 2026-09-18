from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid

from database import SessionLocal
from database_models import Branch, User

from schemas.branch import (
    BranchCreate,
    BranchUpdate,
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
    tags=["Super Admin - Branches"]
)
def create_branch(
    branch: BranchCreate,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

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

    new_branch = Branch(
        name=branch.name,
        location=branch.location,
        phone=branch.phone,
        email=branch.email,
        status="Active"
    )

    db.add(new_branch)
    db.commit()
    db.refresh(new_branch)

    return new_branch


# ==========================================
# GET ALL ACTIVE BRANCHES
# ==========================================

@router.get(
    "/",
    response_model=list[BranchResponse],
    tags=["Super Admin - Branches"]
)
def get_branches(
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

    branches = (
        db.query(Branch)
        .filter(Branch.status == "Active")
        .order_by(Branch.id.asc())
        .all()
    )

    return branches


# ============================================================
# CREATE BRANCH ADMIN
# ============================================================
@router.post(
    "/admins",
    response_model=BranchAdminResponse,
    tags=["Super Admin - Branch Admins"]
)
def create_branch_admin(
    admin: BranchAdminCreate,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

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

    if branch.status == "Deleted":
        raise HTTPException(
            status_code=400,
            detail="Cannot create admin for a deleted branch"
        )

    # ==========================================
    # CHECK IF BRANCH ALREADY HAS AN ADMIN
    # ==========================================

    existing_branch_admin = (
        db.query(User)
        .filter(
            User.branch_id == admin.branch_id,
            User.role == "branch_admin",
            User.status == "Active"
        )
        .first()
    )

    if existing_branch_admin:
        raise HTTPException(
            status_code=400,
            detail="This branch already has a branch admin"
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
    # GENERATE BRANCH ADMIN ID
    # ==========================================

    branch_admin_id = (
        f"BA-{uuid.uuid4().hex[:8].upper()}"
    )

    hashed_password = hash_password(admin.password)

    new_admin = User(
        name=admin.name,
        email=admin.email,
        phone=admin.phone,
        branch_admin_id=branch_admin_id,
        password_hash=hashed_password,
        role="branch_admin",
        branch_id=admin.branch_id,
        status="Active"
    )

    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)

    return new_admin


# ============================================================
# GET ALL ACTIVE BRANCH ADMINS
# ============================================================

@router.get(
    "/admins",
    response_model=list[BranchAdminResponse],
    tags=["Super Admin - Branch Admins"]
)
def get_branch_admins(
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

    admins = (
        db.query(User)
        .filter(
            User.role == "branch_admin",
            User.status == "Active"
        )
        .order_by(User.id.asc())
        .all()
    )

    return admins


# ============================================================
# GET SINGLE ACTIVE BRANCH ADMIN
# ============================================================

@router.get(
    "/admins/{admin_id}",
    response_model=BranchAdminResponse,
    tags=["Super Admin - Branch Admins"]
)
def get_branch_admin(
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

    admin = (
        db.query(User)
        .filter(
            User.id == admin_id,
            User.role == "branch_admin",
            User.status == "Active"
        )
        .first()
    )

    if not admin:
        raise HTTPException(
            status_code=404,
            detail="Active branch admin not found"
        )

    return admin


# ============================================================
# UPDATE BRANCH ADMIN
# ============================================================

@router.put(
    "/admins/{admin_id}",
    response_model=BranchAdminResponse,
    tags=["Super Admin - Branch Admins"]
)
def update_branch_admin(
    admin_id: int,
    admin_data: BranchAdminCreate,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

    admin = (
        db.query(User)
        .filter(
            User.id == admin_id,
            User.role == "branch_admin"
        )
        .first()
    )

    if not admin:
        raise HTTPException(
            status_code=404,
            detail="Branch admin not found"
        )

    if admin.status == "Deleted":
        raise HTTPException(
            status_code=400,
            detail="Cannot update a deleted branch admin"
        )

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

    if branch.status == "Deleted":
        raise HTTPException(
            status_code=400,
            detail="Cannot update admin of a deleted branch"
        )

    existing_email = (
        db.query(User)
        .filter(
            User.email == admin_data.email,
            User.id != admin_id
        )
        .first()
    )

    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    admin.name = admin_data.name
    admin.email = admin_data.email
    admin.phone = admin_data.phone

    if admin_data.password:
        admin.password_hash = hash_password(
            admin_data.password
        )

    db.commit()
    db.refresh(admin)

    return admin


# ============================================================
# SOFT DELETE BRANCH ADMIN
# ============================================================

@router.delete(
    "/admins/{admin_id}",
    response_model=BranchAdminResponse,
    tags=["Super Admin - Branch Admins"]
)
def delete_branch_admin(
    admin_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

    admin = (
        db.query(User)
        .filter(
            User.id == admin_id,
            User.role == "branch_admin"
        )
        .first()
    )

    if not admin:
        raise HTTPException(
            status_code=404,
            detail="Branch admin not found"
        )

    if admin.status == "Deleted":
        raise HTTPException(
            status_code=400,
            detail="Branch admin is already deleted"
        )

    # Only delete the branch admin.
    # The branch remains Active.

    admin.status = "Deleted"

    db.commit()
    db.refresh(admin)

    return admin


# ==========================================
# GET SINGLE ACTIVE BRANCH
# ==========================================

@router.get(
    "/{branch_id}",
    response_model=BranchResponse,
    tags=["Super Admin - Branches"]
)
def get_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

    branch = (
        db.query(Branch)
        .filter(
            Branch.id == branch_id,
            Branch.status == "Active"
        )
        .first()
    )

    if not branch:
        raise HTTPException(
            status_code=404,
            detail="Active branch not found"
        )

    return branch


# ==========================================
# UPDATE BRANCH
# ==========================================

@router.put(
    "/{branch_id}",
    response_model=BranchResponse,
    tags=["Super Admin - Branches"]
)
def update_branch(
    branch_id: int,
    branch_data: BranchUpdate,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

    branch = (
        db.query(Branch)
        .filter(Branch.id == branch_id)
        .first()
    )

    if not branch:
        raise HTTPException(
            status_code=404,
            detail="Branch not found"
        )

    if branch.status == "Deleted":
        raise HTTPException(
            status_code=400,
            detail="Cannot update a deleted branch"
        )

    if branch_data.name is not None:
        branch.name = branch_data.name

    if branch_data.location is not None:
        branch.location = branch_data.location

    if branch_data.phone is not None:
        branch.phone = branch_data.phone

    if branch_data.email is not None:
        branch.email = branch_data.email

    db.commit()
    db.refresh(branch)

    return branch


# ==========================================
# SOFT DELETE BRANCH
# ==========================================

@router.delete(
    "/{branch_id}",
    response_model=BranchResponse,
    tags=["Super Admin - Branches"]
)
def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_admin=Depends(get_current_super_admin)
):

    branch = (
        db.query(Branch)
        .filter(Branch.id == branch_id)
        .first()
    )

    if not branch:
        raise HTTPException(
            status_code=404,
            detail="Branch not found"
        )

    if branch.status == "Deleted":
        raise HTTPException(
            status_code=400,
            detail="Branch is already deleted"
        )

    # Delete the branch
    branch.status = "Deleted"

    # Delete all admins belonging to this branch
    branch_admins = (
        db.query(User)
        .filter(
            User.branch_id == branch_id,
            User.role == "branch_admin"
        )
        .all()
    )

    for admin in branch_admins:
        admin.status = "Deleted"

    db.commit()
    db.refresh(branch)

    return branch