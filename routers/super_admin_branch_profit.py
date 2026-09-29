from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, User
from routers.auth import get_current_super_admin
from routers.branch_profit import (
    enrollment_to_dict,
    get_paid_enrollment_records,
)


router = APIRouter(
    prefix="/super-admin/profit",
    tags=["Super Admin Branch Profit"],
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


def build_profit_response(db: Session, branch_id: int, payment_date: date_type):
    enrollment_records = get_paid_enrollment_records(
        db=db,
        branch_id=branch_id,
        payment_date=payment_date,
    )
    total_profit = sum(
        amount_paid_on_date
        for enrollment, course, amount_paid_on_date in enrollment_records
    )
    return {
        "branch_id": branch_id,
        "date": payment_date.isoformat(),
        "total_profit": float(total_profit),
        "total_enrollments": len(enrollment_records),
        "enrollments": [
            enrollment_to_dict(
                db,
                enrollment,
                course,
                amount_paid_on_date,
            )
            for enrollment, course, amount_paid_on_date in enrollment_records
        ],
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


@router.get("/branches/{branch_id}")
def get_branch_profit(
    branch_id: int,
    payment_date: date_type | None = Query(
        default=None,
        alias="date",
        description="Date to report, in YYYY-MM-DD format. Defaults to today.",
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    selected_date = payment_date or date_type.today()
    return build_profit_response(db, branch_id, selected_date)


@router.get("/branches/{branch_id}/today-profit")
def get_branch_today_profit(
    branch_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    today = date_type.today()
    result = build_profit_response(db, branch_id, today)
    return {
        "branch_id": result["branch_id"],
        "date": result["date"],
        "today_profit": result["total_profit"],
        "total_enrollments": result["total_enrollments"],
        "enrollments": result["enrollments"],
    }
