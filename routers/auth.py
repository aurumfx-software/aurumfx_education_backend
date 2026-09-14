from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import User

from schemas.user import UserRegister, UserLogin, UserResponse,Changepassword

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
    tags=["Authentication"]
)
def register(
    user: UserRegister,
    db: Session = Depends(get_db)
):

    # Check whether email already exists
    existing_user = db.query(User).filter(
        User.email == user.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Hash password
    hashed_password = hash_password(user.password)

    # Create user
    new_user = User(
        name=user.name,
        email=user.email,
        phone=user.phone,
        password_hash=hashed_password,
        role="user"
    )

    # Save user
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# ==========================================
# USER LOGIN
# ==========================================

@router.post("/login", tags=["Authentication"])
def login(
    user: UserLogin,
    db: Session = Depends(get_db)
):

    # Find user by email
    db_user = db.query(User).filter(
        User.email == user.email
    ).first()

    if not db_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # Verify password
    password_correct = verify_password(
        user.password,
        db_user.password_hash
    )

    if not password_correct:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # Check active status
    if not db_user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User account is inactive"
        )

    # Restrict admin accounts from using general user login
    if db_user.role == "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin accounts must use the Admin Login API (/auth/admin-login)"
        )

    # Create JWT
    token = create_access_token(
        user_id=db_user.id,
        role=db_user.role
    )

    return {
        "access_token": token,
        "token_type": "bearer"
    }


# ==========================================
# ADMIN LOGIN
# ==========================================

@router.post("/admin-login", tags=["Admin"])
def admin_login(
    user: UserLogin,
    db: Session = Depends(get_db)
):

    # Find user
    db_user = db.query(User).filter(
        User.email == user.email
    ).first()

    if not db_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # Verify password
    password_correct = verify_password(
        user.password,
        db_user.password_hash
    )

    if not password_correct:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # Check admin role
    if db_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )

    # Create admin JWT
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

    # Decode JWT
    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    # Get user ID from JWT
    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    # Find user in database
    db_user = db.query(User).filter(
        User.id == int(user_id)
    ).first()

    if not db_user:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    # Check active status
    if not db_user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User account is inactive"
        )

    return db_user


# ==========================================
# GET CURRENT ADMIN
# ==========================================

def get_current_admin(
    current_user: User = Depends(get_current_user)
):

    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )

    return current_user


# ==========================================
# GET CURRENT USER PROFILE ENDPOINT
# ==========================================

@router.get("/me", response_model=UserResponse, tags=["Authentication"])
def read_current_user(
    current_user: User = Depends(get_current_user)
):
    return current_user


# ==========================================
# GET ALL NON-ADMIN USERS (STUDENTS) ENDPOINT
# ==========================================

@router.get("/users", response_model=List[UserResponse], tags=["Admin"])
def get_all_users(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """
    Get all registered student users from database (excluding admin users)
    """
    users = db.query(User).filter(User.role != "admin").order_by(User.id.asc()).all()
    return users




# api for change admin password 


@router.put("/admin/change-password", tags=["Admin"])
def change_admin_password(
    password_data:Changepassword,
    current_user:User=Depends(get_current_admin),
    db:Session=Depends(get_db)
):
    
    
    
    # verify current password 


    password_correct=verify_password(
        password_data.current_password,
        current_user.password_hash
        
        
    )
    
    
    if not password_correct:
        raise HTTPException(
            status_code=400,
            detail="current password is incorrect "
        )
    
    
    
    
    # Hash new password
 
    new_password_hash=hash_password(
    password_data.new_password
    
    
     
 )   



# update password 

    current_user.password_hash=new_password_hash

    db.commit()


    return{
    "message":"Admin password updated successfully"
}