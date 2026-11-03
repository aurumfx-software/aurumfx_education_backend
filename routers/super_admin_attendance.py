from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    Branch,
    BranchAdminAttendance,
    Staff,
    StaffAttendance,
    StaffAttendanceAdjustment,
    BranchHoliday,
    User,
)
from routers.auth import get_current_super_admin
from utils.attendance_history import holiday_summary, resolve_period


router = APIRouter(
    prefix="/super-admin/attendance",
    tags=["Super Admin Attendance"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_active_branch(db: Session, branch_id: int) -> Branch:
    branch = (
        db.query(Branch)
        .filter(Branch.id == branch_id)
        .first()
    )
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    if branch.status != "Active":
        raise HTTPException(status_code=400, detail="Branch is inactive")
    return branch


def attendance_counts(records):
    return {
        "total": len(records),
        "present": sum(record.status.lower() == "present" for record, *_ in records),
        "absent": sum(record.status.lower() == "absent" for record, *_ in records),
        "half_day": sum(record.status.lower() == "half day" for record, *_ in records),
        "leave": sum(record.status.lower() == "leave" for record, *_ in records),
    }


def display_timestamp(value):
    return value.strftime("%d %b %Y, %I:%M %p") if value else None


@router.get("/branches")
def get_active_branches(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branches = (
        db.query(Branch)
        .filter(Branch.status == "Active")
        .order_by(Branch.name.asc())
        .all()
    )
    return [
        {
            "branch_id": branch.id,
            "branch_name": branch.name,
            "location": branch.location,
        }
        for branch in branches
    ]


@router.get("/adjustments")
def get_staff_attendance_adjustments(
    branch_id: int | None = Query(default=None),
    staff_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    changed_from: datetime | None = Query(default=None),
    changed_to: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")
    if changed_from and changed_to and changed_from > changed_to:
        raise HTTPException(status_code=400, detail="changed_from must not be after changed_to")

    query = (
        db.query(StaffAttendanceAdjustment, Staff)
        .join(Staff, Staff.id == StaffAttendanceAdjustment.staff_id)
    )
    if branch_id is not None:
        query = query.filter(StaffAttendanceAdjustment.branch_id == branch_id)
    if staff_id is not None:
        query = query.filter(StaffAttendanceAdjustment.staff_id == staff_id)
    if date_from:
        query = query.filter(StaffAttendanceAdjustment.attendance_date >= date_from)
    if date_to:
        query = query.filter(StaffAttendanceAdjustment.attendance_date <= date_to)
    if changed_from:
        query = query.filter(StaffAttendanceAdjustment.changed_at >= changed_from)
    if changed_to:
        query = query.filter(StaffAttendanceAdjustment.changed_at <= changed_to)

    records = query.order_by(StaffAttendanceAdjustment.changed_at.desc()).all()
    return {
        "total": len(records),
        "adjustments": [
            {
                "id": adjustment.id,
                "attendance_id": adjustment.attendance_id,
                "staff_id": adjustment.staff_id,
                "staff_name": staff.name,
                "branch_id": adjustment.branch_id,
                "attendance_date": adjustment.attendance_date,
                "old_status": adjustment.old_status,
                "new_status": adjustment.new_status,
                "changed_by": adjustment.changed_by,
                "changed_at": adjustment.changed_at,
                "changed_at_display": display_timestamp(adjustment.changed_at),
            }
            for adjustment, staff in records
        ],
    }


@router.get("/branches/{branch_id}/staff")
def get_branch_staff_attendance(
    branch_id: int,
    attendance_date: date | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    month: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branch = get_active_branch(db, branch_id)
    period_from, period_to = resolve_period(date_from, date_to, month)
    if attendance_date and (period_from or period_to):
        raise HTTPException(status_code=400, detail="Use attendance_date or a date range, not both")
    query = (
        db.query(StaffAttendance, Staff)
        .join(Staff, Staff.id == StaffAttendance.staff_id)
        .filter(
            StaffAttendance.branch_id == branch_id,
            Staff.branch_id == branch_id,
            Staff.status == "Active",
        )
    )
    if attendance_date is not None:
        query = query.filter(StaffAttendance.date == attendance_date)
    if period_from:
        query = query.filter(StaffAttendance.date >= period_from)
    if period_to:
        query = query.filter(StaffAttendance.date <= period_to)

    records = (
        query
        .order_by(StaffAttendance.date.desc(), Staff.name.asc())
        .all()
    )
    if period_from and period_to:
        holidays = (
            db.query(BranchHoliday)
            .filter(
                BranchHoliday.branch_id == branch_id,
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

    return {
        "branch_id": branch.id,
        "branch_name": branch.name,
        "date": attendance_date.isoformat() if attendance_date else None,
        "date_from": period_from,
        "date_to": period_to,
        **attendance_counts(records),
        "total_holidays": total_holidays,
        "total_working_days": total_working_days,
        "holidays": holiday_details,
        "attendance": [
            {
                "id": attendance.id,
                "staff_id": attendance.staff_id,
                "staff_name": attendance.staff_name or staff.name,
                "branch_id": attendance.branch_id,
                "date": attendance.date,
                "status": attendance.status,
                "marked_by": attendance.marked_by,
                "marked_at": attendance.marked_at,
            }
            for attendance, staff in records
        ],
    }


@router.get("/branches/{branch_id}/branch-admins")
def get_branch_admin_attendance(
    branch_id: int,
    attendance_date: date | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    month: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branch = get_active_branch(db, branch_id)
    period_from, period_to = resolve_period(date_from, date_to, month)
    if attendance_date and (period_from or period_to):
        raise HTTPException(status_code=400, detail="Use attendance_date or a date range, not both")
    query = (
        db.query(BranchAdminAttendance, User)
        .join(User, User.id == BranchAdminAttendance.branch_admin_id)
        .filter(
            BranchAdminAttendance.branch_id == branch_id,
            User.branch_id == branch_id,
            User.role == "branch_admin",
        )
    )
    if attendance_date is not None:
        query = query.filter(BranchAdminAttendance.date == attendance_date)
    if period_from:
        query = query.filter(BranchAdminAttendance.date >= period_from)
    if period_to:
        query = query.filter(BranchAdminAttendance.date <= period_to)

    records = (
        query
        .order_by(BranchAdminAttendance.date.desc(), User.name.asc())
        .all()
    )
    if period_from and period_to:
        holidays = (
            db.query(BranchHoliday)
            .filter(
                BranchHoliday.branch_id == branch_id,
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

    return {
        "branch_id": branch.id,
        "branch_name": branch.name,
        "date": attendance_date.isoformat() if attendance_date else None,
        "date_from": period_from,
        "date_to": period_to,
        **attendance_counts(records),
        "total_holidays": total_holidays,
        "total_working_days": total_working_days,
        "holidays": holiday_details,
        "attendance": [
            {
                "id": attendance.id,
                "branch_admin_id": attendance.branch_admin_id,
                "branch_admin_name": branch_admin.name,
                "branch_admin_email": branch_admin.email,
                "branch_id": attendance.branch_id,
                "date": attendance.date,
                "status": attendance.status,
                "marked_at": attendance.marked_at,
            }
            for attendance, branch_admin in records
        ],
    }
