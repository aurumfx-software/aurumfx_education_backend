from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Enquiry, User
from schemas.enquiry import EnquiryCreate, EnquiryStatusUpdate, EnquiryResponse
from routers.auth import get_db, get_current_admin




router = APIRouter(
    prefix="/enquiries"
)




# ==========================================
# PUBLIC: CREATE ENQUIRY
# ==========================================

@router.post("", response_model=EnquiryResponse, tags=["User"])
def create_enquiry(
    enquiry_data: EnquiryCreate,
    db: Session = Depends(get_db)
):
    """
    Public endpoint: Submit a student admission enquiry or contact form
    """
    new_enquiry = Enquiry(
        name=enquiry_data.name,
        email=enquiry_data.email,
        phone=enquiry_data.phone,
        parents_phone=enquiry_data.parents_phone,
        course=enquiry_data.course,
        qualification=enquiry_data.qualification,
        message=enquiry_data.message,
        status="New"
    )
    db.add(new_enquiry)
    db.commit()
    db.refresh(new_enquiry)
    return new_enquiry



# ==========================================
# ADMIN: GET ALL ENQUIRIES
# ==========================================

@router.get("", response_model=List[EnquiryResponse], tags=["Admin"])
def get_all_enquiries(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """
    Admin only: Get all student admission enquiries ordered by newest first
    """
    enquiries = db.query(Enquiry).order_by(Enquiry.created_at.desc()).all()
    return enquiries


# ==========================================
# ADMIN: UPDATE ENQUIRY STATUS
# ==========================================
 
@router.put("/{enquiry_id}/status", response_model=EnquiryResponse, tags=["Admin"])
def update_enquiry_status(
    enquiry_id: int,
    status_data: EnquiryStatusUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """
    Admin only: Update status of an enquiry (e.g. New, Contacted, Admitted, Rejected)
    """
    enquiry = db.query(Enquiry).filter(Enquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(
            status_code=404,
            detail="Enquiry not found"
        )
    
    enquiry.status = status_data.status
    db.commit()
    db.refresh(enquiry)
    return enquiry




# ==========================================
# ADMIN: DELETE ENQUIRY
# ==========================================

@router.delete("/{enquiry_id}", tags=["Admin"])
def delete_enquiry(
    enquiry_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """
    Admin only: Delete an enquiry
    """
    enquiry = db.query(Enquiry).filter(Enquiry.id == enquiry_id).first()
    if not enquiry:
        raise HTTPException(
            status_code=404,
            detail="Enquiry not found"
        )
    
    db.delete(enquiry)
    db.commit()
    return {"message": "Enquiry deleted successfully"}




