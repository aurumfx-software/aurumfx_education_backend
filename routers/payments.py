import os
import hmac
import hashlib
import requests

from datetime import date, datetime, timezone
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    AdmissionPayment,
    Course,
    Enrollment,
    EnrollmentInstallment,
    RazorpayPaymentOrder,
    User,
)

from routers.auth import get_current_user


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/payments",
    tags=["Student Payments"]
)


# ============================================================
# RAZORPAY CONFIGURATION
# ============================================================

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

RAZORPAY_API_URL = "https://api.razorpay.com/v1"


# ============================================================
# DATABASE DEPENDENCY
# ============================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class CreateOrderRequest(BaseModel):
    course_id: int
    payment_type: Literal["full", "installment"] = "full"
    installment_number: int | None = Field(default=None, ge=1)


class VerifyPaymentRequest(BaseModel):
    enrollment_id: int
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


def ensure_installment_plan(
    db: Session,
    enrollment: Enrollment,
    course: Course,
):
    existing_terms = (
        db.query(EnrollmentInstallment)
        .filter(EnrollmentInstallment.enrollment_id == enrollment.id)
        .order_by(EnrollmentInstallment.installment_number.asc())
        .all()
    )
    if existing_terms:
        return existing_terms

    configured_terms = course.installment_terms or []
    configured_count = course.installment_count or 0
    base_date = course.start_date or date.today()
    if configured_count > 0 and len(configured_terms) == configured_count:
        term_data = configured_terms
    else:
        term_count = max(configured_count, 1)
        per_term_amount = round(enrollment.total_fee / term_count, 2)
        term_data = []
        for number in range(1, term_count + 1):
            if course.installment_schedule == "weekly":
                due_date = base_date + relativedelta(weeks=number - 1)
            else:
                due_date = base_date + relativedelta(months=number - 1)
            amount = (
                round(enrollment.total_fee - per_term_amount * (term_count - 1), 2)
                if number == term_count
                else per_term_amount
            )
            term_data.append({"amount": amount, "due_date": due_date})

    if round(sum(float(term["amount"]) for term in term_data), 2) != round(
        enrollment.total_fee, 2
    ):
        raise HTTPException(
            status_code=409,
            detail="Course installment amounts do not equal the course fee",
        )

    installments = []
    for number, term in enumerate(term_data, start=1):
        due_date = term["due_date"]
        if isinstance(due_date, str):
            due_date = date.fromisoformat(due_date)
        installment = EnrollmentInstallment(
            enrollment_id=enrollment.id,
            installment_number=number,
            amount=round(float(term["amount"]), 2),
            paid_amount=0,
            due_date=due_date,
            status="pending",
            paid_date=None,
            cash_amount=0,
            upi_amount=0,
        )
        db.add(installment)
        installments.append(installment)

    enrollment.installment_schedule = course.installment_schedule
    enrollment.installment_count = len(installments)
    enrollment.installment_amount = round(
        enrollment.total_fee / len(installments), 2
    )
    enrollment.total_paid = enrollment.total_paid or 0
    enrollment.balance_amount = round(
        enrollment.total_fee - enrollment.total_paid, 2
    )
    db.flush()
    return installments


