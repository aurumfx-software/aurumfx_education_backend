from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    Branch,
    Course,
    Enrollment,
    EnrollmentInstallment,
    RazorpayPaymentOrder,
    User,
)
from routers.auth import get_current_super_admin
from routers.enrollments import (
    enrollment_payment_history,
    enrollment_payment_summary,
)
from schemas.enrollment import AdminEnrollmentResponse, BranchAdminEnrollmentUpdate
from schemas.super_admin_enrollment import (
    SuperAdminBranchResponse,
    SuperAdminCourseResponse,
    SuperAdminCourseStudentsResponse,
)


router = APIRouter(
    prefix="/super-admin/enrollments",
    tags=["Super Admin Enrollments"],
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


def build_enrollment_response(
    db: Session,
    enrollment: Enrollment,
    user: User,
    course: Course,
):
    return {
        "enrollment_id": enrollment.id,
        "user_id": enrollment.user_id,
        "course_id": enrollment.course_id,
        "branch_id": enrollment.branch_id,
        "name": enrollment.name,
        "email": enrollment.email,
        "phone": enrollment.phone,
        "parent_name": enrollment.parent_name,
        "parent_phone": enrollment.parent_phone,
        "highest_qualification": enrollment.highest_qualification,
        "address": enrollment.address,
        "course_title": enrollment.course_title,
        "course_image": course.image,
        "course_duration": course.duration,
        "total_fee": enrollment.total_fee,
        **enrollment_payment_summary(db, enrollment),
        "payments": enrollment_payment_history(db, enrollment),
        "status": enrollment.status,
        "course_status": enrollment.course_status,
        "branch_approval_status": enrollment.branch_approval_status,
        "super_admin_approval_status": enrollment.super_admin_approval_status,
        "razorpay_order_id": enrollment.razorpay_order_id,
        "razorpay_payment_id": enrollment.razorpay_payment_id,
        "created_at": enrollment.created_at,
    }


@router.get("/branches", response_model=list[SuperAdminBranchResponse])
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
            "branch_id": branch.id,
            "branch_name": branch.name,
            "location": branch.location,
        }
        for branch in branches
    ]


