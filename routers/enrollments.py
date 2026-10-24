from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from database import SessionLocal
from database_models import (
    Enrollment,
    EnrollmentInstallment,
    AdmissionPayment,
    RazorpayPaymentOrder,
    Branch,
    Course,
    User,
)

from schemas.enrollment import (
    EnrollmentResponse,
    AdminEnrollmentResponse,
    BranchAdminInstallmentPaymentCreate,
    BranchAdminEnrollmentUpdate,
    InstallmentPaymentReject,
    SuperAdminPurchaseReject,
)

from routers.auth import get_current_user, get_current_super_admin


router = APIRouter(
    prefix="/enrollments"
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


def enrollment_payment_summary(db: Session, enrollment: Enrollment):
    installments = (
        db.query(EnrollmentInstallment)
        .filter(EnrollmentInstallment.enrollment_id == enrollment.id)
        .order_by(EnrollmentInstallment.installment_number.asc())
        .all()
    )
    installment_count = len(installments)
    paid_installment_count = sum(
        installment.status == "paid" for installment in installments
    )
    due_installments = [
        installment
        for installment in installments
        if installment.due_date <= date.today()
        and installment.amount - installment.paid_amount > 0
    ]
    pending_payment_amounts = dict(
        db.query(
            AdmissionPayment.installment_id,
            func.sum(AdmissionPayment.amount),
        )
        .filter(
            AdmissionPayment.enrollment_id == enrollment.id,
            AdmissionPayment.status == "pending_review",
            AdmissionPayment.installment_id.isnot(None),
        )
        .group_by(AdmissionPayment.installment_id)
        .all()
    )
    next_installment = next(
        (
            installment
            for installment in sorted(
                installments,
                key=lambda item: (item.due_date, item.installment_number),
            )
            if installment.amount - installment.paid_amount > 0
        ),
        None,
    )

    return {
        "total_paid": enrollment.total_paid or 0,
        "balance_amount": max(
            round(enrollment.total_fee - (enrollment.total_paid or 0), 2),
            0,
        ),
        "installment_count": installment_count,
        "paid_installment_count": paid_installment_count,
        "remaining_installment_count": (
            installment_count - paid_installment_count
        ),
        "payment_plan": "installment" if installment_count else "full_payment",
        "due_installment_count": len(due_installments),
        "next_installment": (
            {
                "installment_id": next_installment.id,
                "installment_number": next_installment.installment_number,
                "due_date": next_installment.due_date,
                "amount": next_installment.amount,
                "remaining_amount": round(
                    next_installment.amount - next_installment.paid_amount, 2
                ),
                "status": next_installment.status,
            }
            if next_installment
            else None
        ),
        "branch_approval_status": enrollment.branch_approval_status,
        "super_admin_approval_status": enrollment.super_admin_approval_status,
        "super_admin_rejection_reason": enrollment.super_admin_rejection_reason,
        "super_admin_rejected_at": enrollment.super_admin_rejected_at,
        "installments": [
            {
                "installment_id": installment.id,
                "installment_number": installment.installment_number,
                "amount": installment.amount,
                "paid_amount": installment.paid_amount,
                "remaining_amount": round(
                    installment.amount - installment.paid_amount, 2
                ),
                "pending_review_amount": round(
                    pending_payment_amounts.get(installment.id, 0) or 0, 2
                ),
                "payment_review_status": (
                    "pending"
                    if pending_payment_amounts.get(installment.id, 0) > 0
                    else None
                ),
                "is_due": (
                    installment.due_date <= date.today()
                    and installment.amount - installment.paid_amount > 0
                ),
                "due_date": installment.due_date,
                "status": installment.status,
                "paid_date": installment.paid_date,
            }
            for installment in installments
        ],
    }


def enrollment_payment_history(db: Session, enrollment: Enrollment):
    return (
        db.query(AdmissionPayment)
        .filter(AdmissionPayment.enrollment_id == enrollment.id)
        .order_by(
            AdmissionPayment.payment_date.asc(),
            AdmissionPayment.id.asc(),
        )
        .all()
    )


def installment_payment_status_fields(payment: AdmissionPayment):
    if payment.payment_method == "razorpay":
        payment_status = (
            "paid"
            if payment.status in {"pending_review", "received", "rejected"}
            else payment.status
        )
        approval_status = {
            "pending_review": "pending",
            "received": (
                "approved" if payment.reviewed_by_user_id else "not_required"
            ),
            "rejected": "rejected",
        }.get(payment.status, "not_required")
    else:
        payment_status = "paid" if payment.status == "received" else payment.status
        approval_status = "not_required"
    return {
        "payment_status": payment_status,
        "approval_status": approval_status,
    }


def build_installment_student_record(
    db: Session,
    enrollment: Enrollment,
    student: User,
    course: Course,
    branch_name: str,
):
    payment_summary = enrollment_payment_summary(db, enrollment)
    payments = enrollment_payment_history(db, enrollment)
    return {
        "enrollment_id": enrollment.id,
        "user_id": student.id,
        "branch_id": enrollment.branch_id,
        "branch_name": branch_name,
        "name": enrollment.name or student.name,
        "email": enrollment.email or student.email,
        "phone": enrollment.phone or student.phone,
        "parent_name": enrollment.parent_name or student.parent_name,
        "parent_phone": enrollment.parent_phone or student.parent_phone,
        "highest_qualification": (
            enrollment.highest_qualification or student.highest_qualification
        ),
        "address": enrollment.address or student.address,
        "course_id": course.id,
        "course_title": enrollment.course_title or course.title,
        "total_fee": enrollment.total_fee,
        **payment_summary,
        "payment_status": enrollment.status,
        "course_status": enrollment.course_status,
        "branch_approval_status": enrollment.branch_approval_status,
        "super_admin_approval_status": enrollment.super_admin_approval_status,
        "payments": [
            {
                "payment_id": payment.id,
                "installment_number": payment.installment_number,
                "amount": payment.amount,
                "cash_amount": payment.cash_amount,
                "upi_amount": payment.upi_amount,
                "payment_method": payment.payment_method,
                "payment_date": payment.payment_date,
                "status": payment.status,
                **installment_payment_status_fields(payment),
                "reviewed_at": payment.reviewed_at,
                "rejection_reason": payment.rejection_reason,
            }
            for payment in payments
        ],
        "created_at": enrollment.created_at,
    }


def get_installment_student_rows(
    db: Session,
    branch_id: int | None,
    fully_paid: bool,
):
    query = (
        db.query(Enrollment, User, Course, Branch.name)
        .join(User, User.id == Enrollment.user_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Branch, Branch.id == Enrollment.branch_id)
    )
    if branch_id is not None:
        query = query.filter(Enrollment.branch_id == branch_id)

    if fully_paid:
        query = query.filter(Enrollment.status == "paid")
    else:
        query = query.filter(
            Enrollment.total_paid > 0,
            Enrollment.balance_amount > 0,
        )
    return query.order_by(Enrollment.created_at.desc()).all()


def build_installment_payment_record(
    payment: AdmissionPayment,
    enrollment: Enrollment,
    student: User,
    course: Course,
    branch_name: str,
):
    return {
        "payment_id": payment.id,
        "enrollment_id": enrollment.id,
        "user_id": student.id,
        "branch_id": enrollment.branch_id,
        "branch_name": branch_name,
        "name": enrollment.name or student.name,
        "email": enrollment.email or student.email,
        "phone": enrollment.phone or student.phone,
        "course_id": course.id,
        "course_title": enrollment.course_title or course.title,
        "installment_id": payment.installment_id,
        "installment_number": payment.installment_number,
        "amount": payment.amount,
        "payment_method": payment.payment_method,
        "payment_reference": payment.payment_reference,
        "payment_date": payment.payment_date,
        "status": payment.status,
        **installment_payment_status_fields(payment),
        "reviewed_by_user_id": payment.reviewed_by_user_id,
        "reviewed_at": payment.reviewed_at,
        "rejection_reason": payment.rejection_reason,
        "created_at": payment.created_at,
    }


def update_enrollment_for_branch_admin(
    enrollment_id: int,
    data: BranchAdminEnrollmentUpdate,
    db: Session,
    current_user: User,
    course_id: int | None = None,
):
    if current_user.role != "branch_admin":
        raise HTTPException(status_code=403, detail="Branch admin access required")
    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch",
        )

    query = db.query(Enrollment).filter(
        Enrollment.id == enrollment_id,
        Enrollment.branch_id == current_user.branch_id,
    )
    if course_id is not None:
        query = query.filter(Enrollment.course_id == course_id)
    enrollment = query.first()
    if not enrollment:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found in your branch/course",
        )

    student = db.query(User).filter(User.id == enrollment.user_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student account not found")

    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No update fields provided")

    profile_fields = {
        "name",
        "email",
        "phone",
        "parent_name",
        "parent_phone",
        "highest_qualification",
        "address",
    }
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
            raise HTTPException(
                status_code=400,
                detail="At least one installment is required",
            )
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
        current_by_number = {
            term.installment_number: term for term in current_terms
        }
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

            if submitted is not None:
                new_amount = round(submitted["amount"], 2)
                if new_amount < round(term.paid_amount, 2):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Installment {number} amount cannot be less than the "
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
                if amount < existing.paid_amount:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Installment {number} cannot be less than its paid amount",
                    )
                existing.amount = amount
                existing.due_date = term_data["due_date"]
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
        enrollment.status = (
            "paid" if enrollment.balance_amount == 0 else "pending"
        )
        enrollment.installment_amount = round(
            terms_total / len(submitted_terms), 2
        )

    for field in profile_fields.intersection(updates):
        value = updates[field]
        setattr(student, field, value)
        setattr(enrollment, field, value)

    db.commit()
    db.refresh(enrollment)
    course = db.query(Course).filter(Course.id == enrollment.course_id).first()
    return {
        "enrollment_id": enrollment.id,
        "user_id": enrollment.user_id,
        "course_id": enrollment.course_id,
        "branch_id": enrollment.branch_id,
        "account_status": student.status,
        "name": enrollment.name,
        "email": enrollment.email,
        "phone": enrollment.phone,
        "parent_name": enrollment.parent_name,
        "parent_phone": enrollment.parent_phone,
        "highest_qualification": enrollment.highest_qualification,
        "address": enrollment.address,
        "course_title": enrollment.course_title,
        "course_image": course.image if course else None,
        "course_duration": course.duration if course else "",
        "total_fee": enrollment.total_fee,
        "status": enrollment.status,
        "course_status": enrollment.course_status,
        "razorpay_order_id": enrollment.razorpay_order_id,
        "razorpay_payment_id": enrollment.razorpay_payment_id,
        "created_at": enrollment.created_at,
        **enrollment_payment_summary(db, enrollment),
        "payments": enrollment_payment_history(db, enrollment),
    }


