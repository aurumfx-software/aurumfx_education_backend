from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import BranchHoliday, User
from routers.auth import get_current_user
from schemas.branch_holiday import BranchHolidayCreate


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

    if month and (date_from or date_to):
        raise HTTPException(status_code=400, detail="Use month or date_from/date_to, not both")
    if month:
        try:
            year, month_number = (int(value) for value in month.split("-", 1))
            date_from = date(year, month_number, 1)
            date_to = date(year, month_number + 1, 1) if month_number < 12 else date(year + 1, 1, 1)
            date_to = date.fromordinal(date_to.toordinal() - 1)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="month must use YYYY-MM format")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to")

    query = db.query(BranchHoliday).filter(BranchHoliday.branch_id == requested_branch_id)
    if date_from:
        query = query.filter(BranchHoliday.date >= date_from)
    if date_to:
        query = query.filter(BranchHoliday.date <= date_to)
    holidays = query.order_by(BranchHoliday.date.asc()).all()
    return {
        "branch_id": requested_branch_id,
        "total": len(holidays),
        "holidays": [serialize_holiday(holiday) for holiday in holidays],
    }
