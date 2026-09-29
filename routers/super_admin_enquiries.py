from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, Enquiry, User
from routers.auth import get_current_super_admin
from schemas.enquiry import EnquiryResponse


router = APIRouter(
    prefix="/super-admin/enquiries",
    tags=["Super Admin Enquiries"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/branches")
def get_branches(
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


@router.get(
    "/branches/{branch_id}",
    response_model=list[EnquiryResponse],
)
def get_branch_enquiries(
    branch_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branch = (
        db.query(Branch)
        .filter(
            Branch.id == branch_id,
            Branch.status == "Active",
        )
        .first()
    )
    if not branch:
        raise HTTPException(status_code=404, detail="Active branch not found")

    enquiries = (
        db.query(Enquiry)
        .filter(Enquiry.branch_id == branch_id)
        .order_by(Enquiry.created_at.desc())
        .all()
    )
    return [
        {
            "id": enquiry.id,
            "branch_id": branch.id,
            "branch_name": branch.name,
            "name": enquiry.name,
            "email": enquiry.email,
            "phone": enquiry.phone,
            "course": enquiry.course,
            "qualification": enquiry.qualification,
            "message": enquiry.message,
            "status": enquiry.status,
            "created_at": enquiry.created_at,
        }
        for enquiry in enquiries
    ]