# ============================================================
# GET MY ENROLLMENTS
# STUDENT ONLY
# ============================================================

@router.get(
    "/{enrollment_id}/installments",
    tags=["Student Installments"],
)
def get_student_installment_details(
    enrollment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can access installment details",
        )

    enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.id == enrollment_id,
            Enrollment.user_id == current_user.id,
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    course = db.query(Course).filter(Course.id == enrollment.course_id).first()
    installments = (
        db.query(EnrollmentInstallment)
        .filter(EnrollmentInstallment.enrollment_id == enrollment.id)
        .order_by(EnrollmentInstallment.installment_number.asc())
        .all()
    )
    payment_rows = enrollment_payment_history(db, enrollment)
    pending_amount_by_installment = {}
    for payment in payment_rows:
        if payment.status == "pending_review" and payment.installment_id:
            pending_amount_by_installment[payment.installment_id] = round(
                pending_amount_by_installment.get(payment.installment_id, 0)
                + payment.amount,
                2,
            )

    installment_details = [
        {
            "installment_id": installment.id,
            "installment_number": installment.installment_number,
            "amount": installment.amount,
            "paid_amount": installment.paid_amount,
            "remaining_amount": round(
                installment.amount - installment.paid_amount, 2
            ),
            "pending_review_amount": pending_amount_by_installment.get(
                installment.id, 0
            ),
            "payment_review_status": (
                "pending"
                if pending_amount_by_installment.get(installment.id, 0) > 0
                else None
            ),
            "due_date": installment.due_date,
            "paid_date": installment.paid_date,
            "status": installment.status,
            "cash_amount": installment.cash_amount,
            "upi_amount": installment.upi_amount,
        }
        for installment in installments
    ]
    latest_received_payment = max(
        (
            payment
            for payment in payment_rows
            if payment.status == "received" and payment.installment_id
        ),
        key=lambda payment: (payment.payment_date, payment.id),
        default=None,
    )
    last_paid_installment = next(
        (
            installment
            for installment in installments
            if installment.id == latest_received_payment.installment_id
        ),
        None,
    ) if latest_received_payment else next(
        (
            installment
            for installment in reversed(installments)
            if installment.paid_amount > 0
        ),
        None,
    )
    next_installment = next(
        (
            installment
            for installment in installments
            if installment.amount - installment.paid_amount > 0
        ),
        None,
    )
    next_payment_pending = (
        pending_amount_by_installment.get(next_installment.id, 0) > 0
        if next_installment
        else False
    )

    return {
        "enrollment_id": enrollment.id,
        "user_id": enrollment.user_id,
        "course_id": enrollment.course_id,
        "course_title": enrollment.course_title or (course.title if course else ""),
        "course_status": enrollment.course_status,
        "branch_approval_status": enrollment.branch_approval_status,
        "super_admin_approval_status": enrollment.super_admin_approval_status,
        "payment_status": enrollment.status,
        "total_fee": enrollment.total_fee,
        "total_paid": enrollment.total_paid,
        "balance_amount": enrollment.balance_amount,
        "installment_count": len(installments),
        "last_paid_installment": (
            {
                "installment_id": last_paid_installment.id,
                "installment_number": last_paid_installment.installment_number,
                "amount": last_paid_installment.amount,
                "paid_amount": last_paid_installment.paid_amount,
                "paid_date": last_paid_installment.paid_date,
                "status": last_paid_installment.status,
            }
            if last_paid_installment
            else None
        ),
        "next_installment": (
            {
                "installment_id": next_installment.id,
                "installment_number": next_installment.installment_number,
                "amount": next_installment.amount,
                "paid_amount": next_installment.paid_amount,
                "remaining_amount": round(
                    next_installment.amount - next_installment.paid_amount, 2
                ),
                "pending_review_amount": pending_amount_by_installment.get(
                    next_installment.id, 0
                ),
                "due_date": next_installment.due_date,
                "status": next_installment.status,
                "payment_review_status": (
                    "pending_review" if next_payment_pending else None
                ),
                "can_create_payment_order": not next_payment_pending,
            }
            if next_installment
            else None
        ),
        "installments": installment_details,
        "payments": [
            {
                "payment_id": payment.id,
                "installment_id": payment.installment_id,
                "installment_number": payment.installment_number,
                "amount": payment.amount,
                "cash_amount": payment.cash_amount,
                "upi_amount": payment.upi_amount,
                "payment_method": payment.payment_method,
                "payment_date": payment.payment_date,
                "status": payment.status,
                **installment_payment_status_fields(payment),
                "payment_reference": payment.payment_reference,
                "reviewed_at": payment.reviewed_at,
                "rejection_reason": payment.rejection_reason,
            }
            for payment in payment_rows
        ],
    }