def apply_student_payment(
    db: Session,
    enrollment: Enrollment,
    payment_order: RazorpayPaymentOrder,
    payment_id: str,
):
    payment_amount = round(payment_order.amount, 2)
    if payment_amount > round(enrollment.balance_amount or 0, 2):
        raise HTTPException(
            status_code=409,
            detail="Enrollment balance changed; payment needs review",
        )

    if payment_order.installment_id:
        selected_installment = (
            db.query(EnrollmentInstallment)
            .filter(
                EnrollmentInstallment.id == payment_order.installment_id,
                EnrollmentInstallment.enrollment_id == enrollment.id,
            )
            .with_for_update()
            .first()
        )
        if not selected_installment:
            raise HTTPException(
                status_code=404,
                detail="Approved installment not found for this enrollment",
            )
        approved_remaining = round(
            selected_installment.amount - selected_installment.paid_amount,
            2,
        )
        if payment_amount > approved_remaining:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Payment exceeds the approved remaining amount for this installment. "
                    f"Allowed: ₹{approved_remaining:.2f}"
                ),
            )

    if payment_order.installment_id:
        installments = (
            db.query(EnrollmentInstallment)
            .filter(
                EnrollmentInstallment.id == payment_order.installment_id,
                EnrollmentInstallment.enrollment_id == enrollment.id,
            )
            .with_for_update()
            .all()
        )
    else:
        installments = (
            db.query(EnrollmentInstallment)
            .filter(
                EnrollmentInstallment.enrollment_id == enrollment.id,
                EnrollmentInstallment.status != "paid",
            )
            .order_by(EnrollmentInstallment.installment_number.asc())
            .with_for_update()
            .all()
        )

    remaining = payment_amount
    payment_date = date.today()
    for installment in installments:
        if remaining <= 0:
            break
        term_remaining = round(installment.amount - installment.paid_amount, 2)
        if term_remaining <= 0:
            continue
        amount_for_term = round(min(remaining, term_remaining), 2)
        installment.paid_amount = round(
            installment.paid_amount + amount_for_term, 2
        )
        installment.status = (
            "paid" if installment.paid_amount >= installment.amount else "partial"
        )
        if installment.status == "paid":
            installment.paid_amount = installment.amount
            installment.paid_date = payment_date
        db.add(
            AdmissionPayment(
                enrollment_id=enrollment.id,
                installment_id=installment.id,
                installment_number=installment.installment_number,
                user_id=enrollment.user_id,
                branch_id=enrollment.branch_id,
                amount=amount_for_term,
                cash_amount=0,
                upi_amount=0,
                payment_method="razorpay",
                payment_date=payment_date,
                status="received",
            )
        )
        remaining = round(remaining - amount_for_term, 2)

    if remaining > 0:
        raise HTTPException(
            status_code=409,
            detail="Selected installment balance changed; payment needs review",
        )

    enrollment.total_paid = round((enrollment.total_paid or 0) + payment_amount, 2)
    enrollment.balance_amount = max(
        round(enrollment.total_fee - enrollment.total_paid, 2), 0
    )
    enrollment.status = "paid" if enrollment.balance_amount == 0 else "pending"
    enrollment.razorpay_payment_id = payment_id
    enrollment.paid_at = datetime.now(timezone.utc)
    payment_order.status = "paid"
    payment_order.razorpay_payment_id = payment_id


# ============================================================
# CHECK RAZORPAY CONFIGURATION
# ============================================================

def check_razorpay_config():

    if not RAZORPAY_KEY_ID:
        raise HTTPException(
            status_code=500,
            detail="RAZORPAY_KEY_ID is not configured"
        )

    if not RAZORPAY_KEY_SECRET:
        raise HTTPException(
            status_code=500,
            detail="RAZORPAY_KEY_SECRET is not configured"
        )


# ============================================================
# CREATE ENROLLMENT + RAZORPAY ORDER
# ============================================================

