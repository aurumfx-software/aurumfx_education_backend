from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import User

from schemas.user import (
    UserRegister,
    UserLogin,
    UserResponse,
    Changepassword
)

from utils.password import hash_password, verify_password

from utils.jwt import create_access_token, decode_access_token


router = APIRouter(
    prefix="/auth"
)


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

        is_active=True
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
    # CHECK ACTIVE STATUS
    # ==========================================

    if not db_user.is_active:
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

    return {
        "access_token": token,
        "token_type": "bearer"
    }


# ==========================================
# SUPER ADMIN LOGIN
# ==========================================

@router.post(
    "/super-admin-login",
    tags=["Super Admin"]
)
def admin_login(
    user: UserLogin,
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

    if not db_user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Super admin account is inactive"
        )

    # ==========================================
    # CREATE SUPER ADMIN JWT
    # ==========================================

    token = create_access_token(
        user_id=db_user.id,
        role=db_user.role
    )

    return {
        "access_token": token,
        "token_type": "bearer"
    }


# ==========================================
# GET CURRENT USER
# ==========================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):

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
    # FIND USER
    # ==========================================

    db_user = (
        db.query(User)
        .filter(User.id == int(user_id))
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

    if not db_user.is_active:
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
# GET ALL NON-SUPER-ADMIN USERS
# ==========================================

# @router.get(
#     "/users",
#     response_model=List[UserResponse],
#     tags=["Super Admin"]
# )
# def get_all_users(
#     db: Session = Depends(get_db),
#     current_admin: User = Depends(get_current_super_admin)
# ):

#     users = (
#         db.query(User)
#         .filter(User.role != "super_admin")
#         .order_by(User.id.asc())
#         .all()
#     )

#     return users


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