from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal

from database_models import (
    User,
    BranchAdminAttendance
)

from routers.auth import get_current_user

from schemas.branch_admin_attendance import (
    BranchAdminAttendanceCreate,
    BranchAdminAttendanceUpdate
)


router = APIRouter(
    prefix="/branch-admin-attendance"
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# =========================================================
# ATTENDANCE STATUS HELPER
# =========================================================

def normalize_attendance_status(status: str):

    status_map = {
        "present": "Present",
        "absent": "Absent",
        "half day": "Half Day",
        "leave": "Leave"
    }

    normalized_status = status.strip().lower()

    if normalized_status not in status_map:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid attendance status. "
                "Allowed values: Present, Absent, Half Day, Leave"
            )
        )

    return status_map[normalized_status]


# =========================================================
# BRANCH ADMIN - MARK OWN ATTENDANCE
# =========================================================

@router.post(
    "/mark",
    tags=["Branch Admin - Own Attendance"]
)
def mark_own_attendance(
    attendance_data: BranchAdminAttendanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Only branch admin can use this API
    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    # Branch admin must belong to a branch
    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    # Normalize status
    status = normalize_attendance_status(
        attendance_data.status
    )

    # Check duplicate attendance
    existing_attendance = (
        db.query(BranchAdminAttendance)
        .filter(
            BranchAdminAttendance.branch_admin_id
            == current_user.id,

            BranchAdminAttendance.date
            == attendance_data.date
        )
        .first()
    )

    if existing_attendance:
        raise HTTPException(
            status_code=400,
            detail="Attendance already marked for this date"
        )

    # Create attendance
    attendance = BranchAdminAttendance(
        branch_admin_id=current_user.id,
        branch_id=current_user.branch_id,
        date=attendance_data.date,
        status=status
    )

    db.add(attendance)
    db.commit()
    db.refresh(attendance)

    return {
        "message": "Attendance marked successfully",

        "attendance": {
            "id": attendance.id,
            "branch_admin_id": attendance.branch_admin_id,
            "branch_id": attendance.branch_id,
            "date": attendance.date,
            "status": attendance.status,
            "marked_at": attendance.marked_at
        }
    }


# =========================================================
# BRANCH ADMIN - GET OWN ATTENDANCE
# =========================================================
@router.get(
    "/my",
    tags=["Branch Admin - Own Attendance"]
)
def get_my_attendance(
    attendance_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    query = (
        db.query(BranchAdminAttendance)
        .filter(
            BranchAdminAttendance.branch_admin_id
            == current_user.id
        )
    )

    # Optional date filter
    if attendance_date is not None:
        query = query.filter(
            BranchAdminAttendance.date == attendance_date
        )

    records = (
        query
        .order_by(
            BranchAdminAttendance.date.desc()
        )
        .all()
    )

    # =====================================================
    # ATTENDANCE COUNTS
    # =====================================================

    present_count = sum(
        1
        for attendance in records
        if attendance.status.lower() == "present"
    )

    absent_count = sum(
        1
        for attendance in records
        if attendance.status.lower() == "absent"
    )

    half_day_count = sum(
        1
        for attendance in records
        if attendance.status.lower() == "half day"
    )

    leave_count = sum(
        1
        for attendance in records
        if attendance.status.lower() == "leave"
    )

    return {
        "date": (
            attendance_date.isoformat()
            if attendance_date
            else None
        ),

        "total": len(records),

        "present": present_count,

        "absent": absent_count,

        "half_day": half_day_count,

        "leave": leave_count,

        "attendance": [
            {
                "id": attendance.id,
                "branch_admin_id": attendance.branch_admin_id,
                "branch_id": attendance.branch_id,
                "date": attendance.date,
                "status": attendance.status,
                "marked_at": attendance.marked_at
            }
            for attendance in records
        ]
    }

# =========================================================
# BRANCH ADMIN - UPDATE OWN ATTENDANCE
# =========================================================

@router.put(
    "/{attendance_id}",
    tags=["Branch Admin - Own Attendance"]
)
def update_own_attendance(
    attendance_id: int,
    attendance_data: BranchAdminAttendanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Only branch admin
    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    # Find ONLY the logged-in admin's attendance
    attendance = (
        db.query(BranchAdminAttendance)
        .filter(
            BranchAdminAttendance.id == attendance_id,

            BranchAdminAttendance.branch_admin_id
            == current_user.id,

            BranchAdminAttendance.branch_id
            == current_user.branch_id
        )
        .first()
    )

    if not attendance:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found"
        )

    # Normalize status
    status = normalize_attendance_status(
        attendance_data.status
    )

    # Update
    attendance.status = status

    db.commit()
    db.refresh(attendance)

    return {
        "message": "Attendance updated successfully",

        "attendance": {
            "id": attendance.id,
            "branch_admin_id": attendance.branch_admin_id,
            "branch_id": attendance.branch_id,
            "date": attendance.date,
            "status": attendance.status,
            "marked_at": attendance.marked_at
        }
    }