@router.get(
    "/my",
    response_model=list[EnrollmentResponse],
    tags=["Student Enrollments"]
)
def get_my_enrollments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can access their enrollments"
        )

    results = (
        db.query(
            Enrollment,
            Course,
            Branch,
            User,
        )
        .join(
            Course,
            Enrollment.course_id == Course.id
        )
        .join(
            Branch,
            Enrollment.branch_id == Branch.id
        )
        .join(
            User,
            Enrollment.user_id == User.id
        )
        .filter(
            Enrollment.user_id == current_user.id
        )
        .order_by(
            Enrollment.created_at.desc()
        )
        .all()
    )

    return [
        {
            "id": enrollment.id,
            "user_id": enrollment.user_id,
            "course_id": enrollment.course_id,
            "branch_id": enrollment.branch_id,

            "name": enrollment.name or student.name,
            "email": enrollment.email or student.email,
            "phone": enrollment.phone or student.phone,

            "parent_name": enrollment.parent_name or student.parent_name,
            "parent_phone": enrollment.parent_phone or student.parent_phone,

            "highest_qualification": (
                enrollment.highest_qualification or student.highest_qualification
            ),
            "address": enrollment.address or student.address,

            "course_title": enrollment.course_title or course.title,
            "course_image": course.image,
            "course_duration": course.duration,
            "branch_details": {
                "id": branch.id,
                "name": branch.name,
                "location": branch.location,
                "phone": branch.phone,
                "email": branch.email,
                "status": branch.status,
            },
            "course_details": {
                "id": course.id,
                "title": enrollment.course_title or course.title,
                "duration": course.duration,
                "start_date": course.start_date,
                "end_date": course.end_date,
                "image": course.image,
                "category": course.category,
                "level": course.level,
            },
            "student_details": {
                "id": student.id,
                "name": enrollment.name or student.name,
                "email": enrollment.email or student.email,
                "phone": enrollment.phone or student.phone,
                "parent_name": enrollment.parent_name or student.parent_name,
                "parent_phone": enrollment.parent_phone or student.parent_phone,
                "highest_qualification": (
                    enrollment.highest_qualification
                    or student.highest_qualification
                ),
                "address": enrollment.address or student.address,
            },

            "total_fee": enrollment.total_fee,
            **enrollment_payment_summary(db, enrollment),
            "payments": [
                {
                    "id": payment.id,
                    "enrollment_id": payment.enrollment_id,
                    "installment_id": payment.installment_id,
                    "installment_number": payment.installment_number,
                    "amount": payment.amount,
                    "cash_amount": payment.cash_amount,
                    "upi_amount": payment.upi_amount,
                    "payment_method": payment.payment_method,
                    "payment_date": payment.payment_date,
                    "status": payment.status,
                    **installment_payment_status_fields(payment),
                    "reviewed_by_user_id": payment.reviewed_by_user_id,
                    "reviewed_at": payment.reviewed_at,
                    "rejection_reason": payment.rejection_reason,
                    "payment_reference": payment.payment_reference,
                }
                for payment in enrollment_payment_history(db, enrollment)
            ],

            # Payment status
            "status": enrollment.status,

            # Branch approval status
            "course_status": enrollment.course_status,
            "super_admin_rejection_reason": enrollment.super_admin_rejection_reason,
            "super_admin_rejected_at": enrollment.super_admin_rejected_at,

            "razorpay_order_id": enrollment.razorpay_order_id,
            "razorpay_payment_id": enrollment.razorpay_payment_id,

            "created_at": enrollment.created_at
        }

        for enrollment, course, branch, student in results
    ]


# ============================================================
# GET MY PURCHASED COURSES
# STUDENT ONLY
# ============================================================

@router.get(
    "/my-purchases",
    tags=["Student Purchases"]
)
def get_my_purchases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can access their purchases"
        )

    results = (
        db.query(
            Enrollment,
            Course
        )
        .join(
            Course,
            Enrollment.course_id == Course.id
        )
        .filter(
            Enrollment.user_id == current_user.id,
            Enrollment.course_status == "approved",
            or_(
                Enrollment.status == "paid",
                Enrollment.total_paid > 0,
            ),
        )
        .order_by(
            Enrollment.created_at.desc()
        )
        .all()
    )

    return [
        {
            "enrollment_id": enrollment.id,

            "course_id": enrollment.course_id,
            "course_title": enrollment.course_title,
            "course_image": course.image,
            "course_duration": course.duration,

            "amount": enrollment.total_fee,

            # Payment status
            "payment_status": enrollment.status,

            # Branch approval status
            "course_status": enrollment.course_status,
            "super_admin_rejection_reason": enrollment.super_admin_rejection_reason,
            "super_admin_rejected_at": enrollment.super_admin_rejected_at,

            "razorpay_payment_id": enrollment.razorpay_payment_id,

            "created_at": enrollment.created_at
        }

        for enrollment, course in results
    ]


