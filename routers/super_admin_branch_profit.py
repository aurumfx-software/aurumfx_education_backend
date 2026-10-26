from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, User
from routers.auth import get_current_super_admin
from routers.branch_profit import build_profit_response


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
    from_date: date_type | None = Query(
        default=None,
        description="Start date for the report, in YYYY-MM-DD format.",
    ),
    to_date: date_type | None = Query(
        default=None,
        description="End date for the report, in YYYY-MM-DD format.",
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    start_date = from_date or payment_date or to_date or date_type.today()
    end_date = to_date or (date_type.today() if from_date else start_date)
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="from_date must be on or before to_date",
        )
    return build_profit_response(
        db,
        branch_id,
        start_date,
        end_date,
    )


@router.get("/branches/{branch_id}/today-profit")
def get_branch_today_profit(
    branch_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    get_active_branch(db, branch_id)
    today = date_type.today()
    result = build_profit_response(db, branch_id, today, today)
    return {
        "branch_id": result["branch_id"],
        "date": result["date"],
        "today_profit": result["total_profit"],
        "total_enrollments": result["total_enrollments"],
        "enrollments": result["enrollments"],
        "payments": result["payments"],
        "total_received": result["total_received"],
        "total_enrolled_students": result["total_enrolled_students"],
        "cash_credited": result["cash_credited"],
        "cash_received": result["cash_received"],
        "upi_credited": result["upi_credited"],
        "upi_received": result["upi_received"],
        "razorpay_credited": result["razorpay_credited"],
        "razorpay_received": result["razorpay_received"],
        "due_student_count": result["due_student_count"],
        "due_student_amount": result["due_student_amount"],
    }
