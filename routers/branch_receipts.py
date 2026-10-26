from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    AdmissionPayment,
    Branch,
    Course,
    Enrollment,
    RazorpayPaymentOrder,
    User,
)
from routers.auth import get_current_user
from routers.payments import render_receipt_html


router = APIRouter(
    prefix="/branch-admin/receipts",
    tags=["Branch Admin Payment Receipts"],
)

BRANCH_RECEIPT_ID_OFFSET = 1_000_000_000


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_branch_admin(current_user: User) -> int:
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
    return current_user.branch_id


def payment_query(
    db: Session,
    branch_id: int | None,
    from_date: date | None = None,
    to_date: date | None = None,
    user_id: int | None = None,
    include_razorpay: bool = True,
):
    query = (
        db.query(
            AdmissionPayment,
            Enrollment,
            Course,
            User,
            Branch.name,
            RazorpayPaymentOrder,
        )
        .join(Enrollment, Enrollment.id == AdmissionPayment.enrollment_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(User, User.id == Enrollment.user_id)
        .join(Branch, Branch.id == AdmissionPayment.branch_id)
        .outerjoin(
            RazorpayPaymentOrder,
            and_(
                RazorpayPaymentOrder.enrollment_id == Enrollment.id,
                RazorpayPaymentOrder.razorpay_payment_id
                == AdmissionPayment.payment_reference,
            ),
        )
        .filter(
            or_(
                AdmissionPayment.status == "received",
                and_(
                    AdmissionPayment.payment_method == "razorpay",
                    AdmissionPayment.status.in_(["pending_review", "rejected"]),
                    RazorpayPaymentOrder.status == "paid",
                ),
            ),
        )
    )
    if branch_id is not None:
        query = query.filter(AdmissionPayment.branch_id == branch_id)
    if from_date is not None:
        query = query.filter(AdmissionPayment.payment_date >= from_date)
    if to_date is not None:
        query = query.filter(AdmissionPayment.payment_date <= to_date)
    if user_id is not None:
        query = query.filter(AdmissionPayment.user_id == user_id)
    if not include_razorpay:
        query = query.filter(AdmissionPayment.payment_method != "razorpay")
    return query.order_by(
        AdmissionPayment.payment_date.desc(),
        AdmissionPayment.id.desc(),
    )


def group_receipt_payments(rows):
    groups = {}
    for payment, enrollment, course, student, branch_name, payment_order in rows:
        if payment.payment_method == "razorpay":
            group_key = ("razorpay", payment.payment_reference)
        elif payment.payment_reference:
            group_key = ("branch", payment.payment_reference)
        else:
            group_key = ("payment", payment.id)
        groups.setdefault(group_key, []).append(
            (payment, enrollment, course, student, branch_name, payment_order)
        )
    return groups


def build_branch_receipt(group):
    payment, enrollment, course, student, branch_name, payment_order = group[0]
    payment_rows = [row[0] for row in group]
    payment_method = payment.payment_method
    method_labels = {
        "cash": "Cash",
        "upi": "UPI",
        "cash_upi": "Cash + UPI",
        "razorpay": "Razorpay",
    }
    cash_amount = round(
        sum(float(row.cash_amount or 0) for row in payment_rows),
        2,
    )
    upi_amount = round(
        sum(float(row.upi_amount or 0) for row in payment_rows),
        2,
    )
    if payment_method == "cash" and cash_amount == 0:
        cash_amount = round(sum(float(row.amount or 0) for row in payment_rows), 2)
    if payment_method == "upi" and upi_amount == 0:
        upi_amount = round(sum(float(row.amount or 0) for row in payment_rows), 2)
    if payment_method != "razorpay":
        payment_method = (
            "cash_upi"
            if cash_amount > 0 and upi_amount > 0
            else "cash"
            if cash_amount > 0
            else "upi"
        )

    installment_numbers = sorted(
        {row.installment_number for row in payment_rows}
    )
    installment_count = max(enrollment.installment_count or 0, len(installment_numbers))
    receipt_amount = round(
        sum(float(row.amount or 0) for row in payment_rows),
        2,
    )
    if receipt_amount >= float(enrollment.total_fee):
        payment_type = "Full course payment"
    elif len(installment_numbers) == 1:
        payment_type = f"Installment {installment_numbers[0]} of {installment_count}"
    elif installment_numbers:
        payment_type = "Installments " + ", ".join(
            str(number) for number in installment_numbers
        )
    else:
        payment_type = "Course payment"

    receipt_date = max(row.payment_date for row in payment_rows)
    payment_record_id = min(row.id for row in payment_rows)
    receipt_id = BRANCH_RECEIPT_ID_OFFSET + payment_record_id
    razorpay_payment_id = (
        payment_order.razorpay_payment_id
        if payment_order
        else payment.payment_reference
        if payment_method == "razorpay"
        else ""
    )
    razorpay_order_id = (
        payment_order.razorpay_order_id
        if payment_order
        else ""
    )
    if payment_method == "razorpay":
        if any(row.status == "pending_review" for row in payment_rows):
            receipt_status = "Verified - Pending branch review"
        elif any(row.status == "rejected" for row in payment_rows):
            receipt_status = "Verified - Rejected by branch"
        else:
            receipt_status = "Verified"
    else:
        receipt_status = "Received"
    receipt_number = (
        f"AFX-{receipt_date.strftime('%Y%m%d')}-{payment_record_id:06d}"
    )

    return {
        "receipt_id": receipt_id,
        "receipt_number": receipt_number,
        "academy_name": "AurumFX Academy",
        "branch_id": payment.branch_id,
        "branch_name": branch_name,
        "student_id": enrollment.user_id,
        "student_name": enrollment.name or student.name,
        "student_email": enrollment.email or student.email,
        "student_phone": enrollment.phone or student.phone,
        "course_id": course.id,
        "course_name": enrollment.course_title or course.title,
        "enrollment_id": enrollment.id,
        "payment_type": payment_type,
        "installment_numbers": installment_numbers,
        "installment_count": installment_count,
        "amount_paid": receipt_amount,
        "currency": "INR",
        "payment_method": method_labels.get(payment_method, payment_method),
        "transaction_reference": (
            payment.payment_reference
            or f"PAY-{receipt_id:06d}"
        ),
        "cash_amount": cash_amount,
        "upi_amount": upi_amount,
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "payment_date": receipt_date.isoformat(),
        "payment_status": receipt_status,
        "course_fee": round(float(enrollment.total_fee), 2),
        "total_paid": round(float(enrollment.total_paid or 0), 2),
        "balance_amount": round(float(enrollment.balance_amount or 0), 2),
        "quote": "Every step forward is progress worth celebrating.",
    }


def list_receipts(
    db: Session,
    branch_id: int,
    from_date: date | None,
    to_date: date | None,
    user_id: int | None = None,
    include_razorpay: bool = True,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date must be on or before to_date",
        )
    rows = payment_query(
        db,
        branch_id,
        from_date,
        to_date,
        user_id,
        include_razorpay,
    ).all()
    receipt_groups = group_receipt_payments(rows)
    receipts = [
        build_branch_receipt(group)
        for group in receipt_groups.values()
    ]
    receipts.sort(
        key=lambda receipt: (receipt["payment_date"], receipt["receipt_id"]),
        reverse=True,
    )
    return receipts


@router.get("")
def get_branch_receipts(
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_branch_admin(current_user)
    receipts = list_receipts(db, branch_id, from_date, to_date)
    for receipt in receipts:
        receipt["receipt_url"] = f"/branch-admin/receipts/{receipt['receipt_id']}"
        receipt["download_url"] = (
            f"/branch-admin/receipts/{receipt['receipt_id']}/download"
        )
    return {
        "branch_id": branch_id,
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "total_receipts": len(receipts),
        "receipts": receipts,
    }


def get_receipt(
    db: Session,
    branch_id: int,
    receipt_id: int,
    user_id: int | None = None,
):
    rows = payment_query(db, branch_id, user_id=user_id).all()
    for group in group_receipt_payments(rows).values():
        if (
            BRANCH_RECEIPT_ID_OFFSET + min(row[0].id for row in group)
            == receipt_id
        ):
            return build_branch_receipt(group)
    raise HTTPException(status_code=404, detail="Receipt not found")


@router.get("/{receipt_id}")
def view_branch_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_branch_admin(current_user)
    receipt = get_receipt(db, branch_id, receipt_id)
    return HTMLResponse(content=render_receipt_html(receipt))


@router.get("/{receipt_id}/download")
def download_branch_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = require_branch_admin(current_user)
    receipt = get_receipt(db, branch_id, receipt_id)
    return HTMLResponse(
        content=render_receipt_html(receipt),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{receipt["receipt_number"]}.html"'
            )
        },
    )