# ============================================================
# GET BRANCH ENROLLMENTS
# BRANCH ADMIN ONLY
# ============================================================

@router.get(
    "/branch-admin/my-enrollments",
    response_model=list[AdminEnrollmentResponse],
    tags=["Branch Admin Enrollments"]
)
def get_branch_admin_enrollments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

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

    results = (
        db.query(
            Enrollment,
            User,
            Course
        )
        .join(
            User,
            Enrollment.user_id == User.id
        )
        .join(
            Course,
            Enrollment.course_id == Course.id
        )
        .filter(
            Enrollment.branch_id == current_user.branch_id
        )
        .order_by(
            Enrollment.created_at.desc()
        )
        .all()
    )

    return [
        {
            "enrollment_id": enrollment.id,
            "user_id": enrollment.user_id,
            "course_id": enrollment.course_id,
            "branch_id": enrollment.branch_id,
            "account_status": student.status,

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

            # Payment status
            "status": enrollment.status,

            # Course approval status
            "course_status": enrollment.course_status,

            "razorpay_order_id": enrollment.razorpay_order_id,
            "razorpay_payment_id": enrollment.razorpay_payment_id,

            "created_at": enrollment.created_at
        }

        for enrollment, student, course in results
    ]


# ============================================================
# GET COURSE ENROLLMENTS
# BRANCH ADMIN ONLY
# ============================================================

@router.get(
    "/branch-admin/course/{course_id}",
    response_model=list[AdminEnrollmentResponse],
    tags=["Branch Admin Enrollments"]
)
def get_branch_admin_course_enrollments(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

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

    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == current_user.branch_id
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found in your branch"
        )

    results = (
        db.query(
            Enrollment,
            User,
            Course
        )
        .join(
            User,
            Enrollment.user_id == User.id
        )
        .join(
            Course,
            Enrollment.course_id == Course.id
        )
        .filter(
            Enrollment.branch_id == current_user.branch_id,
            Enrollment.course_id == course_id
        )
        .order_by(
            Enrollment.created_at.desc()
        )
        .all()
    )

    return [
        {
            "enrollment_id": enrollment.id,
            "user_id": enrollment.user_id,
            "course_id": enrollment.course_id,
            "branch_id": enrollment.branch_id,
            "account_status": student.status,

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

            # Payment status
            "status": enrollment.status,

            # Course approval status
            "course_status": enrollment.course_status,

            "razorpay_order_id": enrollment.razorpay_order_id,
            "razorpay_payment_id": enrollment.razorpay_payment_id,

            "created_at": enrollment.created_at
        }

        for enrollment, student, course in results
    ]


# ============================================================
# UPDATE ENROLLMENT FROM TOTAL OR COURSE-FILTERED LIST
# BRANCH ADMIN ONLY
# ============================================================

