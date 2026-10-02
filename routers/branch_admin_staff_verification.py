from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Staff, User
from routers.auth import get_current_user
from routers.staff_portal import build_staff_profile, require_documents_complete
from schemas.staff import StaffVerificationReject


router = APIRouter(
    prefix="/branch-admin/staff-verification",
    tags=["Branch Admin Staff Verification"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_branch_admin(current_user: User):
    if current_user.role != "branch_admin":
        raise HTTPException(status_code=403, detail="Branch admin access required")
    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch",
        )


@router.get("")
def get_branch_staff_for_verification(
    verification_status: str = Query(default="pending"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_branch_admin(current_user)
    if verification_status not in {"pending", "approved", "rejected", "all"}:
        raise HTTPException(
            status_code=400,
            detail="verification_status must be pending, approved, rejected, or all",
        )

    query = db.query(Staff).filter(
        Staff.branch_id == current_user.branch_id,
        Staff.status == "Active",
    )
    if verification_status != "all":
        query = query.filter(Staff.verification_status == verification_status)

    staff_members = query.order_by(Staff.created_at.desc(), Staff.id.desc()).all()
    return {
        "branch_id": current_user.branch_id,
        "verification_status": verification_status,
        "total_staff": len(staff_members),
        "pending_staff": sum(
            staff.verification_status == "pending" for staff in staff_members
        ),
        "staff": [build_staff_profile(db, staff) for staff in staff_members],
    }


@router.put("/{staff_id}/approve")
def approve_staff_documents(
    staff_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_branch_admin(current_user)
    staff = (
        db.query(Staff)
        .filter(
            Staff.id == staff_id,
            Staff.branch_id == current_user.branch_id,
            Staff.status == "Active",
        )
        .first()
    )
    if not staff:
        raise HTTPException(status_code=404, detail="Active staff not found in your branch")
    if staff.verification_status == "approved":
        raise HTTPException(status_code=400, detail="Staff documents are already approved")

    if staff.verification_status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only pending staff submissions can be approved",
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
    current_user: User = Depends(get_current_user),
):
    require_branch_admin(current_user)
    staff = (
        db.query(Staff)
        .filter(
            Staff.id == staff_id,
            Staff.branch_id == current_user.branch_id,
            Staff.status == "Active",
        )
        .first()
    )
    if not staff:
        raise HTTPException(status_code=404, detail="Active staff not found in your branch")
    if staff.verification_status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only pending staff submissions can be rejected",
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