@router.post(
    "/create-order"
)
def create_order(
    payment_data: CreateOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # ========================================================
    # ONLY STUDENTS
    # ========================================================

    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can make payments"
        )

    # ========================================================
    # CHECK RAZORPAY CONFIGURATION
    # ========================================================

    check_razorpay_config()

    # ========================================================
    # FIND ACTIVE COURSE
    # ========================================================

    course = (
        db.query(Course)
        .filter(
            Course.id == payment_data.course_id,
            Course.is_active == True
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )

    # ========================================================
    # CHECK COURSE BRANCH
    # ========================================================

    if not course.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Course is not assigned to a branch"
        )

    if (
        payment_data.payment_type == "installment"
        and payment_data.installment_number is None
    ):
        raise HTTPException(
            status_code=400,
            detail="installment_number is required for installment payment",
        )
    if (
        payment_data.payment_type == "full"
        and payment_data.installment_number is not None
    ):
        raise HTTPException(
            status_code=400,
            detail="Do not provide installment_number for full payment",
        )

    # ========================================================
    # CHECK EXISTING ENROLLMENT
    # ========================================================

    existing_enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.user_id == current_user.id,
            Enrollment.course_id == course.id
        )
        .first()
    )

    # ========================================================
    # ALREADY PAID
    # ========================================================

    if existing_enrollment:

        if existing_enrollment.status == "paid":
            raise HTTPException(
                status_code=400,
                detail="You are already enrolled in this course"
            )

        # If pending enrollment already exists,
        # reuse it instead of creating another enrollment.

        enrollment = existing_enrollment

    else:

        # ====================================================
        # CREATE NEW PENDING ENROLLMENT
        # ====================================================

        enrollment = Enrollment(
            user_id=current_user.id,
            course_id=course.id,

            # Store course snapshot
            course_title=course.title,

            branch_id=course.branch_id,

            # Student details
            name=current_user.name,
            email=current_user.email,
            phone=current_user.phone,
            parent_name=current_user.parent_name,
            parent_phone=current_user.parent_phone,
            highest_qualification=current_user.highest_qualification,
            address=current_user.address,

            # Course fee
            total_fee=course.price,
            total_paid=0,
            balance_amount=course.price,
            installment_schedule=course.installment_schedule,
            installment_count=course.installment_count or 0,

            # Payment status
            status="pending",

            # Branch approval status
            course_status="pending",

            # Razorpay
            razorpay_order_id=None,
            razorpay_payment_id=None,

            # Payment date
            paid_at=None
        )

        db.add(enrollment)

    # ========================================================
    # FLUSH
    #
    # This gives us enrollment.id before committing.
    # ========================================================

    db.flush()

    # ========================================================
    # AMOUNT
    #
    # Resolve the selected term or full remaining balance.
    # ========================================================

    enrollment.total_paid = enrollment.total_paid or 0
    enrollment.balance_amount = max(
        round(enrollment.total_fee - enrollment.total_paid, 2),
        0,
    )
    if enrollment.balance_amount <= 0:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="You are already enrolled in this course",
        )

    installments = ensure_installment_plan(db, enrollment, course)
    selected_installment = None
    if payment_data.payment_type == "installment":
        selected_installment = next(
            (
                term
                for term in installments
                if term.installment_number == payment_data.installment_number
            ),
            None,
        )
        if not selected_installment:
            db.rollback()
            raise HTTPException(
                status_code=404,
                detail="Installment not found for this enrollment",
            )
        if selected_installment.status == "paid":
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="This installment is already paid",
            )
        approved_remaining = round(
            selected_installment.amount - selected_installment.paid_amount,
            2,
        )
        if approved_remaining <= 0:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail="This installment has no approved remaining amount left",
            )
        payment_amount = approved_remaining
    else:
        payment_amount = round(enrollment.balance_amount, 2)

    open_order = (
        db.query(RazorpayPaymentOrder)
        .filter(
            RazorpayPaymentOrder.enrollment_id == enrollment.id,
            RazorpayPaymentOrder.status == "created",
        )
        .first()
    )
    if open_order:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A payment order is already in progress for this enrollment",
        )

    if payment_amount <= 0 or payment_amount > enrollment.balance_amount:
        db.rollback()
        raise HTTPException(status_code=400, detail="No valid payment is due")

    amount_paise = int(
        round(payment_amount * 100)
    )

    if amount_paise <= 0:

        db.rollback()

        raise HTTPException(
            status_code=400,
            detail="Invalid payment amount"
        )

    # ========================================================
    # CREATE RAZORPAY ORDER
    # ========================================================

    payload = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": f"ENR-{enrollment.id}",
        "notes": {
            "enrollment_id": str(enrollment.id),
            "user_id": str(current_user.id),
            "course_id": str(course.id),
            "course_title": course.title,
            "payment_type": payment_data.payment_type,
            "installment_number": str(
                payment_data.installment_number or ""
            ),
        }
    }

    try:

        razorpay_response = requests.post(
            f"{RAZORPAY_API_URL}/orders",
            auth=(
                RAZORPAY_KEY_ID,
                RAZORPAY_KEY_SECRET
            ),
            json=payload,
            timeout=30
        )

    except requests.RequestException as e:

        db.rollback()

        raise HTTPException(
            status_code=502,
            detail=f"Unable to connect to Razorpay: {str(e)}"
        )

    # ========================================================
    # CHECK RAZORPAY RESPONSE
    # ========================================================

    if not razorpay_response.ok:

        db.rollback()

        try:
            error_data = razorpay_response.json()
        except Exception:
            error_data = razorpay_response.text

        print(
            "Razorpay Order Error:",
            error_data
        )

        raise HTTPException(
            status_code=502,
            detail="Razorpay failed to create order"
        )

    razorpay_data = razorpay_response.json()

    razorpay_order_id = razorpay_data.get("id")

    if not razorpay_order_id:

        db.rollback()

        raise HTTPException(
            status_code=502,
            detail="Razorpay did not return an order ID"
        )

    # ========================================================
    # SAVE RAZORPAY ORDER ID
    # ========================================================

    enrollment.razorpay_order_id = razorpay_order_id
    db.add(
        RazorpayPaymentOrder(
            enrollment_id=enrollment.id,
            installment_id=(
                selected_installment.id if selected_installment else None
            ),
            razorpay_order_id=razorpay_order_id,
            amount=payment_amount,
            status="created",
        )
    )

    # Payment is still pending until verification
    enrollment.status = "pending"

    # Course approval is also pending
    enrollment.course_status = "pending"

    # No payment date until payment is verified
    enrollment.paid_at = None

    # ========================================================
    # COMMIT ENROLLMENT
    # ========================================================

    db.commit()

    db.refresh(enrollment)

    paid_installment_count = sum(
        term.status == "paid" for term in installments
    )

    # ========================================================
    # RETURN ORDER DETAILS
    # ========================================================

    return {
        "success": True,

        "message": (
            "Enrollment and Razorpay order "
            "created successfully"
        ),

        "enrollment_id": enrollment.id,

        # Payment status
        "status": enrollment.status,

        # Branch approval status
        "course_status": enrollment.course_status,

        # Razorpay order
        "order_id": razorpay_order_id,

        # Amount
        "amount": payment_amount,
        "amount_paise": amount_paise,
        "currency": "INR",
        "payment_type": payment_data.payment_type,
        "installment_number": payment_data.installment_number,
        "installment_due_date": (
            selected_installment.due_date if selected_installment else None
        ),
        "total_fee": enrollment.total_fee,
        "total_paid": enrollment.total_paid,
        "balance_amount": enrollment.balance_amount,
        "installment_count": len(installments),
        "paid_installment_count": paid_installment_count,
        "remaining_installment_count": (
            len(installments) - paid_installment_count
        ),
        "installments": [
            {
                "installment_id": term.id,
                "installment_number": term.installment_number,
                "amount": term.amount,
                "paid_amount": term.paid_amount,
                "remaining_amount": round(term.amount - term.paid_amount, 2),
                "due_date": term.due_date,
                "status": term.status,
            }
            for term in installments
        ],

        # Razorpay public key
        "razorpay_key_id": RAZORPAY_KEY_ID,

        # Course
        "course": {
            "id": course.id,
            "title": course.title,
            "image": course.image
        },

        # Student
        "student": {
            "name": current_user.name,
            "email": current_user.email,
            "phone": current_user.phone
        }
    }