@router.get(
    "/branches/{branch_id}/courses",
    response_model=list[SuperAdminCourseResponse],
)
def get_branch_courses(
    branch_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_branch(db, branch_id)
    courses = (
        db.query(Course, Enrollment.id)
        .outerjoin(
            Enrollment,
            (Enrollment.course_id == Course.id)
            & (Enrollment.branch_id == branch_id),
        )
        .filter(Course.branch_id == branch_id)
        .order_by(Course.title.asc())
        .all()
    )

    totals = {}
    course_by_id = {}
    for course, enrollment_id in courses:
        course_by_id[course.id] = course
        totals[course.id] = totals.get(course.id, 0) + (enrollment_id is not None)

    return [
        {
            "course_id": course.id,
            "course_title": course.title,
            "is_active": course.is_active,
            "total_students": totals[course.id],
        }
        for course in course_by_id.values()
    ]


@router.get(
    "/branches/{branch_id}/courses/{course_id}/students",
    response_model=SuperAdminCourseStudentsResponse,
)
def get_course_students(
    branch_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branch = get_branch(db, branch_id)
    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == branch_id,
        )
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found in this branch")

    rows = (
        db.query(Enrollment, User, Course)
        .join(User, Enrollment.user_id == User.id)
        .join(Course, Enrollment.course_id == Course.id)
        .filter(
            Enrollment.branch_id == branch_id,
            Enrollment.course_id == course_id,
        )
        .order_by(Enrollment.created_at.desc())
        .all()
    )
    students = [
        build_enrollment_response(db, enrollment, user, enrolled_course)
        for enrollment, user, enrolled_course in rows
    ]
    return {
        "branch_id": branch.id,
        "branch_name": branch.name,
        "course_id": course.id,
        "course_title": course.title,
        "total_students": len(students),
        "students": students,
    }


@router.put(
    "/branches/{branch_id}/students/{enrollment_id}",
    response_model=AdminEnrollmentResponse,
)
def update_branch_student(
    branch_id: int,
    enrollment_id: int,
    data: BranchAdminEnrollmentUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_branch(db, branch_id)
    enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.id == enrollment_id,
            Enrollment.branch_id == branch_id,
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Student enrollment not found")

    student = db.query(User).filter(User.id == enrollment.user_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student account not found")

    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No update fields provided")

    for field in ("name", "email"):
        if field in updates and not updates[field]:
            raise HTTPException(
                status_code=400,
                detail=f"{field.capitalize()} cannot be empty",
            )

    if "email" in updates and updates["email"] != student.email:
        duplicate_email = (
            db.query(User)
            .filter(User.email == updates["email"], User.id != student.id)
            .first()
        )
        if duplicate_email:
            raise HTTPException(status_code=400, detail="Email already registered")

    if "installments" in updates:
        open_order = (
            db.query(RazorpayPaymentOrder)
            .filter(
                RazorpayPaymentOrder.enrollment_id == enrollment.id,
                RazorpayPaymentOrder.status == "created",
            )
            .first()
        )
        if open_order:
            raise HTTPException(
                status_code=409,
                detail="Cannot change installments while a payment order is in progress",
            )

        submitted_terms = updates["installments"]
        if not submitted_terms:
            raise HTTPException(status_code=400, detail="At least one installment is required")
        submitted_numbers = [term["installment_number"] for term in submitted_terms]
        if submitted_numbers != list(range(1, len(submitted_terms) + 1)):
            raise HTTPException(
                status_code=400,
                detail="Installment numbers must be sequential starting at 1",
            )

        current_terms = (
            db.query(EnrollmentInstallment)
            .filter(EnrollmentInstallment.enrollment_id == enrollment.id)
            .order_by(EnrollmentInstallment.installment_number.asc())
            .all()
        )
        current_by_number = {term.installment_number: term for term in current_terms}
        submitted_by_number = {
            term["installment_number"]: term for term in submitted_terms
        }
        for number, term in current_by_number.items():
            submitted = submitted_by_number.get(number)
            if term.paid_amount > 0 and submitted is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Paid installment {number} cannot be removed",
                )
            if submitted is not None and round(submitted["amount"], 2) < round(term.paid_amount, 2):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Installment {number} cannot be less than the "
                        f"already paid amount ₹{term.paid_amount:.2f}"
                    ),
                )

        terms_total = round(sum(term["amount"] for term in submitted_terms), 2)
        if terms_total < round(enrollment.total_paid or 0, 2):
            raise HTTPException(
                status_code=400,
                detail="Installment total cannot be less than the amount already paid",
            )

        for term_data in submitted_terms:
            number = term_data["installment_number"]
            amount = round(term_data["amount"], 2)
            existing = current_by_number.get(number)
            if existing:
                existing.amount = amount
                existing.due_date = term_data["due_date"]
                existing.status = (
                    "paid" if existing.paid_amount >= amount
                    else "partial" if existing.paid_amount > 0
                    else "pending"
                )
            else:
                db.add(
                    EnrollmentInstallment(
                        enrollment_id=enrollment.id,
                        installment_number=number,
                        amount=amount,
                        paid_amount=0,
                        due_date=term_data["due_date"],
                        status="pending",
                        paid_date=None,
                        cash_amount=0,
                        upi_amount=0,
                    )
                )
        for number, term in current_by_number.items():
            if number not in submitted_by_number:
                if term.paid_amount > 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Paid installment {number} cannot be deleted",
                    )
                db.delete(term)

        enrollment.installment_count = len(submitted_terms)
        enrollment.total_fee = terms_total
        enrollment.balance_amount = max(
            round(terms_total - (enrollment.total_paid or 0), 2),
            0,
        )
        enrollment.status = "paid" if enrollment.balance_amount == 0 else "pending"
        enrollment.installment_amount = round(terms_total / len(submitted_terms), 2)

    profile_fields = {
        "name",
        "email",
        "phone",
        "parent_name",
        "parent_phone",
        "highest_qualification",
        "address",
    }
    for field in profile_fields.intersection(updates):
        value = updates[field]
        setattr(student, field, value)
        setattr(enrollment, field, value)

    db.commit()
    db.refresh(enrollment)
    course = db.query(Course).filter(Course.id == enrollment.course_id).first()
    return build_enrollment_response(db, enrollment, student, course)
