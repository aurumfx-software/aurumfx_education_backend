from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Staff, User, Course

from schemas.staff import (
    StaffCreate,
    StaffUpdate,
    StaffResponse
)

from routers.auth import get_current_user
from utils.password import hash_password


router = APIRouter(
    prefix="/branch-admin/staff",
    tags=["Branch Admin Staff"]
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
# CREATE STAFF
# ==========================================

@router.post(
    "",
    response_model=StaffResponse
)
def create_staff(
    staff_data: StaffCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # --------------------------------------
    # CHECK BRANCH ADMIN
    # --------------------------------------

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    # --------------------------------------
    # CHECK EMAIL
    # --------------------------------------

    existing_user = (
        db.query(User)
        .filter(User.email == staff_data.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # --------------------------------------
    # CHECK COURSE
    # --------------------------------------

    course = (
        db.query(Course)
        .filter(
            Course.id == staff_data.course_id,
            Course.branch_id == current_user.branch_id,
            Course.is_active == True
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found in your branch"
        )

    # --------------------------------------
    # CREATE USER ACCOUNT
    # --------------------------------------

    new_user = User(
        name=staff_data.name,
        email=staff_data.email,
        password_hash=hash_password(staff_data.password),
        phone=staff_data.phone,
        role="staff",
        branch_id=current_user.branch_id,
        address=staff_data.address,
        status="Active"
    )

    db.add(new_user)
    db.flush()

    # --------------------------------------
    # CREATE STAFF RECORD
    # --------------------------------------

    new_staff = Staff(
        user_id=new_user.id,
        branch_id=current_user.branch_id,
        course_id=staff_data.course_id,
        address=staff_data.address
    )

    db.add(new_staff)

    db.commit()

    db.refresh(new_staff)
    db.refresh(new_user)

    return {
        "id": new_staff.id,
        "user_id": new_user.id,
        "branch_id": new_staff.branch_id,
        "name": new_user.name,
        "email": new_user.email,
        "phone": new_user.phone,
        "course_id": course.id,
        "course_name": course.title,
        "address": new_staff.address,
        "created_at": new_staff.created_at
    }


# ==========================================
# GET ALL STAFF
# ==========================================

@router.get(
    "",
    response_model=list[StaffResponse]
)
def get_all_staff(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # --------------------------------------
    # CHECK BRANCH ADMIN
    # --------------------------------------

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    # --------------------------------------
    # GET STAFF
    # --------------------------------------

    results = (
        db.query(Staff, User, Course)
        .join(
            User,
            Staff.user_id == User.id
        )
        .join(
            Course,
            Staff.course_id == Course.id
        )
        .filter(
            Staff.branch_id == current_user.branch_id
        )
        .order_by(
            Staff.created_at.desc()
        )
        .all()
    )

    return [
        {
            "id": staff.id,
            "user_id": staff_user.id,
            "branch_id": staff.branch_id,

            "name": staff_user.name,
            "email": staff_user.email,
            "phone": staff_user.phone,

            "course_id": course.id,
            "course_name": course.title,

            "address": staff.address,
            "created_at": staff.created_at
        }
        for staff, staff_user, course in results
    ]


# ==========================================
# GET SINGLE STAFF
# ==========================================

@router.get(
    "/{staff_id}",
    response_model=StaffResponse
)
def get_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # --------------------------------------
    # CHECK BRANCH ADMIN
    # --------------------------------------

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    # --------------------------------------
    # GET STAFF
    # --------------------------------------

    result = (
        db.query(Staff, User, Course)
        .join(
            User,
            Staff.user_id == User.id
        )
        .join(
            Course,
            Staff.course_id == Course.id
        )
        .filter(
            Staff.id == staff_id,
            Staff.branch_id == current_user.branch_id
        )
        .first()
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Staff not found"
        )

    staff, staff_user, course = result

    return {
        "id": staff.id,
        "user_id": staff_user.id,
        "branch_id": staff.branch_id,

        "name": staff_user.name,
        "email": staff_user.email,
        "phone": staff_user.phone,

        "course_id": course.id,
        "course_name": course.title,

        "address": staff.address,
        "created_at": staff.created_at
    }


# ==========================================
# UPDATE STAFF
# ==========================================

@router.put(
    "/{staff_id}",
    response_model=StaffResponse
)
def update_staff(
    staff_id: int,
    staff_data: StaffUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # --------------------------------------
    # CHECK BRANCH ADMIN
    # --------------------------------------

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    # --------------------------------------
    # GET STAFF
    # --------------------------------------

    staff = (
        db.query(Staff)
        .filter(
            Staff.id == staff_id,
            Staff.branch_id == current_user.branch_id
        )
        .first()
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Staff not found"
        )

    # --------------------------------------
    # GET USER
    # --------------------------------------

    staff_user = (
        db.query(User)
        .filter(
            User.id == staff.user_id,
            User.branch_id == current_user.branch_id,
            User.role == "staff"
        )
        .first()
    )

    if not staff_user:
        raise HTTPException(
            status_code=404,
            detail="Staff user account not found"
        )

    # --------------------------------------
    # CHECK EMAIL
    # --------------------------------------

    existing_user = (
        db.query(User)
        .filter(
            User.email == staff_data.email,
            User.id != staff_user.id
        )
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # --------------------------------------
    # CHECK COURSE
    # --------------------------------------

    course = (
        db.query(Course)
        .filter(
            Course.id == staff_data.course_id,
            Course.branch_id == current_user.branch_id,
            Course.is_active == True
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found in your branch"
        )

    # --------------------------------------
    # UPDATE USER
    # --------------------------------------

    staff_user.name = staff_data.name
    staff_user.email = staff_data.email
    staff_user.phone = staff_data.phone
    staff_user.address = staff_data.address

    # Change password only if provided
    if staff_data.password:
        staff_user.password_hash = hash_password(
            staff_data.password
        )

    # --------------------------------------
    # UPDATE STAFF
    # --------------------------------------

    staff.course_id = staff_data.course_id
    staff.address = staff_data.address

    db.commit()

    db.refresh(staff)
    db.refresh(staff_user)

    return {
        "id": staff.id,
        "user_id": staff_user.id,
        "branch_id": staff.branch_id,

        "name": staff_user.name,
        "email": staff_user.email,
        "phone": staff_user.phone,

        "course_id": course.id,
        "course_name": course.title,

        "address": staff.address,
        "created_at": staff.created_at
    }


# ==========================================
# DELETE STAFF
# ==========================================

@router.delete(
    "/{staff_id}"
)
def delete_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # --------------------------------------
    # CHECK BRANCH ADMIN
    # --------------------------------------

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    # --------------------------------------
    # GET STAFF
    # --------------------------------------

    staff = (
        db.query(Staff)
        .filter(
            Staff.id == staff_id,
            Staff.branch_id == current_user.branch_id
        )
        .first()
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Staff not found"
        )

    user_id = staff.user_id

    # --------------------------------------
    # DELETE STAFF
    # --------------------------------------

    db.delete(staff)

    # Delete login account too
    staff_user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.role == "staff"
        )
        .first()
    )

    if staff_user:
        db.delete(staff_user)

    db.commit()

    return {
        "success": True,
        "message": "Staff deleted successfully"
    }


# # ==========================================
# # GET COURSES FOR STAFF DROPDOWN
# # ==========================================

# @router.get(
#     "/courses/list"
# )
# def get_staff_courses(
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):

#     # --------------------------------------
#     # CHECK BRANCH ADMIN
#     # --------------------------------------

#     if current_user.role != "branch_admin":
#         raise HTTPException(
#             status_code=403,
#             detail="Branch admin access required"
#         )

#     if not current_user.branch_id:
#         raise HTTPException(
#             status_code=400,
#             detail="Branch admin is not assigned to a branch"
#         )

#     # --------------------------------------
#     # GET ACTIVE COURSES
#     # --------------------------------------

#     courses = (
#         db.query(Course)
#         .filter(
#             Course.branch_id == current_user.branch_id,
#             Course.is_active == True
#         )
#         .order_by(Course.title.asc())
#         .all()
#     )

#     return [
#         {
#             "id": course.id,
#             "title": course.title
#         }
#         for course in courses
#     ]