from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal

from database_models import (
    User,
    Staff,
    StaffAttendance,
    StaffAttendanceAdjustment,
    BranchHoliday,
)

from routers.auth import get_current_user

from schemas.staff_attendance import (
    StaffAttendanceCreate,
    StaffAttendanceUpdate
)
from utils.attendance_history import holiday_summary, resolve_period


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

    # =====================================================
    # CHECK STAFF
    # =====================================================

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

    # =====================================================
    # NORMALIZE STATUS
    # =====================================================

    status = normalize_attendance_status(
        attendance_data.status
    )

    # =====================================================
    # CHECK DUPLICATE ATTENDANCE
    # =====================================================

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

    # =====================================================
    # CREATE ATTENDANCE
    # =====================================================

    attendance = StaffAttendance(
        staff_id=staff.id,

        # IMPORTANT:
        # Save staff name in attendance table
        staff_name=staff.name,

        branch_id=current_user.branch_id,
        date=attendance_data.date,
        status=status,
        marked_by=current_user.id
    )

    db.add(attendance)
    db.commit()
    db.refresh(attendance)

    # =====================================================
    # RESPONSE
    # =====================================================

    return {
        "message": "Attendance marked successfully",

        "attendance": {
            "id": attendance.id,
            "staff_id": attendance.staff_id,
            "staff_name": attendance.staff_name,
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
    attendance_date: date | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    month: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only branch admin can view branch attendance
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

    period_from, period_to = resolve_period(date_from, date_to, month)
    if attendance_date and (period_from or period_to):
        raise HTTPException(status_code=400, detail="Use attendance_date or a date range, not both")

    # =====================================================
    # GET ONLY THIS BRANCH ATTENDANCE
    # =====================================================

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

    # =====================================================
    # OPTIONAL DATE FILTER
    # =====================================================

    if attendance_date is not None:
        query = query.filter(
            StaffAttendance.date == attendance_date
        )
    if period_from:
        query = query.filter(StaffAttendance.date >= period_from)
    if period_to:
        query = query.filter(StaffAttendance.date <= period_to)

    if period_from and period_to:
        holidays = (
            db.query(BranchHoliday)
            .filter(
                BranchHoliday.branch_id == current_user.branch_id,
                BranchHoliday.date >= period_from,
                BranchHoliday.date <= period_to,
            )
            .all()
        )
        total_holidays, total_working_days, holiday_details = holiday_summary(
            period_from, period_to, holidays
        )
    else:
        total_holidays = total_working_days = None
        holiday_details = []

    # =====================================================
    # GET RECORDS
    # =====================================================

    records = (
        query
        .order_by(
            StaffAttendance.date.desc(),
            Staff.name.asc()
        )
        .all()
    )

    # =====================================================
    # ATTENDANCE COUNTS
    # =====================================================

    present_count = sum(
        1
        for attendance, staff in records
        if attendance.status.lower() == "present"
    )

    absent_count = sum(
        1
        for attendance, staff in records
        if attendance.status.lower() == "absent"
    )

    half_day_count = sum(
        1
        for attendance, staff in records
        if attendance.status.lower() == "half day"
    )

    leave_count = sum(
        1
        for attendance, staff in records
        if attendance.status.lower() == "leave"
    )

    # =====================================================
    # RESPONSE
    # =====================================================

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
        "date_from": period_from,
        "date_to": period_to,
        "total_holidays": total_holidays,
        "total_working_days": total_working_days,
        "holidays": holiday_details,

        "attendance": [
            {
                "id": attendance.id,
                "staff_id": attendance.staff_id,

                # Stored name if available.
                # Fallback for old records where staff_name
                # was NULL.
                "staff_name": (
                    attendance.staff_name
                    if attendance.staff_name
                    else staff.name
                ),

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
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    month: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only staff can access this endpoint
    if current_user.role != "staff":
        raise HTTPException(
            status_code=403,
            detail="Staff access required"
        )

    period_from, period_to = resolve_period(date_from, date_to, month)
    if attendance_date and (period_from or period_to):
        raise HTTPException(status_code=400, detail="Use attendance_date or a date range, not both")

    # =====================================================
    # FIND LOGGED-IN STAFF
    # =====================================================

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

    # =====================================================
    # GET ONLY THIS STAFF'S ATTENDANCE
    # =====================================================

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
    if period_from:
        query = query.filter(StaffAttendance.date >= period_from)
    if period_to:
        query = query.filter(StaffAttendance.date <= period_to)

    records = (
        query
        .order_by(
            StaffAttendance.date.desc()
        )
        .all()
    )

    if period_from and period_to:
        holidays = (
            db.query(BranchHoliday)
            .filter(
                BranchHoliday.branch_id == staff.branch_id,
                BranchHoliday.date >= period_from,
                BranchHoliday.date <= period_to,
            )
            .all()
        )
        total_holidays, total_working_days, holiday_details = holiday_summary(
            period_from, period_to, holidays
        )
    else:
        total_holidays = total_working_days = None
        holiday_details = []

    present_count = sum(record.status.lower() == "present" for record in records)
    absent_count = sum(record.status.lower() == "absent" for record in records)
    half_day_count = sum(record.status.lower() == "half day" for record in records)

    return {
        "total": len(records),
        "present": present_count,
        "absent": absent_count,
        "half_day": half_day_count,
        "date_from": period_from,
        "date_to": period_to,
        "total_holidays": total_holidays,
        "total_working_days": total_working_days,
        "holidays": holiday_details,

        "attendance": [
            {
                "id": attendance.id,
                "staff_id": attendance.staff_id,

                # Fallback handles old rows where
                # staff_name was NULL.
                "staff_name": (
                    attendance.staff_name
                    if attendance.staff_name
                    else staff.name
                ),

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

    # =====================================================
    # GET ATTENDANCE
    # =====================================================

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

    # =====================================================
    # GET STAFF
    # =====================================================

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

    # =====================================================
    # NORMALIZE STATUS
    # =====================================================

    status = normalize_attendance_status(
        attendance_data.status
    )

    # =====================================================
    # UPDATE ATTENDANCE
    # =====================================================

    previous_status = attendance.status
    if previous_status != status:
        db.add(
            StaffAttendanceAdjustment(
                attendance_id=attendance.id,
                staff_id=attendance.staff_id,
                branch_id=attendance.branch_id,
                attendance_date=attendance.date,
                old_status=previous_status,
                new_status=status,
                changed_by=current_user.id,
            )
        )

    attendance.status = status

    # Update staff name as well.
    # This fixes old attendance rows that had NULL staff_name.
    attendance.staff_name = staff.name

    attendance.marked_by = current_user.id

    db.commit()
    db.refresh(attendance)

    # =====================================================
    # RESPONSE
    # =====================================================

    return {
        "message": "Attendance updated successfully",

        "attendance": {
            "id": attendance.id,
            "staff_id": attendance.staff_id,
            "staff_name": attendance.staff_name,
            "branch_id": attendance.branch_id,
            "date": attendance.date,
            "status": attendance.status,
            "marked_by": attendance.marked_by,
            "marked_at": attendance.marked_at
        }
    }