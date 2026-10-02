from typing import List
from ipaddress import ip_address

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import User, Branch, Staff

from schemas.user import (
    UserRegister,
    UserLogin,
    UserResponse,
    Changepassword,
    BranchAdminLogin,
    SuperAdminLogin,
)
from schemas.staff import StaffLogin

from utils.password import hash_password, verify_password
from utils.jwt import create_access_token, decode_access_token


router = APIRouter(
    prefix="/auth"
)


# ==========================================
# HTTP BEARER AUTHENTICATION
# ==========================================

security = HTTPBearer()


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
# USER REGISTER
# ==========================================

@router.post(
    "/register",
    response_model=UserResponse,
    tags=["User Authentication"]
)
def register(
    user: UserRegister,
    db: Session = Depends(get_db)
):

    # ==========================================
    # CHECK WHETHER EMAIL ALREADY EXISTS
    # ==========================================

    existing_user = (
        db.query(User)
        .filter(User.email == user.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # ==========================================
    # HASH PASSWORD
    # ==========================================

    hashed_password = hash_password(
        user.password
    )

    # ==========================================
    # CREATE USER
    # ==========================================

    new_user = User(
        name=user.name,
        email=user.email,
        phone=user.phone,

        parent_name=user.parent_name,
        parent_phone=user.parent_phone,

        highest_qualification=user.highest_qualification,

        address=user.address,

        password_hash=hashed_password,

        profile_image=None,

        role="user",

        status="Active"
    )

    # ==========================================
    # SAVE USER
    # ==========================================

    db.add(new_user)

    db.commit()

    db.refresh(new_user)

    return new_user


# ==========================================
# USER LOGIN
# ==========================================

@router.post(
    "/login",
    tags=["User Authentication"]
)
def login(
    user: UserLogin,
    db: Session = Depends(get_db)
):
    login_identifier = user.staff_code or user.email

    # ==========================================
    # FIND USER
    # ==========================================

    db_user = (
        db.query(User)
        .filter(User.email == login_identifier)
        .first()
    )

    if not db_user:
        db_user = (
            db.query(User)
            .join(Staff, Staff.user_id == User.id)
            .filter(
                Staff.staff_code == login_identifier.strip().upper(),
                Staff.status == "Active",
                User.role == "staff",
            )
            .first()
        )

    if not db_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # ==========================================
    # VERIFY PASSWORD
    # ==========================================

    password_correct = verify_password(
        user.password,
        db_user.password_hash
    )

    if not password_correct:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # ==========================================
    # CHECK ACTIVE STATUS
    # ==========================================

    if db_user.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="User account is inactive"
        )

    # ==========================================
    # RESTRICT SUPER ADMIN
    # ==========================================

    if db_user.role == "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Super admin accounts must use the Super Admin Login API (/auth/super-admin-login)"
        )

    # ==========================================
    # CREATE JWT
    # ==========================================

    token = create_access_token(
        user_id=db_user.id,
        role=db_user.role
    )

    # ==========================================
    # RESPONSE
    # ==========================================

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer",
        "role": db_user.role,
        "user_id": db_user.id,
        "name": db_user.name,
        "email": db_user.email,
        "staff_code": (
            db.query(Staff.staff_code)
            .filter(Staff.user_id == db_user.id)
            .scalar()
            if db_user.role == "staff"
            else None
        ),
    }


# ==========================================
# SUPER ADMIN LOGIN
# ==========================================

@router.post(
    "/super-admin-login",
    tags=["Super Admin"]
)
def admin_login(
    user: SuperAdminLogin,
    db: Session = Depends(get_db)
):

    # ==========================================
    # FIND USER
    # ==========================================

    db_user = (
        db.query(User)
        .filter(User.email == user.email)
        .first()
    )

    if not db_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # ==========================================
    # VERIFY PASSWORD
    # ==========================================

    password_correct = verify_password(
        user.password,
        db_user.password_hash
    )

    if not password_correct:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # ==========================================
    # CHECK SUPER ADMIN ROLE
    # ==========================================

    if db_user.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Super admin access required"
        )

    # ==========================================
    # CHECK ACTIVE STATUS
    # ==========================================

    if db_user.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Super admin account is inactive"
        )

    # ==========================================
    # CREATE JWT
    # ==========================================

    token = create_access_token(
        user_id=db_user.id,
        role=db_user.role
    )

    # ==========================================
    # RESPONSE
    # ==========================================

    return {
        "message": "Super admin login successful",
        "access_token": token,
        "token_type": "bearer",
        "role": db_user.role,
        "user_id": db_user.id,
        "name": db_user.name,
        "email": db_user.email
    }


# ==========================================
# GET CURRENT USER
# ==========================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):

    # ==========================================
    # GET TOKEN FROM AUTHORIZATION HEADER
    # ==========================================

    token = credentials.credentials

    # ==========================================
    # DECODE JWT
    # ==========================================

    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    # ==========================================
    # GET USER ID
    # ==========================================

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    # ==========================================
    # CONVERT USER ID
    # ==========================================

    try:
        user_id = int(user_id)

    except (TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    # ==========================================
    # FIND USER
    # ==========================================

    db_user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if not db_user:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    # ==========================================
    # CHECK ACTIVE STATUS
    # ==========================================

    if db_user.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="User account is inactive"
        )

    return db_user


