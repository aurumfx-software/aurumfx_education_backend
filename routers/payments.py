import os
import hmac
import hashlib
from html import escape
import requests

from datetime import date, datetime, timezone
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
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
    course_id: int | None = None
    enrollment_id: int | None = None
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
                status="pending_review",
                credited_to_balance=True,
                payment_reference=payment_id,
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


def build_student_receipt(
    db: Session,
    enrollment: Enrollment,
    payment_order: RazorpayPaymentOrder,
):
    if payment_order.status != "paid" or not payment_order.razorpay_payment_id:
        raise HTTPException(status_code=404, detail="Verified receipt not found")

    student = db.query(User).filter(User.id == enrollment.user_id).first()
    course = db.query(Course).filter(Course.id == enrollment.course_id).first()
    if not student or not course:
        raise HTTPException(
            status_code=404,
            detail="Student or course details for this receipt were not found",
        )

    allocations = (
        db.query(AdmissionPayment)
        .filter(
            AdmissionPayment.enrollment_id == enrollment.id,
            AdmissionPayment.payment_reference == payment_order.razorpay_payment_id,
            AdmissionPayment.payment_method == "razorpay",
        )
        .order_by(AdmissionPayment.installment_number.asc())
        .all()
    )
    if not allocations:
        raise HTTPException(
            status_code=404,
            detail="Verified payment details for this receipt were not found",
        )

    installment_numbers = sorted(
        {payment.installment_number for payment in allocations}
    )
    installment_count = (
        db.query(EnrollmentInstallment)
        .filter(EnrollmentInstallment.enrollment_id == enrollment.id)
        .count()
    )
    if payment_order.installment_id:
        installment = (
            db.query(EnrollmentInstallment)
            .filter(EnrollmentInstallment.id == payment_order.installment_id)
            .first()
        )
        number = (
            installment.installment_number
            if installment
            else installment_numbers[0]
        )
        payment_type = f"Installment {number} of {installment_count}"
    elif (enrollment.balance_amount or 0) <= 0:
        payment_type = "Remaining course balance settlement"
    else:
        payment_type = "Course payment"

    receipt_date = max(payment.payment_date for payment in allocations)
    return {
        "receipt_id": payment_order.id,
        "receipt_number": (
            f"AFX-{receipt_date.strftime('%Y%m%d')}-{payment_order.id:06d}"
        ),
        "academy_name": "AurumFX Academy",
        "student_name": enrollment.name or student.name,
        "student_email": enrollment.email or student.email,
        "student_phone": enrollment.phone or student.phone,
        "course_id": course.id,
        "course_name": enrollment.course_title or course.title,
        "enrollment_id": enrollment.id,
        "payment_type": payment_type,
        "installment_numbers": installment_numbers,
        "installment_count": installment_count,
        "amount_paid": round(float(payment_order.amount), 2),
        "currency": "INR",
        "payment_method": "Razorpay",
        "transaction_reference": payment_order.razorpay_payment_id,
        "upi_transaction_id": "",
        "cash_amount": 0.0,
        "upi_amount": 0.0,
        "razorpay_order_id": payment_order.razorpay_order_id,
        "razorpay_payment_id": payment_order.razorpay_payment_id,
        "payment_date": receipt_date.isoformat(),
        "payment_status": "Verified",
        "course_fee": round(float(enrollment.total_fee), 2),
        "total_paid": round(float(enrollment.total_paid or 0), 2),
        "balance_amount": round(float(enrollment.balance_amount or 0), 2),
        "quote": "Every step forward is progress worth celebrating.",
    }


