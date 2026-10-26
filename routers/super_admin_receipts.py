from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    Branch,
    Enrollment,
    RazorpayPaymentOrder,
    User,
)
from routers.auth import get_current_super_admin
from routers.branch_receipts import (
    BRANCH_RECEIPT_ID_OFFSET,
    build_branch_receipt,
    group_receipt_payments,
    payment_query,
)
from routers.payments import build_student_receipt, render_receipt_html


router = APIRouter(
    prefix="/super-admin/receipts",
    tags=["Super Admin Payment Receipts"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_receipts(
    db: Session,
    branch_id: int | None,
    from_date: date | None,
    to_date: date | None,
    student_name: str | None,
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=400,
            detail="from_date must be on or before to_date",
        )

    query = payment_query(
        db,
        branch_id=branch_id,
        from_date=from_date,
        to_date=to_date,
    )
    if student_name:
        search_text = (
            student_name.strip()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        if search_text:
            search_pattern = f"%{search_text}%"
            query = query.filter(
                or_(
                    Enrollment.name.ilike(search_pattern, escape="\\"),
                    User.name.ilike(search_pattern, escape="\\"),
                )
            )

    rows = query.all()
    grouped = group_receipt_payments(rows)
    receipts = [
        build_branch_receipt(group)
        for group in grouped.values()
    ]
    receipts.sort(
        key=lambda receipt: (
            receipt["payment_date"],
            receipt["receipt_id"],
        ),
        reverse=True,
    )
    return receipts


@router.get("")
def list_super_admin_receipts(
    branch_id: int | None = Query(default=None, gt=0),
    student_name: str | None = Query(default=None, min_length=1, max_length=255),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branch_name = None
    if branch_id is not None:
        branch = db.query(Branch).filter(Branch.id == branch_id).first()
        if not branch:
            raise HTTPException(status_code=404, detail="Branch not found")
        branch_name = branch.name

    receipts = get_receipts(
        db,
        branch_id,
        from_date,
        to_date,
        student_name,
    )
    for receipt in receipts:
        receipt["receipt_url"] = f"/super-admin/receipts/{receipt['receipt_id']}"
        receipt["download_url"] = (
            f"/super-admin/receipts/{receipt['receipt_id']}/download"
        )
    return {
        "branch_id": branch_id,
        "branch_name": branch_name,
        "student_name_filter": student_name,
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "total_receipts": len(receipts),
        "offset": offset,
        "limit": limit,
        "receipts": receipts[offset : offset + limit],
    }


def get_super_admin_receipt(db: Session, receipt_id: int):
    if receipt_id >= BRANCH_RECEIPT_ID_OFFSET:
        rows = payment_query(db, branch_id=None).all()
        for group in group_receipt_payments(rows).values():
            if (
                BRANCH_RECEIPT_ID_OFFSET + min(row[0].id for row in group)
                == receipt_id
            ):
                return build_branch_receipt(group)
    else:
        payment_order_record = (
            db.query(RazorpayPaymentOrder, Enrollment)
            .join(
                Enrollment,
                Enrollment.id == RazorpayPaymentOrder.enrollment_id,
            )
            .filter(
                RazorpayPaymentOrder.id == receipt_id,
                RazorpayPaymentOrder.status == "paid",
                RazorpayPaymentOrder.razorpay_payment_id.isnot(None),
            )
            .first()
        )
        if payment_order_record:
            payment_order, enrollment = payment_order_record
            branch = (
                db.query(Branch)
                .filter(Branch.id == enrollment.branch_id)
                .first()
            )
            receipt = build_student_receipt(db, enrollment, payment_order)
            receipt["branch_id"] = enrollment.branch_id
            receipt["branch_name"] = branch.name if branch else ""
            return receipt
    raise HTTPException(status_code=404, detail="Receipt not found")


@router.get("/{receipt_id}")
def view_super_admin_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    receipt = get_super_admin_receipt(db, receipt_id)
    return HTMLResponse(content=render_receipt_html(receipt))


@router.get("/{receipt_id}/download")
def download_super_admin_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    receipt = get_super_admin_receipt(db, receipt_id)
    return HTMLResponse(
        content=render_receipt_html(receipt),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{receipt["receipt_number"]}.html"'
            )
        },
    )
