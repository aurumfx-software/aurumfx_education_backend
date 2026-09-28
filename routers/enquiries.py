from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Enquiry, User, Branch

from schemas.enquiry import (
    EnquiryCreate,
    EnquiryStatusUpdate,
    EnquiryResponse
)

from routers.auth import (
    get_db,
    get_current_user,
    get_current_super_admin
)


router = APIRouter(
    prefix="/enquiries"
)


@router.get(
    "/branches",
    tags=["Student Enquiries"],
)
def get_enquiry_branches(
    db: Session = Depends(get_db),
):
    branches = (
        db.query(Branch)
        .filter(Branch.status == "Active")
        .order_by(Branch.name.asc())
        .all()
    )
    return [
        {
            "id": branch.id,
            "name": branch.name,
            "location": branch.location,
        }
        for branch in branches
    ]



# ==========================================
# PUBLIC: CREATE ENQUIRY
# ==========================================

@router.post(
    "",
    response_model=EnquiryResponse,
    tags=["Student Enquiries"]
)
def create_enquiry(
    enquiry_data: EnquiryCreate,
    db: Session = Depends(get_db)
):
    """
    Public endpoint:
    Submit a student admission enquiry or contact form.
    """

    branch = (
        db.query(Branch)
        .filter(
            Branch.id == enquiry_data.branch_id,
            Branch.status == "Active",
        )
        .first()
    )
    if not branch:
        raise HTTPException(
            status_code=404,
            detail="Active branch not found",
        )

    new_enquiry = Enquiry(
        branch_id=branch.id,
        name=enquiry_data.name,
        email=enquiry_data.email,
        phone=enquiry_data.phone,
        course=enquiry_data.course,
        qualification=enquiry_data.qualification,
        message=enquiry_data.message,
        status="New"
    )

    db.add(new_enquiry)

    db.commit()

    db.refresh(new_enquiry)

    return {
        "id": new_enquiry.id,
        "branch_id": branch.id,
        "branch_name": branch.name,
        "name": new_enquiry.name,
        "email": new_enquiry.email,
        "phone": new_enquiry.phone,
        "course": new_enquiry.course,
        "qualification": new_enquiry.qualification,
        "message": new_enquiry.message,
        "status": new_enquiry.status,
        "created_at": new_enquiry.created_at,
    }


@router.get(
    "/branch-admin",
    response_model=List[EnquiryResponse],
    tags=["Branch Admin Enquiries"],
)
def get_branch_admin_enquiries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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

    results = (
        db.query(Enquiry, Branch.name)
        .join(Branch, Branch.id == Enquiry.branch_id)
        .filter(Enquiry.branch_id == current_user.branch_id)
        .order_by(Enquiry.created_at.desc())
        .all()
    )
    return [
        {
            "id": enquiry.id,
            "branch_id": enquiry.branch_id,
            "branch_name": branch_name,
            "name": enquiry.name,
            "email": enquiry.email,
            "phone": enquiry.phone,
            "course": enquiry.course,
            "qualification": enquiry.qualification,
            "message": enquiry.message,
            "status": enquiry.status,
            "created_at": enquiry.created_at,
        }
        for enquiry, branch_name in results
    ]


# ==========================================
# SUPER ADMIN: GET ALL ENQUIRIES
# ==========================================

# @router.get(
#     "",
#     response_model=List[EnquiryResponse],
#     tags=["Super Admin"]
# )
# def get_all_enquiries(
#     db: Session = Depends(get_db),
#     current_admin: User = Depends(get_current_super_admin)
# ):
#     """
#     Super admin only:
#     Get all student admission enquiries ordered by newest first.
#     """

#     enquiries = (
#         db.query(Enquiry)
#         .order_by(Enquiry.created_at.desc())
#         .all()
#     )

#     return enquiries


# ==========================================
# SUPER ADMIN: UPDATE ENQUIRY STATUS
# ==========================================

# @router.put(
#     "/{enquiry_id}/status",
#     response_model=EnquiryResponse,
#     tags=["Super Admin"]
# )
# def update_enquiry_status(
#     enquiry_id: int,
#     status_data: EnquiryStatusUpdate,
#     db: Session = Depends(get_db),
#     current_admin: User = Depends(get_current_super_admin)
# ):
#     """
#     Super admin only:
#     Update status of an enquiry.
#     """

#     enquiry = (
#         db.query(Enquiry)
#         .filter(Enquiry.id == enquiry_id)
#         .first()
#     )

#     if not enquiry:
#         raise HTTPException(
#             status_code=404,
#             detail="Enquiry not found"
#         )

#     enquiry.status = status_data.status

#     db.commit()

#     db.refresh(enquiry)

#     return enquiry


# # ==========================================
# # SUPER ADMIN: DELETE ENQUIRY
# # ==========================================

# @router.delete(
#     "/{enquiry_id}",
#     tags=["Super Admin"]
# )
# def delete_enquiry(
#     enquiry_id: int,
#     db: Session = Depends(get_db),
#     current_admin: User = Depends(get_current_super_admin)
# ):
#     """
#     Super admin only:
#     Delete an enquiry.
#     """

#     enquiry = (
#         db.query(Enquiry)
#         .filter(Enquiry.id == enquiry_id)
#         .first()
#     )

#     if not enquiry:
#         raise HTTPException(
#             status_code=404,
#             detail="Enquiry not found"
#         )

#     db.delete(enquiry)

#     db.commit()

#     return {
#         "message": "Enquiry deleted successfully"
#     }