from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, Staff, User
from routers.auth import get_current_super_admin
from routers.staff_portal import build_staff_profile, require_documents_complete
from schemas.staff import StaffVerificationReject


router = APIRouter(
    prefix="/super-admin/staff-verification",
    tags=["Super Admin Staff Verification"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_staff_by_verification_status(verification_status: str, db: Session):
    staff_members = (
        db.query(Staff)
        .filter(
            Staff.status == "Active",
            Staff.verification_submitted_at.isnot(None),
            Staff.verification_status == verification_status,
        )
        .order_by(Staff.created_at.desc(), Staff.id.desc())
        .all()
    )
    return {
        "verification_status": verification_status,
        "document_status": verification_status,
        "total_staff": len(staff_members),
        "pending_staff": len(staff_members) if verification_status == "pending" else 0,
        "staff": [build_staff_profile(db, staff) for staff in staff_members],
    }


@router.get("")
@router.get("/pending")
def get_pending_staff_verification(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    return get_staff_by_verification_status("pending", db)


@router.get("/approved")
def get_approved_staff_documents(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    return get_staff_by_verification_status("approved", db)


@router.get("/rejected")
def get_rejected_staff_documents(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    return get_staff_by_verification_status("rejected", db)


def get_active_staff(db: Session, staff_id: int) -> Staff:
    staff = (
        db.query(Staff)
        .filter(Staff.id == staff_id, Staff.status == "Active")
        .first()
    )
    if not staff:
        raise HTTPException(status_code=404, detail="Active staff not found")
    if not db.query(Branch.id).filter(Branch.id == staff.branch_id).first():
        raise HTTPException(status_code=404, detail="Staff branch not found")
    return staff


@router.put("/{staff_id}/approve")
def approve_staff_documents(
    staff_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    staff = get_active_staff(db, staff_id)
    if staff.verification_status == "approved":
        raise HTTPException(status_code=400, detail="Staff documents are already approved")
    if staff.verification_status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only pending staff submissions can be approved",
        )
    if staff.verification_submitted_at is None:
        raise HTTPException(
            status_code=409,
            detail="Staff documents have not been submitted",
        )

    require_documents_complete(staff)
    staff.verification_status = "approved"
    staff.verification_approved_at = datetime.now(timezone.utc)
    staff.verification_rejection_reason = None
    staff.verification_rejected_at = None
    db.commit()
    db.refresh(staff)
    return {
        "message": "Staff documents approved",
        "staff": build_staff_profile(db, staff),
    }


@router.put("/{staff_id}/reject")
def reject_staff_documents(
    staff_id: int,
    rejection_data: StaffVerificationReject,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    staff = get_active_staff(db, staff_id)
    if staff.verification_status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only pending staff submissions can be rejected",
        )
    if staff.verification_submitted_at is None:
        raise HTTPException(
            status_code=409,
            detail="Staff documents have not been submitted",
        )

    reason = rejection_data.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required")

    staff.verification_status = "rejected"
    staff.verification_rejection_reason = reason
    staff.verification_rejected_at = datetime.now(timezone.utc)
    staff.verification_approved_at = None
    db.commit()
    db.refresh(staff)
    return {
        "message": "Staff documents rejected",
        "staff": build_staff_profile(db, staff),
    }