@router.put(
    "/branch-admin/my-enrollments/{enrollment_id}",
    response_model=AdminEnrollmentResponse,
    tags=["Branch Admin Enrollments"],
)
def update_branch_admin_enrollment(
    enrollment_id: int,
    data: BranchAdminEnrollmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return update_enrollment_for_branch_admin(
        enrollment_id=enrollment_id,
        data=data,
        db=db,
        current_user=current_user,
    )


@router.put(
    "/branch-admin/course/{course_id}/{enrollment_id}",
    response_model=AdminEnrollmentResponse,
    tags=["Branch Admin Enrollments"],
)
def update_branch_admin_course_enrollment(
    course_id: int,
    enrollment_id: int,
    data: BranchAdminEnrollmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return update_enrollment_for_branch_admin(
        enrollment_id=enrollment_id,
        data=data,
        db=db,
        current_user=current_user,
        course_id=course_id,
    )


# ============================================================
# GET BRANCH COURSE PURCHASE SUMMARY
# BRANCH ADMIN ONLY
# ============================================================

@router.get(
    "/branch-admin/course-summary",
    tags=["Branch Admin Enrollments"]
)
def get_branch_admin_course_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

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

    results = (
        db.query(
            Course.id.label("course_id"),
            Course.title.label("course_title"),
            Course.image.label("course_image"),

            func.count(
                Enrollment.id
            ).label("purchase_count")
        )
        .outerjoin(
            Enrollment,
            and_(
                Enrollment.course_id == Course.id,
                Enrollment.status == "paid"
            )
        )
        .filter(
            Course.branch_id == current_user.branch_id
        )
        .group_by(
            Course.id,
            Course.title,
            Course.image
        )
        .order_by(
            Course.id.asc()
        )
        .all()
    )

    return [
        {
            "course_id": row.course_id,
            "course_title": row.course_title,
            "course_image": row.course_image,
            "purchase_count": row.purchase_count
        }

        for row in results
    ]



# ============================================================
# GET BRANCH ADMIN PURCHASES
# BRANCH ADMIN ONLY
# ============================================================

@router.get(
    "/branch-admin/purchases",
    tags=["Branch Admin Purchases"]
)
def get_branch_admin_purchases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

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

    results = (
        db.query(
            Enrollment,
            User,
            Course
        )
        .join(
            User,
            Enrollment.user_id == User.id
        )
        .join(
            Course,
            Enrollment.course_id == Course.id
        )
        .filter(
            Enrollment.branch_id == current_user.branch_id,
            Enrollment.status == "paid"
        )
        .order_by(
            Enrollment.created_at.desc()
        )
        .all()
    )

    return [
        {
            "enrollment_id": enrollment.id,
            "user_id": enrollment.user_id,
            "course_id": enrollment.course_id,

            "name": student.name,
            "email": student.email,
            "phone": student.phone,
            "parent_name": enrollment.parent_name,
            "parent_phone": enrollment.parent_phone,
            "highest_qualification": enrollment.highest_qualification,
            "address": enrollment.address,

            "course_title": enrollment.course_title,
            "course_image": course.image,
            "course_duration": course.duration,

            "amount": enrollment.total_fee,
            "total_fee": enrollment.total_fee,
            **enrollment_payment_summary(db, enrollment),

            # Payment status
            "payment_status": enrollment.status,

            # Branch approval status
            "course_status": enrollment.course_status,

            "razorpay_order_id": enrollment.razorpay_order_id,
            "razorpay_payment_id": enrollment.razorpay_payment_id,

            "created_at": enrollment.created_at
        }
        for enrollment, student, course in results
    ]





















# ============================================================
# GET PENDING PURCHASES
# BRANCH ADMIN ONLY
# ============================================================

@router.get(
    "/branch-admin/pending",
    tags=["Branch Admin Purchases"]
)
def get_pending_purchases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

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

    results = (
        db.query(
            Enrollment,
            User,
            Course
        )
        .join(
            User,
            Enrollment.user_id == User.id
        )
        .join(
            Course,
            Enrollment.course_id == Course.id
        )
        .filter(
            Enrollment.branch_id == current_user.branch_id,
            Enrollment.branch_approval_status == "pending"
        )
        .filter(
            or_(
                Enrollment.status == "paid",
                Enrollment.total_paid > 0,
            )
        )
        .order_by(
            Enrollment.created_at.desc()
        )
        .all()
    )

    return [
        {
            "enrollment_id": enrollment.id,
            "user_id": enrollment.user_id,
            "course_id": enrollment.course_id,

            "name": student.name,
            "email": student.email,
            "phone": student.phone,
            "parent_name": enrollment.parent_name,
            "parent_phone": enrollment.parent_phone,
            "highest_qualification": enrollment.highest_qualification,
            "address": enrollment.address,

            "course_title": enrollment.course_title,
            "course_image": course.image,
            "course_duration": course.duration,

            "amount": enrollment.total_fee,
            "total_fee": enrollment.total_fee,
            **enrollment_payment_summary(db, enrollment),

            "payment_status": enrollment.status,
            "course_status": enrollment.course_status,
            "branch_approval_status": enrollment.branch_approval_status,
            "super_admin_approval_status": enrollment.super_admin_approval_status,

            "razorpay_order_id": enrollment.razorpay_order_id,
            "razorpay_payment_id": enrollment.razorpay_payment_id,

            "created_at": enrollment.created_at
        }

        for enrollment, student, course in results
    ]


# ============================================================
# GET APPROVED PURCHASE HISTORY
# BRANCH ADMIN ONLY
# ============================================================

@router.get(
    "/branch-admin/approved",
    tags=["Branch Admin Purchases"]
)
def get_approved_purchases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

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

    results = (
        db.query(
            Enrollment,
            User,
            Course
        )
        .join(
            User,
            Enrollment.user_id == User.id
        )
        .join(
            Course,
            Enrollment.course_id == Course.id
        )
        .filter(
            Enrollment.branch_id == current_user.branch_id,
            Enrollment.branch_approval_status == "approved",
            Enrollment.super_admin_approval_status != "rejected",
            or_(
                Enrollment.status == "paid",
                Enrollment.total_paid > 0,
            ),
        )
        .order_by(
            Enrollment.created_at.desc()
        )
        .all()
    )

    return [
        {
            "enrollment_id": enrollment.id,
            "user_id": enrollment.user_id,
            "course_id": enrollment.course_id,

            "name": student.name,
            "email": student.email,
            "phone": student.phone,
            "parent_name": enrollment.parent_name,
            "parent_phone": enrollment.parent_phone,
            "highest_qualification": enrollment.highest_qualification,
            "address": enrollment.address,

            "course_title": enrollment.course_title,
            "course_image": course.image,
            "course_duration": course.duration,

            "amount": enrollment.total_fee,
            "total_fee": enrollment.total_fee,
            **enrollment_payment_summary(db, enrollment),

            "payment_status": enrollment.status,
            "course_status": enrollment.course_status,

            "razorpay_order_id": enrollment.razorpay_order_id,
            "razorpay_payment_id": enrollment.razorpay_payment_id,

            "created_at": enrollment.created_at
        }

        for enrollment, student, course in results
    ]


@router.get(
    "/branch-admin/rejected",
    tags=["Branch Admin Purchases"],
)
def get_rejected_purchases_for_branch_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required",
        )
    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch",
        )

    rows = (
        db.query(Enrollment, User, Course)
        .join(User, User.id == Enrollment.user_id)
        .join(Course, Course.id == Enrollment.course_id)
        .filter(
            Enrollment.branch_id == current_user.branch_id,
            Enrollment.super_admin_approval_status == "rejected",
            or_(
                Enrollment.status == "paid",
                Enrollment.total_paid > 0,
            ),
        )
        .order_by(Enrollment.super_admin_rejected_at.desc())
        .all()
    )
    return [
        {
            "enrollment_id": enrollment.id,
            "user_id": enrollment.user_id,
            "course_id": enrollment.course_id,
            "name": enrollment.name or student.name,
            "email": enrollment.email or student.email,
            "phone": enrollment.phone or student.phone,
            "parent_name": enrollment.parent_name,
            "parent_phone": enrollment.parent_phone,
            "highest_qualification": enrollment.highest_qualification,
            "address": enrollment.address,
            "course_title": enrollment.course_title or course.title,
            "course_image": course.image,
            "course_duration": course.duration,
            "total_fee": enrollment.total_fee,
            "amount": enrollment.total_fee,
            **enrollment_payment_summary(db, enrollment),
            "payment_status": enrollment.status,
            "course_status": enrollment.course_status,
            "super_admin_rejection_reason": enrollment.super_admin_rejection_reason,
            "super_admin_rejected_at": enrollment.super_admin_rejected_at,
            "created_at": enrollment.created_at,
        }
        for enrollment, student, course in rows
    ]


def require_branch_admin(current_user: User) -> int:
    if current_user.role != "branch_admin":
        raise HTTPException(status_code=403, detail="Branch admin access required")
    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch",
        )
    return current_user.branch_id


def serialize_installment_student_rows(db: Session, rows):
    return [
        build_installment_student_record(
            db, enrollment, student, course, branch_name
        )
        for enrollment, student, course, branch_name in rows
    ]


def get_installment_payment_rows(
    db: Session,
    branch_id: int | None,
    status: str,
    today_only: bool = False,
):
    query = (
        db.query(AdmissionPayment, Enrollment, User, Course, Branch.name)
        .join(Enrollment, Enrollment.id == AdmissionPayment.enrollment_id)
        .join(User, User.id == Enrollment.user_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Branch, Branch.id == Enrollment.branch_id)
        .filter(AdmissionPayment.status == status)
    )
    if status == "pending_review":
        query = query.filter(AdmissionPayment.payment_method == "razorpay")
    if branch_id is not None:
        query = query.filter(Enrollment.branch_id == branch_id)
    if today_only:
        query = query.filter(func.date(AdmissionPayment.created_at) == date.today())
    return query.order_by(
        AdmissionPayment.created_at.desc(),
        AdmissionPayment.id.desc(),
    ).all()


def serialize_installment_payment_rows(rows):
    return [
        build_installment_payment_record(
            payment, enrollment, student, course, branch_name
        )
        for payment, enrollment, student, course, branch_name in rows
    ]


