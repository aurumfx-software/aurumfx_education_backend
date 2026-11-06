from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import BranchHoliday, User
from routers.auth import get_current_user
from schemas.branch_holiday import BranchHolidayCreate
from utils.attendance_history import holiday_summary, resolve_period


router = APIRouter(prefix="/holidays", tags=["Branch Holidays"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_holiday(holiday: BranchHoliday):
    return {
        "id": holiday.id,
        "branch_id": holiday.branch_id,
        "date": holiday.date,
        "reason": holiday.reason,
        "marked_by": holiday.marked_by,
        "marked_at": holiday.marked_at,
    }


@router.post("")
def create_branch_holiday(
    holiday_data: BranchHolidayCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "branch_admin":
        raise HTTPException(status_code=403, detail="Branch admin access required")
    if not current_user.branch_id:
        raise HTTPException(status_code=400, detail="Branch admin is not assigned to a branch")
    reason = holiday_data.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Holiday reason is required")

    holiday = BranchHoliday(
        branch_id=current_user.branch_id,
        date=holiday_data.date,
        reason=reason,
        marked_by=current_user.id,
    )
    db.add(holiday)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A holiday already exists for this date")
    db.refresh(holiday)
    return {"message": "Holiday marked successfully", "holiday": serialize_holiday(holiday)}


@router.get("")
def get_branch_holidays(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    month: str | None = Query(default=None),
    branch_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "branch_admin":
        if not current_user.branch_id:
            raise HTTPException(status_code=400, detail="Branch admin is not assigned to a branch")
        requested_branch_id = current_user.branch_id
    elif current_user.role == "super_admin":
        requested_branch_id = branch_id
        if requested_branch_id is None:
            raise HTTPException(status_code=422, detail="branch_id is required for super admin")
    else:
        raise HTTPException(status_code=403, detail="Branch admin or super admin access required")

    date_from, date_to = resolve_period(date_from, date_to, month)

    query = db.query(BranchHoliday).filter(BranchHoliday.branch_id == requested_branch_id)
    if date_from:
        query = query.filter(BranchHoliday.date >= date_from)
    if date_to:
        query = query.filter(BranchHoliday.date <= date_to)
    holidays = query.order_by(BranchHoliday.date.asc()).all()
    if date_from and date_to:
        _, _, summary = holiday_summary(date_from, date_to, holidays)
        holidays_by_date = {holiday.date: holiday for holiday in holidays}
        holiday_details = []
        for detail in summary:
            holiday = holidays_by_date.get(detail["date"])
            if holiday:
                holiday_details.append({
                    **serialize_holiday(holiday),
                    "type": "special",
                })
            else:
                holiday_details.append({
                    "id": None,
                    "branch_id": requested_branch_id,
                    "date": detail["date"],
                    "reason": "Sunday",
                    "type": "sunday",
                    "marked_by": None,
                    "marked_at": None,
                })
    else:
        holiday_details = [
            {
                **serialize_holiday(holiday),
                "type": "special",
            }
            for holiday in holidays
        ]
    return {
        "branch_id": requested_branch_id,
        "total": len(holiday_details),
        "holidays": holiday_details,
    }