def render_receipt_html(receipt: dict) -> str:
    safe = {
        key: escape(str(value))
        for key, value in receipt.items()
        if value is not None
    }
    safe.setdefault("branch_name", "")
    safe.setdefault("upi_transaction_id", "")
    for key in (
        "amount_paid",
        "cash_amount",
        "upi_amount",
        "course_fee",
        "total_paid",
        "balance_amount",
    ):
        safe[key] = f"{float(receipt[key]):,.2f}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Payment receipt {safe['receipt_number']}</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, "Segoe UI", Arial, sans-serif; }}
    body {{ margin: 0; padding: 36px 16px; background: #f1f5f9; color: #172033; }}
    .receipt {{ max-width: 720px; margin: auto; padding: 40px; background: #fff;
      border-radius: 18px; box-shadow: 0 18px 55px #17203318; }}
    .top {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start;
      border-bottom: 1px solid #e2e8f0; padding-bottom: 24px; }}
    .brand {{ color: #173b70; font-size: 25px; font-weight: 800; }}
    .subtitle, .muted {{ color: #64748b; font-size: 13px; }}
    .badge {{ padding: 8px 12px; border-radius: 999px; background: #dcfce7;
      color: #166534; font-size: 12px; font-weight: 700; }}
    h1 {{ margin: 28px 0 6px; font-size: 27px; }}
    .amount {{ margin: 22px 0; padding: 22px; border-radius: 14px;
      background: linear-gradient(130deg, #102e59, #245b9e); color: white; }}
    .amount small {{ display: block; opacity: .8; margin-bottom: 6px; }}
    .amount strong {{ font-size: 34px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px 24px; padding: 18px 0; }}
    .label {{ display: block; color: #64748b; font-size: 12px; margin-bottom: 5px; }}
    .value {{ font-size: 14px; font-weight: 650; overflow-wrap: anywhere; }}
    .quote {{ margin-top: 24px; padding: 18px; border-left: 3px solid #d5a33b;
      background: #fffbeb; color: #66521e; font-style: italic; }}
    footer {{ margin-top: 26px; padding-top: 16px; border-top: 1px solid #e2e8f0;
      color: #64748b; font-size: 12px; text-align: center; }}
    .print {{ display: block; margin: 22px auto 0; padding: 11px 18px; border: 0;
      border-radius: 8px; background: #173b70; color: #fff; font-size: 14px; cursor: pointer; }}
    @media (max-width: 560px) {{ .receipt {{ padding: 24px 20px; }} .grid {{ grid-template-columns: 1fr; }}
      .top {{ flex-direction: column; }} }}
    @media print {{ body {{ padding: 0; background: white; }} .receipt {{ box-shadow: none; }} .print {{ display: none; }} }}
  </style>
</head>
<body>
  <main class="receipt">
    <header class="top">
      <div><div class="brand">{safe['academy_name']}</div>
        <div class="subtitle">Official course payment receipt</div></div>
      <span class="badge">{safe['payment_status'].upper()}</span>
    </header>
    <h1>Payment receipt</h1>
    <div class="muted">Receipt no. {safe['receipt_number']} &nbsp;·&nbsp; {safe['payment_date']}</div>
    <section class="amount"><small>Amount received</small>
      <strong>₹{safe['amount_paid']}</strong></section>
    <section class="grid">
      <div><span class="label">Student</span><span class="value">{safe['student_name']}</span></div>
      <div><span class="label">Course</span><span class="value">{safe['course_name']}</span></div>
      <div><span class="label">Branch</span><span class="value">{safe['branch_name']}</span></div>
      <div><span class="label">Payment type</span><span class="value">{safe['payment_type']}</span></div>
      <div><span class="label">Payment method</span><span class="value">{safe['payment_method']}</span></div>
      <div><span class="label">Transaction reference</span><span class="value">{safe['transaction_reference']}</span></div>
      <div><span class="label">Cash portion</span><span class="value">₹{safe['cash_amount']}</span></div>
      <div><span class="label">UPI portion</span><span class="value">₹{safe['upi_amount']}</span></div>
      <div><span class="label">UPI transaction ID</span><span class="value">{safe['upi_transaction_id']}</span></div>
      <div><span class="label">Razorpay payment ID</span><span class="value">{safe['razorpay_payment_id']}</span></div>
      <div><span class="label">Razorpay order ID</span><span class="value">{safe['razorpay_order_id']}</span></div>
      <div><span class="label">Course fee</span><span class="value">₹{safe['course_fee']}</span></div>
      <div><span class="label">Paid to date</span><span class="value">₹{safe['total_paid']}</span></div>
      <div><span class="label">Remaining balance</span><span class="value">₹{safe['balance_amount']}</span></div>
    </section>
    <div class="quote">“{safe['quote']}”</div>
    <footer>This receipt records your course payment. Keep it for your records.<br>
      Thank you for choosing AurumFX Academy.</footer>
    <button class="print" onclick="window.print()">Print / Save as PDF</button>
  </main>
</body>
</html>"""


def get_student_receipt_order(
    db: Session,
    current_user: User,
    receipt_id: int,
):
    result = (
        db.query(RazorpayPaymentOrder, Enrollment)
        .join(Enrollment, Enrollment.id == RazorpayPaymentOrder.enrollment_id)
        .filter(
            RazorpayPaymentOrder.id == receipt_id,
            Enrollment.user_id == current_user.id,
            RazorpayPaymentOrder.status == "paid",
            RazorpayPaymentOrder.razorpay_payment_id.isnot(None),
        )
        .first()
    )
    return result


def ensure_student(current_user: User):
    if current_user.role != "user":
        raise HTTPException(
            status_code=403,
            detail="Only students can access payment receipts",
        )


def get_student_branch_payment_receipt(
    db: Session,
    current_user: User,
    receipt_id: int,
):
    from routers.branch_receipts import list_receipts

    branch_ids = (
        db.query(Enrollment.branch_id)
        .filter(Enrollment.user_id == current_user.id)
        .distinct()
        .all()
    )
    for row in branch_ids:
        receipts = list_receipts(
            db,
            row.branch_id,
            from_date=None,
            to_date=None,
            user_id=current_user.id,
            include_razorpay=False,
        )
        for receipt in receipts:
            if receipt["receipt_id"] == receipt_id:
                return receipt
    return None


@router.get("/receipts")
def list_student_receipts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_student(current_user)
    paid_orders = (
        db.query(RazorpayPaymentOrder, Enrollment)
        .join(Enrollment, Enrollment.id == RazorpayPaymentOrder.enrollment_id)
        .filter(
            Enrollment.user_id == current_user.id,
            RazorpayPaymentOrder.status == "paid",
            RazorpayPaymentOrder.razorpay_payment_id.isnot(None),
        )
        .order_by(RazorpayPaymentOrder.id.desc())
        .all()
    )
    razorpay_receipts = [
        build_student_receipt(db, enrollment, payment_order)
        for payment_order, enrollment in paid_orders
    ]
    from routers.branch_receipts import list_receipts

    student_branch_ids = [
        row.branch_id
        for row in (
            db.query(Enrollment.branch_id)
            .filter(Enrollment.user_id == current_user.id)
            .distinct()
            .all()
        )
    ]
    branch_payment_receipts = []
    for branch_id in student_branch_ids:
        branch_payment_receipts.extend(
            list_receipts(
                db,
                branch_id,
                from_date=None,
                to_date=None,
                user_id=current_user.id,
                include_razorpay=False,
            )
        )
    receipts = razorpay_receipts + branch_payment_receipts
    receipts.sort(
        key=lambda receipt: (
            receipt["payment_date"],
            receipt["receipt_id"],
        ),
        reverse=True,
    )
    for receipt in receipts:
        receipt["receipt_url"] = f"/payments/receipts/{receipt['receipt_id']}"
        receipt["download_url"] = (
            f"/payments/receipts/{receipt['receipt_id']}/download"
        )
    return {
        "total_receipts": len(receipts),
        "receipts": receipts,
    }


@router.get("/receipts/{receipt_id}")
def view_student_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_student(current_user)
    result = get_student_receipt_order(
        db,
        current_user,
        receipt_id,
    )
    if result:
        payment_order, enrollment = result
        receipt = build_student_receipt(db, enrollment, payment_order)
    else:
        receipt = get_student_branch_payment_receipt(
            db,
            current_user,
            receipt_id,
        )
    if not result and not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return HTMLResponse(content=render_receipt_html(receipt))


@router.get("/receipts/{receipt_id}/download")
def download_student_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_student(current_user)
    result = get_student_receipt_order(
        db,
        current_user,
        receipt_id,
    )
    if result:
        payment_order, enrollment = result
        receipt = build_student_receipt(db, enrollment, payment_order)
    else:
        receipt = get_student_branch_payment_receipt(
            db,
            current_user,
            receipt_id,
        )
    if not result and not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    filename = f"{receipt['receipt_number']}.html"
    return HTMLResponse(
        content=render_receipt_html(receipt),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


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

    if payment_data.course_id is None and payment_data.enrollment_id is None:
        raise HTTPException(
            status_code=400,
            detail="course_id or enrollment_id is required",
        )

    if (
        payment_data.payment_type == "full"
        and payment_data.installment_number is not None
    ):
        raise HTTPException(
            status_code=400,
            detail="Do not provide installment_number for full payment",
        )

    existing_enrollment = None
    if payment_data.enrollment_id is not None:
        existing_enrollment = (
            db.query(Enrollment)
            .filter(
                Enrollment.id == payment_data.enrollment_id,
                Enrollment.user_id == current_user.id,
            )
            .with_for_update()
            .first()
        )
        if not existing_enrollment:
            raise HTTPException(status_code=404, detail="Enrollment not found")
        if (
            payment_data.course_id is not None
            and payment_data.course_id != existing_enrollment.course_id
        ):
            raise HTTPException(
                status_code=400,
                detail="Course does not match the enrollment",
            )
        course = (
            db.query(Course)
            .filter(Course.id == existing_enrollment.course_id)
            .first()
        )
    else:
        course = (
            db.query(Course)
            .filter(
                Course.id == payment_data.course_id,
                Course.is_active == True,
            )
            .first()
        )
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")
        existing_enrollment = (
            db.query(Enrollment)
            .filter(
                Enrollment.user_id == current_user.id,
                Enrollment.course_id == course.id,
            )
            .first()
        )

    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if not course.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Course is not assigned to a branch",
        )

    if (
        payment_data.payment_type == "installment"
        and payment_data.installment_number is None
        and existing_enrollment is None
    ):
        raise HTTPException(
            status_code=400,
            detail="installment_number is required for a new enrollment",
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
        if payment_data.installment_number is None:
            selected_installment = next(
                (term for term in installments if term.status != "paid"),
                None,
            )
        else:
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

    pending_payment = (
        db.query(AdmissionPayment.id)
        .filter(
            AdmissionPayment.enrollment_id == enrollment.id,
            AdmissionPayment.status == "pending_review",
        )
        .first()
    )
    if pending_payment:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A Razorpay installment payment is awaiting BranchAdmin review",
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
        payment_record = (
            db.query(AdmissionPayment)
            .filter(
                AdmissionPayment.enrollment_id == enrollment.id,
                AdmissionPayment.payment_reference
                == payment_order.razorpay_payment_id,
            )
            .first()
        )
        review_status = (
            "pending"
            if payment_record and payment_record.status == "pending_review"
            else "rejected"
            if payment_record and payment_record.status == "rejected"
            else "approved"
            if payment_record and payment_record.reviewed_by_user_id
            else "not_required"
        )
        receipt = build_student_receipt(db, enrollment, payment_order)
        return {
            "success": True,
            "message": "Payment already verified",
            "payment_status": "paid",
            "approval_status": review_status,
            "installment_payment_status": (
                payment_record.status if payment_record else "received"
            ),
            "credited_to_balance": (
                payment_record.credited_to_balance if payment_record else False
            ),
            "enrollment_id": enrollment.id,
            "status": enrollment.status,
            "total_paid": enrollment.total_paid,
            "balance_amount": enrollment.balance_amount,
            "razorpay_order_id": payment_order.razorpay_order_id,
            "razorpay_payment_id": payment_order.razorpay_payment_id,
            "paid_at": enrollment.paid_at,
            "receipt": receipt,
            "receipt_url": f"/payments/receipts/{payment_order.id}",
            "receipt_download_url": (
                f"/payments/receipts/{payment_order.id}/download"
            ),
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
    db.refresh(payment_order)
    receipt = build_student_receipt(db, enrollment, payment_order)
    return {
        "success": True,
        "message": (
            "Payment verified and credited successfully; BranchAdmin review is pending"
        ),
        "payment_status": "paid",
        "approval_status": "pending",
        "installment_payment_status": "pending_review",
        "credited_to_balance": True,
        "enrollment_id": enrollment.id,
        "status": enrollment.status,
        "course_status": enrollment.course_status,
        "branch_approval_status": enrollment.branch_approval_status,
        "super_admin_approval_status": enrollment.super_admin_approval_status,
        "course_status": enrollment.course_status,
        "total_fee": enrollment.total_fee,
        "total_paid": enrollment.total_paid,
        "balance_amount": enrollment.balance_amount,
        "razorpay_order_id": payment_order.razorpay_order_id,
        "razorpay_payment_id": payment_data.razorpay_payment_id,
        "paid_at": enrollment.paid_at,
        "receipt": receipt,
        "receipt_url": f"/payments/receipts/{payment_order.id}",
        "receipt_download_url": (
            f"/payments/receipts/{payment_order.id}/download"
        ),
    }