import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, Course, Staff, StaffCourse, User
from routers.auth import get_current_super_admin
from routers.staff_portal import private_document_url
from schemas.staff import StaffCreate, StaffResponse, StaffUpdate
from utils.password import hash_password


router = APIRouter(
    prefix="/super-admin/staff",
    tags=["Super Admin Staff"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_branch(db: Session, branch_id: int) -> Branch:
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch


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
            detail="One or more selected courses were not found in this branch",
        )

    course_by_id = {course.id: course for course in courses}
    return [course_by_id[course_id] for course_id in course_ids]


def build_staff_response(db: Session, staff: Staff):
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
        "id": staff.id,
        "user_id": staff.user_id,
        "branch_id": staff.branch_id,
        "staff_code": staff.staff_code,
        "name": staff.name,
        "email": staff.email,
        "phone": staff.phone,
        "course_id": staff.course_id,
        "course_name": primary_course.title if primary_course else "",
        "course_ids": [course.id for course in courses],
        "course_names": [course.title for course in courses],
        "address": staff.address,
        "salary": staff.salary,
        "status": staff.status,
        "created_at": staff.created_at,
    }


def build_super_admin_staff_response(db: Session, staff: Staff, branch: Branch):
    return {
        **build_staff_response(db, staff),
        "branch_name": branch.name,
        "branch_location": branch.location,
        "branch_status": branch.status,
        "verification_status": staff.verification_status,
        "aadhaar_number": staff.aadhaar_number,
        "pan_number": staff.pan_number,
        "bank_account_number": staff.bank_account_number,
        "bank_ifsc": staff.bank_ifsc,
        "documents": {
            "aadhaar_front_url": private_document_url(staff.aadhaar_front_key),
            "aadhaar_back_url": private_document_url(staff.aadhaar_back_key),
            "pan_card_url": private_document_url(staff.pan_card_key),
            "bank_passbook_url": private_document_url(staff.bank_passbook_key),
            "other_document_url": private_document_url(staff.other_document_key),
            "other_document_name": staff.other_document_name,
        },
        "verification_submitted_at": staff.verification_submitted_at,
        "verification_approved_at": staff.verification_approved_at,
        "verification_rejection_reason": staff.verification_rejection_reason,
        "verification_rejected_at": staff.verification_rejected_at,
    }


def get_active_staff(db: Session, branch_id: int, staff_id: int) -> Staff:
    staff = (
        db.query(Staff)
        .filter(
            Staff.id == staff_id,
            Staff.branch_id == branch_id,
            Staff.status == "Active",
        )
        .first()
    )
    if not staff:
        raise HTTPException(status_code=404, detail="Active staff not found")
    return staff


