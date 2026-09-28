import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Staff, StaffCourse, User, Course

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


def get_selected_courses(db: Session, staff_data, branch_id: int):
    if staff_data.course_ids is not None:
        course_ids = staff_data.course_ids
    elif staff_data.course_id is not None:
        course_ids = [staff_data.course_id]
    else:
        raise HTTPException(
            status_code=400,
            detail="Select at least one course for the staff member",
        )

    course_ids = list(dict.fromkeys(course_ids))
    if not course_ids:
        raise HTTPException(
            status_code=400,
            detail="Select at least one course for the staff member",
        )
    courses = (
        db.query(Course)
        .filter(
            Course.id.in_(course_ids),
            Course.branch_id == branch_id,
            Course.is_active == True,
        )
        .all()
    )
    if len(courses) != len(course_ids):
        raise HTTPException(
            status_code=404,
            detail="One or more selected courses were not found in your branch",
        )
    course_by_id = {course.id: course for course in courses}
    return [course_by_id[course_id] for course_id in course_ids]


def staff_course_details(db: Session, staff: Staff):
    courses = (
        db.query(Course)
        .join(StaffCourse, StaffCourse.course_id == Course.id)
        .filter(StaffCourse.staff_id == staff.id)
        .order_by(Course.title.asc())
        .all()
    )
    if not courses:
        primary_course = db.query(Course).filter(Course.id == staff.course_id).first()
        if primary_course:
            courses = [primary_course]
    primary_course = db.query(Course).filter(Course.id == staff.course_id).first()
    return {
        "course_id": staff.course_id,
        "course_name": primary_course.title if primary_course else "",
        "course_ids": [course.id for course in courses],
        "course_names": [course.title for course in courses],
    }


def build_staff_response(db: Session, staff: Staff):
    return {
        "id": staff.id,
        "user_id": staff.user_id,
        "branch_id": staff.branch_id,
        "staff_code": staff.staff_code,
        "name": staff.name,
        "email": staff.email,
        "phone": staff.phone,
        **staff_course_details(db, staff),
        "address": staff.address,
        "salary": staff.salary,
        "status": staff.status,
        "created_at": staff.created_at,
    }


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
        .filter(
            User.email == staff_data.email
        )
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # --------------------------------------
    # CHECK COURSES
    # --------------------------------------

    courses = get_selected_courses(
        db,
        staff_data,
        current_user.branch_id,
    )

    # --------------------------------------
    # CREATE USER ACCOUNT
    # --------------------------------------

    new_user = User(
        name=staff_data.name,
        email=staff_data.email,
        password_hash=hash_password(
            staff_data.password
        ),
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
        course_id=courses[0].id,
        staff_code=(
            f"STF-{current_user.branch_id}-"
            f"{uuid.uuid4().hex[:10].upper()}"
        ),

        name=staff_data.name,
        email=staff_data.email,
        phone=staff_data.phone,
        address=staff_data.address,

        # SALARY
        salary=staff_data.salary,

        status="Active"
    )

    db.add(new_staff)
    db.flush()
    db.add_all(
        [
            StaffCourse(staff_id=new_staff.id, course_id=course.id)
            for course in courses
        ]
    )

    db.commit()

    db.refresh(new_staff)

    return build_staff_response(db, new_staff)


# ==========================================
# GET COURSES FOR STAFF DROPDOWN
# IMPORTANT: Keep this BEFORE /{staff_id}
# ==========================================

@router.get(
    "/courses/list"
)
def get_staff_courses(
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
    # GET ACTIVE COURSES
    # --------------------------------------

    courses = (
        db.query(Course)
        .filter(
            Course.branch_id == current_user.branch_id,
            Course.is_active == True
        )
        .order_by(
            Course.title.asc()
        )
        .all()
    )

    return [
        {
            "id": course.id,
            "title": course.title
        }
        for course in courses
    ]


# ==========================================
# GET ALL ACTIVE STAFF
# Deleted staff are NOT shown
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
    # GET ACTIVE STAFF ONLY
    # --------------------------------------

    results = (
        db.query(Staff)
        .filter(
            Staff.branch_id == current_user.branch_id,
            Staff.status == "Active"
        )
        .order_by(
            Staff.created_at.desc()
        )
        .all()
    )

    return [
        build_staff_response(db, staff)
        for staff in results
    ]


# ==========================================
# GET SINGLE ACTIVE STAFF
# Deleted staff are NOT shown
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
    # GET ACTIVE STAFF ONLY
    # --------------------------------------

    staff = (
        db.query(Staff)
        .filter(
            Staff.id == staff_id,
            Staff.branch_id == current_user.branch_id,
            Staff.status == "Active"
        )
        .first()
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Staff not found"
        )

    return build_staff_response(db, staff)


# ==========================================
# UPDATE STAFF
# Only ACTIVE staff can be updated
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
    # GET ACTIVE STAFF
    # --------------------------------------

    staff = (
        db.query(Staff)
        .filter(
            Staff.id == staff_id,
            Staff.branch_id == current_user.branch_id,
            Staff.status == "Active"
        )
        .first()
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Active staff not found"
        )

    # --------------------------------------
    # GET USER ACCOUNT
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
    # CHECK COURSES
    # --------------------------------------

    courses = None
    if staff_data.course_ids is not None or staff_data.course_id is not None:
        courses = get_selected_courses(
            db,
            staff_data,
            current_user.branch_id,
        )

    # --------------------------------------
    # UPDATE USER ACCOUNT
    # --------------------------------------

    staff_user.name = staff_data.name
    staff_user.email = staff_data.email
    staff_user.phone = staff_data.phone
    staff_user.address = staff_data.address

    if staff_data.password:
        staff_user.password_hash = hash_password(
            staff_data.password
        )

    # --------------------------------------
    # UPDATE STAFF TABLE
    # --------------------------------------

    staff.name = staff_data.name
    staff.email = staff_data.email
    staff.phone = staff_data.phone
    if courses is not None:
        staff.course_id = courses[0].id
        db.query(StaffCourse).filter(
            StaffCourse.staff_id == staff.id
        ).delete(synchronize_session=False)
        db.add_all(
            [
                StaffCourse(staff_id=staff.id, course_id=course.id)
                for course in courses
            ]
        )
    staff.address = staff_data.address

    # UPDATE SALARY
    staff.salary = staff_data.salary

    db.commit()

    db.refresh(staff)

    return build_staff_response(db, staff)


# ==========================================
# SOFT DELETE STAFF
# Active → Deleted
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
    # GET ACTIVE STAFF
    # --------------------------------------

    staff = (
        db.query(Staff)
        .filter(
            Staff.id == staff_id,
            Staff.branch_id == current_user.branch_id,
            Staff.status == "Active"
        )
        .first()
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Active staff not found"
        )

    # --------------------------------------
    # SOFT DELETE STAFF
    # --------------------------------------

    staff.status = "Deleted"

    # --------------------------------------
    # DISABLE USER LOGIN
    # --------------------------------------

    staff_user = (
        db.query(User)
        .filter(
            User.id == staff.user_id,
            User.role == "staff",
            User.branch_id == current_user.branch_id
        )
        .first()
    )

    if staff_user:
        staff_user.status = "Deleted"

    db.commit()

    return {
        "success": True,
        "message": "Staff deleted successfully"
    }