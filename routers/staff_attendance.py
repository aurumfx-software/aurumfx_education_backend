from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal

from database_models import (
    User,
    Staff,
    StaffAttendance
)

from routers.auth import get_current_user

from schemas.staff_attendance import (
    StaffAttendanceCreate,
    StaffAttendanceUpdate
)


router = APIRouter(
    prefix="/staff-attendance"
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
    """
    Accepts any letter case and converts it
    to the standard attendance status.
    """

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
# BRANCH ADMIN - MARK ATTENDANCE
# =========================================================

@router.post(
    "/mark",
    tags=["Branch Admin - Staff Attendance"]
)
def mark_staff_attendance(
    attendance_data: StaffAttendanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only branch admin can mark attendance
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

    # Check staff belongs to this branch
    staff = (
        db.query(Staff)
        .filter(
            Staff.id == attendance_data.staff_id,
            Staff.branch_id == current_user.branch_id,
            Staff.status == "Active"
        )
        .first()
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Active staff not found in your branch"
        )

    # Normalize attendance status
    status = normalize_attendance_status(
        attendance_data.status
    )

    # Check if attendance already exists
    existing_attendance = (
        db.query(StaffAttendance)
        .filter(
            StaffAttendance.staff_id == staff.id,
            StaffAttendance.date == attendance_data.date
        )
        .first()
    )

    if existing_attendance:
        raise HTTPException(
            status_code=400,
            detail="Attendance already marked for this staff on this date"
        )

    # Create attendance
    attendance = StaffAttendance(
        staff_id=staff.id,
        branch_id=current_user.branch_id,
        date=attendance_data.date,
        status=status,
        marked_by=current_user.id
    )

    db.add(attendance)
    db.commit()
    db.refresh(attendance)

    return {
        "message": "Attendance marked successfully",
        "attendance": {
            "id": attendance.id,
            "staff_id": attendance.staff_id,
            "staff_name": staff.name,
            "branch_id": attendance.branch_id,
            "date": attendance.date,
            "status": attendance.status,
            "marked_by": attendance.marked_by,
            "marked_at": attendance.marked_at
        }
    }


# =========================================================
# BRANCH ADMIN - GET ATTENDANCE
# =========================================================

@router.get(
    "",
    tags=["Branch Admin - Staff Attendance"]
)
def get_staff_attendance(
    staff_id: int | None = Query(default=None),
    attendance_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only branch admin can view all branch attendance
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

    # Get only active staff from current branch
    query = (
        db.query(StaffAttendance, Staff)
        .join(
            Staff,
            Staff.id == StaffAttendance.staff_id
        )
        .filter(
            StaffAttendance.branch_id == current_user.branch_id,
            Staff.status == "Active"
        )
    )

    # Optional staff filter
    if staff_id is not None:
        query = query.filter(
            StaffAttendance.staff_id == staff_id
        )

    # Optional date filter
    if attendance_date is not None:
        query = query.filter(
            StaffAttendance.date == attendance_date
        )

    records = (
        query
        .order_by(
            StaffAttendance.date.desc()
        )
        .all()
    )

    return {
        "total": len(records),
        "attendance": [
            {
                "id": attendance.id,
                "staff_id": attendance.staff_id,
                "staff_name": staff.name,
                "branch_id": attendance.branch_id,
                "date": attendance.date,
                "status": attendance.status,
                "marked_by": attendance.marked_by,
                "marked_at": attendance.marked_at
            }
            for attendance, staff in records
        ]
    }


# =========================================================
# STAFF - GET OWN ATTENDANCE ONLY
# =========================================================

@router.get(
    "/my",
    tags=["Staff - My Attendance"]
)
def get_my_attendance(
    attendance_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only staff can access this endpoint
    if current_user.role != "staff":
        raise HTTPException(
            status_code=403,
            detail="Staff access required"
        )

    # Find logged-in staff
    staff = (
        db.query(Staff)
        .filter(
            Staff.user_id == current_user.id,
            Staff.status == "Active"
        )
        .first()
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Active staff profile not found"
        )

    # Get only this staff's attendance
    query = (
        db.query(StaffAttendance)
        .filter(
            StaffAttendance.staff_id == staff.id
        )
    )

    # Optional date filter
    if attendance_date is not None:
        query = query.filter(
            StaffAttendance.date == attendance_date
        )

    records = (
        query
        .order_by(
            StaffAttendance.date.desc()
        )
        .all()
    )

    return {
        "total": len(records),
        "attendance": [
            {
                "id": attendance.id,
                "staff_id": attendance.staff_id,
                "date": attendance.date,
                "status": attendance.status,
                "marked_by": attendance.marked_by,
                "marked_at": attendance.marked_at
            }
            for attendance in records
        ]
    }


# =========================================================
# BRANCH ADMIN - UPDATE ATTENDANCE
# =========================================================

@router.put(
    "/{attendance_id}",
    tags=["Branch Admin - Staff Attendance"]
)
def update_staff_attendance(
    attendance_id: int,
    attendance_data: StaffAttendanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only branch admin can edit attendance
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

    # Get attendance record
    attendance = (
        db.query(StaffAttendance)
        .filter(
            StaffAttendance.id == attendance_id,
            StaffAttendance.branch_id == current_user.branch_id
        )
        .first()
    )

    if not attendance:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found"
        )

    # Get staff to return staff name
    staff = (
        db.query(Staff)
        .filter(
            Staff.id == attendance.staff_id,
            Staff.branch_id == current_user.branch_id
        )
        .first()
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Staff not found in your branch"
        )

    # Normalize attendance status
    status = normalize_attendance_status(
        attendance_data.status
    )

    # Update attendance
    attendance.status = status
    attendance.marked_by = current_user.id

    db.commit()
    db.refresh(attendance)

    return {
        "message": "Attendance updated successfully",
        "attendance": {
            "id": attendance.id,
            "staff_id": attendance.staff_id,
            "staff_name": staff.name,
            "branch_id": attendance.branch_id,
            "date": attendance.date,
            "status": attendance.status,
            "marked_by": attendance.marked_by,
            "marked_at": attendance.marked_at
        }
    }