@router.get("/branches")
def get_branches(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branches = (
        db.query(Branch)
        .filter(Branch.status == "Active")
        .order_by(Branch.name.asc())
        .all()
    )
    return [
        {
            "id": branch.id,
            "name": branch.name,
            "location": branch.location,
            "status": branch.status,
        }
        for branch in branches
    ]


@router.get("")
def get_all_staff(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    total_staff = db.query(func.count(Staff.id)).scalar() or 0
    active_staff = (
        db.query(func.count(Staff.id))
        .filter(Staff.status == "Active")
        .scalar()
        or 0
    )
    rows = (
        db.query(Staff, Branch)
        .join(Branch, Branch.id == Staff.branch_id)
        .order_by(Staff.created_at.desc(), Staff.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    staff_details = []
    for staff, branch in rows:
        staff_details.append(build_super_admin_staff_response(db, staff, branch))

    return {
        "total_staff": int(total_staff),
        "active_staff": int(active_staff),
        "inactive_staff": int(total_staff - active_staff),
        "offset": offset,
        "limit": limit,
        "staff": staff_details,
    }


@router.get("/branches/{branch_id}/courses")
def get_branch_courses(
    branch_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branch = get_branch(db, branch_id)
    if branch.status != "Active":
        raise HTTPException(status_code=400, detail="Branch is inactive")

    courses = (
        db.query(Course)
        .filter(
            Course.branch_id == branch_id,
            Course.is_active == True,
        )
        .order_by(Course.title.asc())
        .all()
    )
    return [{"id": course.id, "title": course.title} for course in courses]


@router.get("/branches/{branch_id}/staff")
def get_branch_staff(
    branch_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_branch(db, branch_id)
    staff_members = (
        db.query(Staff)
        .filter(
            Staff.branch_id == branch_id,
        )
        .order_by(Staff.created_at.desc())
        .all()
    )
    branch = get_branch(db, branch_id)
    active_staff = sum(staff.status == "Active" for staff in staff_members)
    return {
        "branch_id": branch.id,
        "branch_name": branch.name,
        "total_staff": len(staff_members),
        "active_staff": active_staff,
        "inactive_staff": len(staff_members) - active_staff,
        "staff": [
            build_super_admin_staff_response(db, staff, branch)
            for staff in staff_members
        ],
    }


@router.post(
    "/branches/{branch_id}/staff",
    response_model=StaffResponse,
)
def create_branch_staff(
    branch_id: int,
    staff_data: StaffCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branch = get_branch(db, branch_id)
    if branch.status != "Active":
        raise HTTPException(status_code=400, detail="Branch is inactive")

    existing_user = db.query(User).filter(User.email == staff_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    courses = get_selected_courses(db, staff_data, branch_id)
    new_user = User(
        name=staff_data.name,
        email=staff_data.email,
        password_hash=hash_password(staff_data.password),
        phone=staff_data.phone,
        role="staff",
        branch_id=branch_id,
        address=staff_data.address,
        status="Active",
    )
    db.add(new_user)
    db.flush()

    new_staff = Staff(
        user_id=new_user.id,
        branch_id=branch_id,
        course_id=courses[0].id,
        staff_code=f"STF-{branch_id}-{uuid.uuid4().hex[:10].upper()}",
        name=staff_data.name,
        email=staff_data.email,
        phone=staff_data.phone,
        address=staff_data.address,
        salary=staff_data.salary,
        status="Active",
    )
    db.add(new_staff)
    db.flush()
    db.add_all(
        [StaffCourse(staff_id=new_staff.id, course_id=course.id) for course in courses]
    )

    db.commit()
    db.refresh(new_staff)
    return build_staff_response(db, new_staff)


@router.get(
    "/branches/{branch_id}/staff/{staff_id}",
    response_model=StaffResponse,
)
def get_branch_staff_member(
    branch_id: int,
    staff_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_branch(db, branch_id)
    staff = get_active_staff(db, branch_id, staff_id)
    return build_staff_response(db, staff)


@router.put(
    "/branches/{branch_id}/staff/{staff_id}",
    response_model=StaffResponse,
)
def update_branch_staff(
    branch_id: int,
    staff_id: int,
    staff_data: StaffUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_branch(db, branch_id)
    staff = get_active_staff(db, branch_id, staff_id)
    staff_user = (
        db.query(User)
        .filter(
            User.id == staff.user_id,
            User.branch_id == branch_id,
            User.role == "staff",
        )
        .first()
    )
    if not staff_user:
        raise HTTPException(status_code=404, detail="Staff user account not found")

    existing_user = (
        db.query(User)
        .filter(User.email == staff_data.email, User.id != staff_user.id)
        .first()
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    courses = None
    if staff_data.course_ids is not None or staff_data.course_id is not None:
        courses = get_selected_courses(db, staff_data, branch_id)

    staff_user.name = staff_data.name
    staff_user.email = staff_data.email
    staff_user.phone = staff_data.phone
    staff_user.address = staff_data.address
    if staff_data.password:
        staff_user.password_hash = hash_password(staff_data.password)

    staff.name = staff_data.name
    staff.email = staff_data.email
    staff.phone = staff_data.phone
    staff.address = staff_data.address
    staff.salary = staff_data.salary
    if courses is not None:
        staff.course_id = courses[0].id
        db.query(StaffCourse).filter(
            StaffCourse.staff_id == staff.id
        ).delete(synchronize_session=False)
        db.add_all(
            [StaffCourse(staff_id=staff.id, course_id=course.id) for course in courses]
        )

    db.commit()
    db.refresh(staff)
    return build_staff_response(db, staff)


@router.delete("/branches/{branch_id}/staff/{staff_id}")
def delete_branch_staff(
    branch_id: int,
    staff_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_branch(db, branch_id)
    staff = get_active_staff(db, branch_id, staff_id)
    staff.status = "Deleted"

    staff_user = (
        db.query(User)
        .filter(
            User.id == staff.user_id,
            User.branch_id == branch_id,
            User.role == "staff",
        )
        .first()
    )
    if staff_user:
        staff_user.status = "Deleted"

    db.commit()
    return {"success": True, "message": "Staff deleted successfully"}
