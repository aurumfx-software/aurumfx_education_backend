from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    Branch,
    BranchAdminAttendance,
    Staff,
    StaffAttendance,
    User,
)
from routers.auth import get_current_super_admin


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


@router.get("/branches/{branch_id}/staff")
def get_branch_staff_attendance(
    branch_id: int,
    attendance_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branch = get_active_branch(db, branch_id)
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

    records = (
        query
        .order_by(StaffAttendance.date.desc(), Staff.name.asc())
        .all()
    )
    return {
        "branch_id": branch.id,
        "branch_name": branch.name,
        "date": attendance_date.isoformat() if attendance_date else None,
        **attendance_counts(records),
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
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branch = get_active_branch(db, branch_id)
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

    records = (
        query
        .order_by(BranchAdminAttendance.date.desc(), User.name.asc())
        .all()
    )
    return {
        "branch_id": branch.id,
        "branch_name": branch.name,
        "date": attendance_date.isoformat() if attendance_date else None,
        **attendance_counts(records),
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