@router.get(
    "/branch-admin/installment-students",
    tags=["Branch Admin Installments"],
)
def get_branch_admin_installment_students(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_branch_admin(current_user)
    rows = get_installment_student_rows(db, branch_id, fully_paid=False)
    students = serialize_installment_student_rows(db, rows)
    return {"count": len(students), "students": students}


@router.get(
    "/branch-admin/fully-paid-students",
    tags=["Branch Admin Installments"],
)
def get_branch_admin_fully_paid_students(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_branch_admin(current_user)
    rows = get_installment_student_rows(db, branch_id, fully_paid=True)
    students = serialize_installment_student_rows(db, rows)
    return {"count": len(students), "students": students}


@router.post(
    "/branch-admin/{enrollment_id}/installment-payments",
    tags=["Branch Admin Installments"],
)
def record_branch_admin_installment_payment(
    enrollment_id: int,
    data: BranchAdminInstallmentPaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_branch_admin(current_user)
    enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.id == enrollment_id,
            Enrollment.branch_id == branch_id,
        )
        .with_for_update()
        .first()
    )
    if not enrollment:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found in your branch",
        )

    installment = (
        db.query(EnrollmentInstallment)
        .filter(
            EnrollmentInstallment.enrollment_id == enrollment.id,
            EnrollmentInstallment.installment_number == data.installment_number,
        )
        .with_for_update()
        .first()
    )
    if not installment:
        raise HTTPException(status_code=404, detail="Installment not found")

    cash_amount = round(data.cash_amount, 2)
    upi_amount = round(data.upi_amount, 2)
    amount = round(cash_amount + upi_amount, 2)
    installment_remaining = round(
        installment.amount - installment.paid_amount, 2
    )
    enrollment_balance = round(enrollment.balance_amount or 0, 2)
    pending_amount = (
        db.query(func.coalesce(func.sum(AdmissionPayment.amount), 0))
        .filter(
            AdmissionPayment.installment_id == installment.id,
            AdmissionPayment.status == "pending_review",
        )
        .scalar()
    ) or 0
    available_amount = round(
        min(installment_remaining, enrollment_balance) - pending_amount, 2
    )
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Enter a cash or UPI amount")
    if amount > available_amount:
        raise HTTPException(
            status_code=400,
            detail=(
                "Payment cannot exceed the available installment balance "
                f"₹{max(available_amount, 0):.2f}"
            ),
        )

    payment_date = data.payment_date or date.today()
    installment.paid_amount = round(installment.paid_amount + amount, 2)
    installment.status = (
        "paid" if installment.paid_amount >= installment.amount else "partial"
    )
    if installment.status == "paid":
        installment.paid_amount = installment.amount
        installment.paid_date = payment_date
    installment.cash_amount = round(
        (installment.cash_amount or 0) + cash_amount, 2
    )
    installment.upi_amount = round(
        (installment.upi_amount or 0) + upi_amount, 2
    )

    payment = AdmissionPayment(
        enrollment_id=enrollment.id,
        installment_id=installment.id,
        installment_number=installment.installment_number,
        user_id=enrollment.user_id,
        branch_id=enrollment.branch_id,
        amount=amount,
        cash_amount=cash_amount,
        upi_amount=upi_amount,
        payment_method=(
            "cash_upi"
            if cash_amount > 0 and upi_amount > 0
            else "cash"
            if cash_amount > 0
            else "upi"
        ),
        payment_date=payment_date,
        status="received",
        reviewed_by_user_id=current_user.id,
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(payment)
    enrollment.total_paid = round((enrollment.total_paid or 0) + amount, 2)
    enrollment.balance_amount = max(
        round(enrollment.total_fee - enrollment.total_paid, 2), 0
    )
    enrollment.status = "paid" if enrollment.balance_amount == 0 else "pending"
    db.commit()
    db.refresh(payment)
    student = db.query(User).filter(User.id == enrollment.user_id).first()
    course = db.query(Course).filter(Course.id == enrollment.course_id).first()
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    return {
        "success": True,
        "message": "BranchAdmin cash/UPI installment payment recorded",
        **build_installment_payment_record(
            payment,
            enrollment,
            student,
            course,
            branch.name if branch else "",
        ),
    }


@router.get(
    "/branch-admin/installment-payments/today",
    tags=["Branch Admin Installments"],
)
def get_today_installment_payment_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_branch_admin(current_user)
    rows = get_installment_payment_rows(
        db, branch_id, "pending_review", today_only=True
    )
    payments = serialize_installment_payment_rows(rows)
    return {"date": date.today(), "count": len(payments), "payments": payments}


@router.get(
    "/branch-admin/installment-payments/pending",
    tags=["Branch Admin Installments"],
)
def get_pending_installment_payment_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_branch_admin(current_user)
    rows = get_installment_payment_rows(db, branch_id, "pending_review")
    payments = serialize_installment_payment_rows(rows)
    return {"count": len(payments), "payments": payments}


@router.put(
    "/branch-admin/installment-payments/{payment_id}/approve",
    tags=["Branch Admin Installments"],
)
def approve_installment_payment_request(
    payment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_branch_admin(current_user)
    payment = (
        db.query(AdmissionPayment)
        .filter(AdmissionPayment.id == payment_id)
        .with_for_update()
        .first()
    )
    if not payment or payment.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if payment.status != "pending_review":
        raise HTTPException(
            status_code=409,
            detail="Payment request is no longer pending",
        )
    if payment.payment_method != "razorpay":
        raise HTTPException(
            status_code=409,
            detail="Only verified Razorpay payments require approval",
        )

    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.id == payment.enrollment_id)
        .with_for_update()
        .first()
    )
    installment = (
        db.query(EnrollmentInstallment)
        .filter(EnrollmentInstallment.id == payment.installment_id)
        .with_for_update()
        .first()
    )
    if not enrollment or not installment:
        raise HTTPException(status_code=409, detail="Payment installment was not found")

    amount = round(payment.amount, 2)
    installment_remaining = round(installment.amount - installment.paid_amount, 2)
    enrollment_balance = round(enrollment.balance_amount or 0, 2)
    if amount > installment_remaining or amount > enrollment_balance:
        raise HTTPException(
            status_code=409,
            detail="Payment amount exceeds the current installment or enrollment balance",
        )

    installment.paid_amount = round(installment.paid_amount + amount, 2)
    installment.status = (
        "paid" if installment.paid_amount >= installment.amount else "partial"
    )
    if installment.status == "paid":
        installment.paid_amount = installment.amount
        installment.paid_date = payment.payment_date
    installment.cash_amount = round(
        (installment.cash_amount or 0) + payment.cash_amount, 2
    )
    installment.upi_amount = round(
        (installment.upi_amount or 0) + payment.upi_amount, 2
    )

    enrollment.total_paid = round((enrollment.total_paid or 0) + amount, 2)
    enrollment.balance_amount = max(
        round(enrollment.total_fee - enrollment.total_paid, 2), 0
    )
    enrollment.status = "paid" if enrollment.balance_amount == 0 else "pending"

    payment.status = "received"
    payment.reviewed_by_user_id = current_user.id
    payment.reviewed_at = datetime.now(timezone.utc)
    payment.rejection_reason = None

    db.commit()
    db.refresh(payment)
    student = db.query(User).filter(User.id == enrollment.user_id).first()
    course = db.query(Course).filter(Course.id == enrollment.course_id).first()
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    return {
        "success": True,
        "message": "Installment payment approved and applied to the student balance",
        **build_installment_payment_record(
            payment,
            enrollment,
            student,
            course,
            branch.name if branch else "",
        ),
    }


