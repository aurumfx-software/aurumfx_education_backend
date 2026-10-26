from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, BranchExpense, User
from routers.auth import get_current_user
from schemas.expense import BranchExpenseCreate


router = APIRouter(
    prefix="/branch-admin/expenses",
    tags=["Branch Admin Expenses"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_branch_id(current_user: User) -> int:
    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required",
        )
    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch",
        )
    return current_user.branch_id


def get_date_range(
    from_date: date | None,
    to_date: date | None,
) -> tuple[date, date]:
    start_date = from_date or to_date or date.today()
    end_date = to_date or (date.today() if from_date else start_date)
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="from_date must be on or before to_date",
        )
    return start_date, end_date


def build_expense_report(
    db: Session,
    branch_id: int,
    from_date: date,
    to_date: date,
):
    records = (
        db.query(BranchExpense)
        .filter(
            BranchExpense.branch_id == branch_id,
            BranchExpense.expense_date >= from_date,
            BranchExpense.expense_date <= to_date,
        )
        .order_by(
            BranchExpense.expense_date.desc(),
            BranchExpense.id.desc(),
        )
        .all()
    )
    item_totals = {}
    for expense in records:
        item_totals[expense.item] = (
            item_totals.get(expense.item, 0.0) + float(expense.cost)
        )
    most_spent_item = None
    if item_totals:
        item, total = max(item_totals.items(), key=lambda pair: pair[1])
        most_spent_item = {"item": item, "total_cost": round(total, 2)}

    return {
        "branch_id": branch_id,
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "total_cost": round(sum(float(row.cost) for row in records), 2),
        "expense_count": len(records),
        "most_spent_item": most_spent_item,
        "expenses": [
            expense_to_dict(expense)
            for expense in records
        ],
    }


def expense_to_dict(expense: BranchExpense) -> dict:
    return {
        "expense_id": expense.id,
        "branch_id": expense.branch_id,
        "item": expense.item,
        "cost": float(expense.cost),
        "expense_date": expense.expense_date.isoformat(),
        "created_by_user_id": expense.created_by_user_id,
        "created_at": expense.created_at,
    }


@router.post("")
def create_branch_expense(
    data: BranchExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = get_branch_id(current_user)
    branch_exists = (
        db.query(Branch.id)
        .filter(Branch.id == branch_id)
        .first()
    )
    if not branch_exists:
        raise HTTPException(status_code=404, detail="Assigned branch not found")

    expense = BranchExpense(
        branch_id=branch_id,
        item=data.item,
        cost=round(data.cost, 2),
        expense_date=date.today(),
        created_by_user_id=current_user.id,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return {
        "message": "Expense recorded successfully",
        "expense": {
            "expense_id": expense.id,
            "branch_id": expense.branch_id,
            "item": expense.item,
            "cost": float(expense.cost),
            "expense_date": expense.expense_date.isoformat(),
            "created_by_user_id": expense.created_by_user_id,
            "created_at": expense.created_at,
        },
    }


@router.get("")
def get_branch_expenses(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    branch_id = get_branch_id(current_user)
    start_date, end_date = get_date_range(from_date, to_date)
    report = build_expense_report(db, branch_id, start_date, end_date)
    most_expense = max(
        report["expenses"],
        key=lambda expense: expense["cost"],
        default=None,
    )
    report["most_expensive_expense"] = most_expense
    return report
