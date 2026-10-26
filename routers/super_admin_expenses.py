from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, BranchExpense, User
from routers.auth import get_current_super_admin
from routers.branch_expenses import expense_to_dict, get_date_range


router = APIRouter(
    prefix="/super-admin/expenses",
    tags=["Super Admin Expenses"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
def get_expenses_report(
    branch_id: int | None = Query(default=None, gt=0),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    start_date, end_date = get_date_range(from_date, to_date)
    selected_branch = None
    if branch_id is not None:
        selected_branch = db.query(Branch).filter(
            Branch.id == branch_id
        ).first()
        if not selected_branch:
            raise HTTPException(status_code=404, detail="Branch not found")

    all_expenses = (
        db.query(BranchExpense, Branch.name)
        .join(Branch, Branch.id == BranchExpense.branch_id)
        .filter(
            BranchExpense.expense_date >= start_date,
            BranchExpense.expense_date <= end_date,
        )
        .order_by(
            BranchExpense.expense_date.desc(),
            BranchExpense.id.desc(),
        )
        .all()
    )
    all_branch_totals = {}
    all_item_totals = {}
    for expense, branch_name in all_expenses:
        branch_total = all_branch_totals.setdefault(
            expense.branch_id,
            {
                "branch_id": expense.branch_id,
                "branch_name": branch_name,
                "total_cost": 0.0,
                "expense_count": 0,
                "item_totals": {},
            },
        )
        cost = float(expense.cost)
        branch_total["total_cost"] += cost
        branch_total["expense_count"] += 1
        branch_total["item_totals"][expense.item] = (
            branch_total["item_totals"].get(expense.item, 0.0) + cost
        )
        all_item_totals[expense.item] = (
            all_item_totals.get(expense.item, 0.0) + cost
        )

    branches = db.query(Branch).order_by(Branch.name.asc()).all()
    for branch in branches:
        all_branch_totals.setdefault(
            branch.id,
            {
                "branch_id": branch.id,
                "branch_name": branch.name,
                "total_cost": 0.0,
                "expense_count": 0,
                "item_totals": {},
            },
        )
    branch_totals = []
    for totals in all_branch_totals.values():
        item_totals = totals.pop("item_totals")
        if item_totals:
            item, amount = max(item_totals.items(), key=lambda pair: pair[1])
            totals["most_spent_item"] = {
                "item": item,
                "total_cost": round(amount, 2),
            }
        else:
            totals["most_spent_item"] = None
        totals["total_cost"] = round(totals["total_cost"], 2)
        branch_totals.append(totals)
    branch_totals.sort(key=lambda row: row["total_cost"], reverse=True)

    all_branches_total_cost = round(
        sum(row["total_cost"] for row in branch_totals),
        2,
    )
    highest_spending_branch = next(
        (row for row in branch_totals if row["total_cost"] > 0),
        None,
    )
    most_spent_item = None
    if all_item_totals:
        item, amount = max(all_item_totals.items(), key=lambda pair: pair[1])
        most_spent_item = {"item": item, "total_cost": round(amount, 2)}

    selected_expense_records = [
        (expense, branch_name)
        for expense, branch_name in all_expenses
        if branch_id is None or expense.branch_id == branch_id
    ]
    expenses = [
        {
            **expense_to_dict(expense),
            "branch_name": branch_name,
        }
        for expense, branch_name in selected_expense_records
    ]
    selected_total_cost = round(
        sum(float(expense.cost) for expense, _ in selected_expense_records),
        2,
    )
    selected_item_totals = {}
    for expense, _ in selected_expense_records:
        selected_item_totals[expense.item] = (
            selected_item_totals.get(expense.item, 0.0) + float(expense.cost)
        )
    selected_most_spent_item = None
    if selected_item_totals:
        item, amount = max(
            selected_item_totals.items(),
            key=lambda pair: pair[1],
        )
        selected_most_spent_item = {
            "item": item,
            "total_cost": round(amount, 2),
        }
    most_expensive_expense = max(
        expenses,
        key=lambda expense: expense["cost"],
        default=None,
    )

    return {
        "from_date": start_date.isoformat(),
        "to_date": end_date.isoformat(),
        "branch_id": branch_id,
        "total_cost": selected_total_cost,
        "expense_count": len(expenses),
        "most_spent_item": selected_most_spent_item,
        "most_expensive_expense": most_expensive_expense,
        "expenses": expenses,
        "all_branches_total_cost": all_branches_total_cost,
        "all_branches_most_spent_item": most_spent_item,
        "highest_spending_branch": highest_spending_branch,
        "branch_totals": branch_totals,
    }