# ==========================================
# GET CURRENT SUPER ADMIN
# ==========================================

def get_current_super_admin(
    current_user: User = Depends(get_current_user)
):

    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Super admin access required"
        )

    return current_user


# ==========================================
# GET CURRENT USER PROFILE
# ==========================================

@router.get(
    "/me",
    response_model=UserResponse,
    tags=["User Authentication"]
)
def read_current_user(
    current_user: User = Depends(get_current_user)
):

    return current_user


# ==========================================
# CHANGE SUPER ADMIN PASSWORD
# ==========================================

@router.put(
    "/super-admin/change-password",
    tags=["Super Admin"]
)
def change_admin_password(
    password_data: Changepassword,
    current_user: User = Depends(get_current_super_admin),
    db: Session = Depends(get_db)
):

    # ==========================================
    # VERIFY CURRENT PASSWORD
    # ==========================================

    password_correct = verify_password(
        password_data.current_password,
        current_user.password_hash
    )

    if not password_correct:
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect"
        )

    # ==========================================
    # HASH NEW PASSWORD
    # ==========================================

    new_password_hash = hash_password(
        password_data.new_password
    )

    # ==========================================
    # UPDATE PASSWORD
    # ==========================================

    current_user.password_hash = new_password_hash

    db.commit()

    return {
        "message": "Super admin password updated successfully"
    }


# ==========================================
# BRANCH ADMIN LOGIN
# ==========================================

@router.post(
    "/branch-admin-login",
    tags=["Branch Admin Authentication"]
)
def branch_admin_login(
    request: Request,
    login_data: BranchAdminLogin,
    db: Session = Depends(get_db)
):

    # ==========================================
    # FIND BRANCH ADMIN
    # ==========================================

    login_identifier = (
        login_data.branch_admin_id or login_data.email or ""
    ).strip()
    db_user = (
        db.query(User)
        .filter(
            User.role == "branch_admin",
            or_(
                User.email == login_identifier,
                User.branch_admin_id == login_identifier.upper(),
            ),
        )
        .first()
    )

    if not db_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid branch admin ID or password"
        )

    # ==========================================
    # CHECK PASSWORD
    # ==========================================

    password_correct = verify_password(
        login_data.password,
        db_user.password_hash
    )

    if not password_correct:
        raise HTTPException(
            status_code=401,
            detail="Invalid branch admin ID or password"
        )

    # ==========================================
    # CHECK ADMIN STATUS
    # ==========================================

    if db_user.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Branch admin account is inactive"
        )

    # ==========================================
    # CHECK BRANCH
    # ==========================================

    branch = (
        db.query(Branch)
        .filter(Branch.id == db_user.branch_id)
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

    if branch.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Branch is inactive"
        )

    if db_user.allowed_ip_address:
        client_host = request.client.host if request.client else None
        try:
            client_ip = ip_address(client_host)
            allowed_ip = ip_address(db_user.allowed_ip_address)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=403,
                detail="Unable to verify the login IP address",
            )

        if client_ip != allowed_ip:
            raise HTTPException(
                status_code=403,
                detail="Login is only allowed from the registered IP address",
            )

    # ==========================================
    # CREATE JWT
    # ==========================================

    token = create_access_token(
        user_id=db_user.id,
        role=db_user.role
    )

    # ==========================================
    # RESPONSE
    # ==========================================

    return {
        "message": "Branch admin login successful",
        "access_token": token,
        "token_type": "bearer",
        "role": db_user.role,
        "branch_admin_id": db_user.branch_admin_id,
        "branch_id": db_user.branch_id,
        "user_id": db_user.id,
        "name": db_user.name,
        "email": db_user.email
    }


@router.post(
    "/staff-login",
    tags=["Staff Authentication"],
)
def staff_login(
    login_data: StaffLogin,
    db: Session = Depends(get_db),
):
    staff_code = login_data.staff_code.strip().upper()
    staff = (
        db.query(Staff, User)
        .join(User, User.id == Staff.user_id)
        .filter(
            Staff.staff_code == staff_code,
            Staff.status == "Active",
            User.role == "staff",
            User.status == "Active",
        )
        .first()
    )
    if not staff:
        raise HTTPException(
            status_code=401,
            detail="Invalid staff ID or password",
        )

    staff_record, staff_user = staff
    if not verify_password(login_data.password, staff_user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Invalid staff ID or password",
        )

    branch = db.query(Branch).filter(Branch.id == staff_record.branch_id).first()
    if not branch or branch.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Staff branch is inactive",
        )

    token = create_access_token(
        user_id=staff_user.id,
        role=staff_user.role,
    )
    return {
        "message": "Staff login successful",
        "access_token": token,
        "token_type": "bearer",
        "role": staff_user.role,
        "user_id": staff_user.id,
        "staff_id": staff_record.id,
        "staff_code": staff_record.staff_code,
        "name": staff_record.name,
        "email": staff_record.email,
        "branch_id": staff_record.branch_id,
        "verification_status": staff_record.verification_status,
    }


# ==========================================
# LOGOUT
# ==========================================

@router.post(
    "/logout",
    tags=["Authentication"]
)
def logout():

    return {
        "message": "Logout successful"
    }