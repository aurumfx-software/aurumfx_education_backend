from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from database import SessionLocal
from database_models import (
    Enrollment,
    EnrollmentInstallment,
    RazorpayPaymentOrder,
    Course,
    User,
)

from schemas.enrollment import (
    EnrollmentResponse,
    AdminEnrollmentResponse,
    BranchAdminEnrollmentUpdate,
)

from routers.auth import get_current_user


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
        "due_installment_count": len(due_installments),
        "installments": [
            {
                "installment_id": installment.id,
                "installment_number": installment.installment_number,
                "amount": installment.amount,
                "paid_amount": installment.paid_amount,
                "remaining_amount": round(
                    installment.amount - installment.paid_amount, 2
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
            if term.paid_amount > 0:
                submitted = submitted_by_number.get(number)
                if (
                    submitted is None
                    or round(submitted["amount"], 2) != round(term.amount, 2)
                    or submitted["due_date"] != term.due_date
                ):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Paid or partially paid installment {number} cannot be changed or removed",
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
    }


# ============================================================
# GET MY ENROLLMENTS
# STUDENT ONLY
# ============================================================

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
            Course
        )
        .join(
            Course,
            Enrollment.course_id == Course.id
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

            # Payment status
            "status": enrollment.status,

            # Branch approval status
            "course_status": enrollment.course_status,

            "razorpay_order_id": enrollment.razorpay_order_id,
            "razorpay_payment_id": enrollment.razorpay_payment_id,

            "created_at": enrollment.created_at
        }

        for enrollment, course in results
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

            "course_id": enrollment.course_id,
            "course_title": enrollment.course_title,
            "course_image": course.image,
            "course_duration": course.duration,

            "amount": enrollment.total_fee,

            # Payment status
            "payment_status": enrollment.status,

            # Branch approval status
            "course_status": enrollment.course_status,

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
            Enrollment.status == "paid",
            Enrollment.course_status == "pending"
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
            Enrollment.status == "paid",
            Enrollment.course_status == "approved"
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

    # Payment must be completed first
    if enrollment.status != "paid":
        raise HTTPException(
            status_code=400,
            detail="Payment has not been completed"
        )

    # Already approved
    if enrollment.course_status == "approved":
        raise HTTPException(
            status_code=400,
            detail="Course is already approved"
        )

    # Approve course
    enrollment.course_status = "approved"

    db.commit()
    db.refresh(enrollment)

    return {
        "success": True,
        "message": "Course purchase approved successfully",

        "enrollment_id": enrollment.id,

        "payment_status": enrollment.status,
        "course_status": enrollment.course_status,

        "razorpay_payment_id": enrollment.razorpay_payment_id
    }