@router.put(
    "/branch-admin/installment-payments/{payment_id}/reject",
    tags=["Branch Admin Installments"],
)
def reject_installment_payment_request(
    payment_id: int,
    data: InstallmentPaymentReject,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_branch_admin(current_user)
    payment = (
        db.query(AdmissionPayment)
        .filter(
            AdmissionPayment.id == payment_id,
            AdmissionPayment.branch_id == branch_id,
        )
        .with_for_update()
        .first()
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if payment.status != "pending_review":
        raise HTTPException(status_code=409, detail="Payment request is no longer pending")
    if payment.payment_method != "razorpay":
        raise HTTPException(
            status_code=409,
            detail="Only verified Razorpay payments can be rejected here",
        )
    reason = data.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required")

    payment.status = "rejected"
    payment.reviewed_by_user_id = current_user.id
    payment.reviewed_at = datetime.now(timezone.utc)
    payment.rejection_reason = reason
    db.commit()
    db.refresh(payment)
    enrollment = db.query(Enrollment).filter(
        Enrollment.id == payment.enrollment_id
    ).first()
    student = db.query(User).filter(User.id == payment.user_id).first()
    course = db.query(Course).filter(Course.id == enrollment.course_id).first()
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    return {
        "success": True,
        "message": (
            "Installment payment rejected in the enrollment records. "
            "This does not refund the Razorpay charge."
        ),
        **build_installment_payment_record(
            payment,
            enrollment,
            student,
            course,
            branch.name if branch else "",
        ),
    }


@router.get(
    "/branch-admin/installment-payments/history",
    tags=["Branch Admin Installments"],
)
def get_branch_admin_installment_payment_history(
    status: str = Query(default="received"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_branch_admin(current_user)
    if status not in {"received", "rejected"}:
        raise HTTPException(
            status_code=400,
            detail="Status must be received or rejected",
        )
    rows = get_installment_payment_rows(db, branch_id, status)
    payments = [
        build_installment_payment_record(
            payment, enrollment, student, course, branch_name
        )
        for payment, enrollment, student, course, branch_name in rows
        if payment.reviewed_by_user_id is not None
    ]
    return {"count": len(payments), "payments": payments}


def require_super_admin_branch(db: Session, branch_id: int | None):
    if branch_id is not None and not db.query(Branch.id).filter(
        Branch.id == branch_id
    ).first():
        raise HTTPException(status_code=404, detail="Branch not found")


@router.get(
    "/super-admin/installment-students",
    tags=["Super Admin Installments"],
)
def get_super_admin_installment_students(
    branch_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    require_super_admin_branch(db, branch_id)
    rows = get_installment_student_rows(db, branch_id, fully_paid=False)
    students = serialize_installment_student_rows(db, rows)
    return {"count": len(students), "students": students}


@router.get(
    "/super-admin/fully-paid-students",
    tags=["Super Admin Installments"],
)
def get_super_admin_fully_paid_students(
    branch_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    require_super_admin_branch(db, branch_id)
    rows = get_installment_student_rows(db, branch_id, fully_paid=True)
    students = serialize_installment_student_rows(db, rows)
    return {"count": len(students), "students": students}


@router.get(
    "/super-admin/branch-admin-installment-history",
    tags=["Super Admin Installments"],
)
def get_super_admin_branch_admin_installment_history(
    branch_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    require_super_admin_branch(db, branch_id)
    rows = (
        get_installment_payment_rows(db, branch_id, "received")
        + get_installment_payment_rows(db, branch_id, "rejected")
    )
    payments = [
        build_installment_payment_record(
            payment, enrollment, student, course, branch_name
        )
        for payment, enrollment, student, course, branch_name in rows
        if payment.reviewed_by_user_id is not None
    ]
    payments.sort(
        key=lambda payment: (
            str(payment["reviewed_at"] or payment["created_at"] or ""),
            payment["payment_id"],
        ),
        reverse=True,
    )
    return {"count": len(payments), "payments": payments}


# ============================================================
# APPROVE PURCHASE
# BRANCH ADMIN ONLY
# ============================================================

@router.put(
    "/branch-admin/{enrollment_id}/approve",
    tags=["Branch Admin Purchases"]
)
def approve_purchase(
    enrollment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

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

    enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.id == enrollment_id,
            Enrollment.branch_id == current_user.branch_id
        )
        .first()
    )

    if not enrollment:
        raise HTTPException(
            status_code=404,
            detail="Purchase not found in your branch"
        )

    # Require at least one payment before branch approval.
    if enrollment.status != "paid" and enrollment.total_paid <= 0:
        raise HTTPException(
            status_code=400,
            detail="At least one payment is required before approval"
        )

    if enrollment.branch_approval_status == "approved":
        raise HTTPException(
            status_code=400,
            detail="Branch has already approved this enrollment"
        )

    enrollment.branch_approval_status = "approved"
    enrollment.super_admin_approval_status = "pending"
    enrollment.course_status = "partially_approved"

    db.commit()
    db.refresh(enrollment)

    return {
        "success": True,
        "message": "Branch approval saved; super-admin approval is required",

        "enrollment_id": enrollment.id,

        "payment_status": enrollment.status,
        "course_status": enrollment.course_status,
        "branch_approval_status": enrollment.branch_approval_status,
        "super_admin_approval_status": enrollment.super_admin_approval_status,
        "super_admin_rejection_reason": enrollment.super_admin_rejection_reason,
        "super_admin_rejected_at": enrollment.super_admin_rejected_at,

        "razorpay_payment_id": enrollment.razorpay_payment_id
    }


def super_admin_purchase_record(
    db: Session,
    enrollment: Enrollment,
    student: User,
    course: Course,
    branch_name: str,
):
    return {
        "enrollment_id": enrollment.id,
        "user_id": enrollment.user_id,
        "course_id": enrollment.course_id,
        "branch_id": enrollment.branch_id,
        "branch_name": branch_name,
        "name": enrollment.name or student.name,
        "email": enrollment.email or student.email,
        "phone": enrollment.phone or student.phone,
        "parent_name": enrollment.parent_name,
        "parent_phone": enrollment.parent_phone,
        "highest_qualification": enrollment.highest_qualification,
        "address": enrollment.address,
        "course_title": enrollment.course_title or course.title,
        "course_image": course.image,
        "course_duration": course.duration,
        "total_fee": enrollment.total_fee,
        "amount": enrollment.total_fee,
        **enrollment_payment_summary(db, enrollment),
        "payment_status": enrollment.status,
        "course_status": enrollment.course_status,
        "branch_approval_status": enrollment.branch_approval_status,
        "super_admin_approval_status": enrollment.super_admin_approval_status,
        "super_admin_rejection_reason": enrollment.super_admin_rejection_reason,
        "super_admin_rejected_at": enrollment.super_admin_rejected_at,
        "razorpay_order_id": enrollment.razorpay_order_id,
        "razorpay_payment_id": enrollment.razorpay_payment_id,
        "created_at": enrollment.created_at,
    }


def get_super_admin_purchase_rows(
    db: Session,
    branch_id: int | None,
    queue: str,
):
    if branch_id is not None:
        branch = db.query(Branch).filter(Branch.id == branch_id).first()
        if not branch:
            raise HTTPException(status_code=404, detail="Branch not found")

    query = (
        db.query(Enrollment, User, Course, Branch.name)
        .join(User, Enrollment.user_id == User.id)
        .join(Course, Enrollment.course_id == Course.id)
        .join(Branch, Enrollment.branch_id == Branch.id)
    )
    if branch_id is not None:
        query = query.filter(Enrollment.branch_id == branch_id)

    if queue == "pending":
        query = query.filter(
            Enrollment.branch_approval_status == "approved",
            Enrollment.super_admin_approval_status == "pending",
            or_(
                Enrollment.status == "paid",
                Enrollment.total_paid > 0,
            ),
        )
    elif queue == "approved":
        query = query.filter(
            Enrollment.super_admin_approval_status == "approved",
            or_(
                Enrollment.status == "paid",
                Enrollment.total_paid > 0,
            ),
        )
    elif queue == "rejected":
        query = query.filter(
            Enrollment.super_admin_approval_status == "rejected",
            or_(
                Enrollment.status == "paid",
                Enrollment.total_paid > 0,
            ),
        )
    else:
        query = query.filter(
            or_(
                Enrollment.status == "paid",
                Enrollment.total_paid > 0,
            )
        )

    return query.order_by(Enrollment.created_at.desc()).all()


@router.get(
    "/super-admin/branches",
    tags=["Super Admin Purchases"],
)
def get_super_admin_purchase_branches(
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
        {"branch_id": branch.id, "branch_name": branch.name}
        for branch in branches
    ]


@router.get(
    "/super-admin/pending",
    tags=["Super Admin Purchases"],
)
def get_super_admin_pending_purchases(
    branch_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    results = get_super_admin_purchase_rows(db, branch_id, "pending")
    return [
        super_admin_purchase_record(
            db, enrollment, student, course, branch_name
        )
        for enrollment, student, course, branch_name in results
    ]


@router.get(
    "/super-admin/approved",
    tags=["Super Admin Purchases"],
)
def get_super_admin_approved_purchases(
    branch_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    results = get_super_admin_purchase_rows(db, branch_id, "approved")
    return [
        super_admin_purchase_record(
            db, enrollment, student, course, branch_name
        )
        for enrollment, student, course, branch_name in results
    ]


@router.get(
    "/super-admin/rejected",
    tags=["Super Admin Purchases"],
)
def get_super_admin_rejected_purchases(
    branch_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    results = get_super_admin_purchase_rows(db, branch_id, "rejected")
    return [
        super_admin_purchase_record(db, enrollment, student, course, branch_name)
        for enrollment, student, course, branch_name in results
    ]


@router.get(
    "/super-admin/history",
    tags=["Super Admin Purchases"],
)
def get_super_admin_purchase_history(
    branch_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    results = get_super_admin_purchase_rows(db, branch_id, "history")
    return [
        super_admin_purchase_record(
            db, enrollment, student, course, branch_name
        )
        for enrollment, student, course, branch_name in results
    ]


@router.put(
    "/super-admin/{enrollment_id}/approve",
    tags=["Super Admin Purchases"],
)
def approve_purchase_as_super_admin(
    enrollment_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.id == enrollment_id)
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Purchase not found")
    if enrollment.status != "paid" and enrollment.total_paid <= 0:
        raise HTTPException(
            status_code=400,
            detail="At least one payment is required before approval",
        )
    if enrollment.branch_approval_status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Branch admin approval is required first",
        )
    if enrollment.super_admin_approval_status == "approved":
        raise HTTPException(
            status_code=400,
            detail="Super-admin has already approved this enrollment",
        )
    if enrollment.super_admin_approval_status == "rejected":
        raise HTTPException(
            status_code=409,
            detail="A rejected enrollment cannot be approved",
        )

    enrollment.super_admin_approval_status = "approved"
    enrollment.course_status = "approved"
    db.commit()
    db.refresh(enrollment)

    student = db.query(User).filter(User.id == enrollment.user_id).first()
    course = db.query(Course).filter(Course.id == enrollment.course_id).first()
    branch = db.query(Branch).filter(Branch.id == enrollment.branch_id).first()
    return {
        "success": True,
        "message": "Enrollment fully approved",
        **super_admin_purchase_record(
            db,
            enrollment,
            student,
            course,
            branch.name if branch else "",
        ),
    }


@router.put(
    "/super-admin/{enrollment_id}/reject",
    tags=["Super Admin Purchases"],
)
def reject_purchase_as_super_admin(
    enrollment_id: int,
    rejection_data: SuperAdminPurchaseReject,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    enrollment = (
        db.query(Enrollment)
        .filter(Enrollment.id == enrollment_id)
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Purchase not found")
    if enrollment.status != "paid" and enrollment.total_paid <= 0:
        raise HTTPException(
            status_code=400,
            detail="At least one payment is required before rejection",
        )
    if enrollment.branch_approval_status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Branch admin approval is required first",
        )
    if enrollment.super_admin_approval_status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only pending super-admin approvals can be rejected",
        )

    reason = rejection_data.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required")

    enrollment.super_admin_approval_status = "rejected"
    enrollment.course_status = "rejected"
    enrollment.super_admin_rejection_reason = reason
    enrollment.super_admin_rejected_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(enrollment)

    student = db.query(User).filter(User.id == enrollment.user_id).first()
    course = db.query(Course).filter(Course.id == enrollment.course_id).first()
    branch = db.query(Branch).filter(Branch.id == enrollment.branch_id).first()
    return {
        "success": True,
        "message": "Enrollment rejected",
        **super_admin_purchase_record(
            db,
            enrollment,
            student,
            course,
            branch.name if branch else "",
        ),
    }