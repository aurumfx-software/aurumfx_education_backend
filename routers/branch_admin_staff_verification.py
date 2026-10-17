from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Staff, User
from routers.auth import get_current_user
from routers.staff_portal import (
    build_staff_profile,
    build_staff_verification_reviewers,
    require_documents_complete,
)
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


def get_branch_staff_by_verification_status(
    verification_status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_branch_admin(current_user)

    query = db.query(Staff).filter(
        Staff.branch_id == current_user.branch_id,
        Staff.status == "Active",
        Staff.verification_submitted_at.isnot(None),
        Staff.verification_status == verification_status,
    )

    staff_members = query.order_by(Staff.created_at.desc(), Staff.id.desc()).all()
    staff_profiles = []
    for staff in staff_members:
        profile = build_staff_profile(db, staff)
        if verification_status in {"approved", "rejected"}:
            profile.update(build_staff_verification_reviewers(db, staff))
        staff_profiles.append(profile)

    return {
        "branch_id": current_user.branch_id,
        "verification_status": verification_status,
        "document_status": verification_status,
        "total_staff": len(staff_members),
        "pending_staff": len(staff_members) if verification_status == "pending" else 0,
        "staff": staff_profiles,
    }


@router.get("")
@router.get("/pending")
def get_pending_branch_staff_verification(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_branch_staff_by_verification_status(
        "pending",
        db=db,
        current_user=current_user,
    )


@router.get("/approved")
def get_approved_branch_staff_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_branch_staff_by_verification_status(
        "approved",
        db=db,
        current_user=current_user,
    )


@router.get("/rejected")
def get_rejected_branch_staff_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_branch_staff_by_verification_status(
        "rejected",
        db=db,
        current_user=current_user,
    )


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
    if staff.verification_submitted_at is None:
        raise HTTPException(
            status_code=409,
            detail="Staff documents have not been submitted",
        )

    require_documents_complete(staff)
    staff.verification_status = "approved"
    staff.verification_approved_at = datetime.now(timezone.utc)
    staff.verification_approved_by_user_id = current_user.id
    staff.verification_rejection_reason = None
    staff.verification_rejected_at = None
    staff.verification_rejected_by_user_id = None
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
    staff.verification_rejected_by_user_id = current_user.id
    staff.verification_approved_at = None
    staff.verification_approved_by_user_id = None
    db.commit()
    db.refresh(staff)
    return {
        "message": "Staff documents rejected",
        "staff": build_staff_profile(db, staff),
    }