# ============================================================
# VERIFY RAZORPAY PAYMENT
# ============================================================

@router.post(
    "/verify"
)
def verify_payment(
    payment_data: VerifyPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # ========================================================
    # ONLY STUDENTS
    # ========================================================

    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can verify payments"
        )

    # ========================================================
    # CHECK RAZORPAY CONFIGURATION
    # ========================================================

    check_razorpay_config()

    # ========================================================
    # FIND ENROLLMENT
    # ========================================================

    enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.id == payment_data.enrollment_id,
            Enrollment.user_id == current_user.id
        )
        .first()
    )

    if not enrollment:
        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )

    payment_order = (
        db.query(RazorpayPaymentOrder)
        .filter(
            RazorpayPaymentOrder.enrollment_id == enrollment.id,
            RazorpayPaymentOrder.razorpay_order_id
            == payment_data.razorpay_order_id,
        )
        .with_for_update()
        .first()
    )

    if payment_order and payment_order.status == "paid":
        return {
            "success": True,
            "message": "Payment already verified",
            "enrollment_id": enrollment.id,
            "status": enrollment.status,
            "total_paid": enrollment.total_paid,
            "balance_amount": enrollment.balance_amount,
            "razorpay_order_id": payment_order.razorpay_order_id,
            "razorpay_payment_id": payment_order.razorpay_payment_id,
            "paid_at": enrollment.paid_at,
        }

    if not payment_order:
        if enrollment.razorpay_order_id != payment_data.razorpay_order_id:
            raise HTTPException(
                status_code=400,
                detail="Razorpay order ID does not match this enrollment",
            )
        if enrollment.status == "paid" and (enrollment.balance_amount or 0) <= 0:
            return {
                "success": True,
                "message": "Payment already verified",
                "enrollment_id": enrollment.id,
                "status": enrollment.status,
                "razorpay_order_id": enrollment.razorpay_order_id,
                "razorpay_payment_id": enrollment.razorpay_payment_id,
                "paid_at": enrollment.paid_at,
            }
        enrollment.total_paid = enrollment.total_paid or 0
        enrollment.balance_amount = max(
            round(enrollment.total_fee - enrollment.total_paid, 2),
            0,
        )
        payment_order = RazorpayPaymentOrder(
            enrollment_id=enrollment.id,
            installment_id=None,
            razorpay_order_id=payment_data.razorpay_order_id,
            amount=round(enrollment.balance_amount, 2),
            status="created",
        )
        db.add(payment_order)
        db.flush()

    if payment_order.status != "created":
        raise HTTPException(
            status_code=400,
            detail="This Razorpay order cannot be verified again",
        )

    generated_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        (
            payment_data.razorpay_order_id
            + "|"
            + payment_data.razorpay_payment_id
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(
        generated_signature,
        payment_data.razorpay_signature,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid Razorpay payment signature",
        )

    course = db.query(Course).filter(Course.id == enrollment.course_id).first()
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found for enrollment",
        )

    enrollment.total_paid = enrollment.total_paid or 0
    if enrollment.balance_amount is None:
        enrollment.balance_amount = round(
            enrollment.total_fee - enrollment.total_paid, 2
        )
    ensure_installment_plan(db, enrollment, course)
    apply_student_payment(
        db=db,
        enrollment=enrollment,
        payment_order=payment_order,
        payment_id=payment_data.razorpay_payment_id,
    )

    db.commit()
    db.refresh(enrollment)
    return {
        "success": True,
        "message": "Payment verified successfully",
        "enrollment_id": enrollment.id,
        "status": enrollment.status,
        "course_status": enrollment.course_status,
        "total_fee": enrollment.total_fee,
        "total_paid": enrollment.total_paid,
        "balance_amount": enrollment.balance_amount,
        "razorpay_order_id": payment_order.razorpay_order_id,
        "razorpay_payment_id": payment_data.razorpay_payment_id,
        "paid_at": enrollment.paid_at,
    }