import re
import uuid
from datetime import datetime, timezone
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Branch, Course, Staff, StaffCourse, User
from routers.auth import get_current_user
from utils.spaces import SPACES_BUCKET, spaces_client


router = APIRouter(
    prefix="/staff",
    tags=["Staff Portal"],
)

ALLOWED_DOCUMENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_staff_record(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Staff:
    if current_user.role != "staff":
        raise HTTPException(status_code=403, detail="Staff access required")

    staff = (
        db.query(Staff)
        .filter(
            Staff.user_id == current_user.id,
            Staff.status == "Active",
        )
        .first()
    )
    if not staff:
        raise HTTPException(status_code=404, detail="Active staff profile not found")
    return staff


def get_staff_courses(db: Session, staff: Staff):
    courses = (
        db.query(Course)
        .join(StaffCourse, StaffCourse.course_id == Course.id)
        .filter(StaffCourse.staff_id == staff.id)
        .order_by(Course.title.asc())
        .all()
    )
    if not courses:
        course = db.query(Course).filter(Course.id == staff.course_id).first()
        if course:
            courses = [course]
    return courses


def private_document_url(object_key: str | None):
    if not object_key:
        return None
    try:
        return spaces_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": SPACES_BUCKET, "Key": object_key},
            ExpiresIn=900,
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to create a private document link: {error}",
        )


def build_staff_profile(db: Session, staff: Staff):
    branch = db.query(Branch).filter(Branch.id == staff.branch_id).first()
    courses = get_staff_courses(db, staff)
    user = db.query(User).filter(User.id == staff.user_id).first()
    return {
        "staff_id": staff.id,
        "user_id": staff.user_id,
        "staff_code": staff.staff_code,
        "name": staff.name,
        "email": staff.email,
        "phone": staff.phone,
        "address": staff.address,
        "salary": staff.salary,
        "employment_status": staff.status,
        "verification_status": staff.verification_status,
        "aadhaar_number": staff.aadhaar_number,
        "pan_number": staff.pan_number,
        "bank_account_number": staff.bank_account_number,
        "bank_ifsc": staff.bank_ifsc,
        "documents": {
            "aadhaar_front_url": private_document_url(staff.aadhaar_front_key),
            "aadhaar_back_url": private_document_url(staff.aadhaar_back_key),
            "pan_card_url": private_document_url(staff.pan_card_key),
            "bank_passbook_url": private_document_url(staff.bank_passbook_key),
            "other_document_url": private_document_url(staff.other_document_key),
            "other_document_name": staff.other_document_name,
        },
        "verification_submitted_at": staff.verification_submitted_at,
        "verification_approved_at": staff.verification_approved_at,
        "verification_rejection_reason": staff.verification_rejection_reason,
        "verification_rejected_at": staff.verification_rejected_at,
        "branch": (
            {
                "branch_id": branch.id,
                "branch_name": branch.name,
                "branch_location": branch.location,
            }
            if branch
            else None
        ),
        "courses": [
            {"course_id": course.id, "course_title": course.title}
            for course in courses
        ],
        "created_at": staff.created_at,
        "account_status": user.status if user else None,
    }


def validate_document_numbers(
    aadhaar_number: str | None,
    pan_number: str | None,
    bank_account_number: str | None,
    bank_ifsc: str | None,
):
    if aadhaar_number is not None:
        aadhaar_number = re.sub(r"\s+", "", aadhaar_number)
        if not re.fullmatch(r"[2-9][0-9]{11}", aadhaar_number):
            raise HTTPException(
                status_code=400,
                detail="Aadhaar number must contain 12 digits",
            )

    if pan_number is not None:
        pan_number = pan_number.strip().upper()
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan_number):
            raise HTTPException(
                status_code=400,
                detail="PAN number format is invalid",
            )

    if bank_account_number is not None:
        bank_account_number = re.sub(r"\s+", "", bank_account_number)
        if not re.fullmatch(r"[0-9]{8,18}", bank_account_number):
            raise HTTPException(
                status_code=400,
                detail="Bank account number must contain 8 to 18 digits",
            )

    if bank_ifsc is not None:
        bank_ifsc = bank_ifsc.strip().upper()
        if not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", bank_ifsc):
            raise HTTPException(status_code=400, detail="IFSC code format is invalid")

    return aadhaar_number, pan_number, bank_account_number, bank_ifsc


async def upload_private_document(staff_id: int, document_kind: str, upload: UploadFile):
    if upload.content_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Documents must be JPEG, PNG, WEBP, or PDF files",
        )

    content = await upload.read(MAX_DOCUMENT_BYTES + 1)
    if len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Each document must be 10 MB or smaller")

    extension = ALLOWED_DOCUMENT_TYPES[upload.content_type]
    object_key = f"staff-documents/{staff_id}/{document_kind}/{uuid.uuid4()}{extension}"
    try:
        spaces_client.put_object(
            Bucket=SPACES_BUCKET,
            Key=object_key,
            Body=content,
            ContentType=upload.content_type,
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Document upload failed: {error}")
    return object_key


def delete_private_document(object_key: str | None):
    if not object_key:
        return
    try:
        spaces_client.delete_object(Bucket=SPACES_BUCKET, Key=object_key)
    except Exception as error:
        print(f"Unable to remove replaced staff document: {error}")


def require_documents_complete(staff: Staff):
    required_values = {
        "Aadhaar number": staff.aadhaar_number,
        "PAN number": staff.pan_number,
        "bank account number": staff.bank_account_number,
        "IFSC code": staff.bank_ifsc,
        "Aadhaar front image": staff.aadhaar_front_key,
        "Aadhaar back image": staff.aadhaar_back_key,
        "PAN card image": staff.pan_card_key,
        "bank passbook image": staff.bank_passbook_key,
    }
    missing = [label for label, value in required_values.items() if not value]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="Staff documents are incomplete: " + ", ".join(missing),
        )


@router.get("/me")
def get_my_staff_profile(
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    return build_staff_profile(db, staff)


@router.put("/me/documents")
async def update_my_staff_documents(
    aadhaar_number: str | None = Form(default=None),
    pan_number: str | None = Form(default=None),
    bank_account_number: str | None = Form(default=None),
    bank_ifsc: str | None = Form(default=None),
    aadhaar_front: UploadFile | None = File(default=None),
    aadhaar_back: UploadFile | None = File(default=None),
    pan_card: UploadFile | None = File(default=None),
    bank_passbook: UploadFile | None = File(default=None),
    other_document: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    if staff.verification_status == "approved":
        raise HTTPException(
            status_code=409,
            detail="Approved staff documents can no longer be edited",
        )

    aadhaar_number, pan_number, bank_account_number, bank_ifsc = validate_document_numbers(
        aadhaar_number,
        pan_number,
        bank_account_number,
        bank_ifsc,
    )

    uploads = {
        "aadhaar_front_key": ("aadhaar-front", aadhaar_front),
        "aadhaar_back_key": ("aadhaar-back", aadhaar_back),
        "pan_card_key": ("pan-card", pan_card),
        "bank_passbook_key": ("bank-passbook", bank_passbook),
        "other_document_key": ("other-document", other_document),
    }
    has_values = any(
        value is not None
        for value in (
            aadhaar_number,
            pan_number,
            bank_account_number,
            bank_ifsc,
        )
    )
    if not has_values and not any(upload is not None for _, upload in uploads.values()):
        raise HTTPException(status_code=400, detail="Submit at least one document or detail")

    uploaded_keys = []
    replaced_keys = []
    try:
        for field, (document_kind, upload) in uploads.items():
            if upload is None:
                continue
            new_key = await upload_private_document(staff.id, document_kind, upload)
            uploaded_keys.append(new_key)
            old_key = getattr(staff, field)
            if old_key:
                replaced_keys.append(old_key)
            setattr(staff, field, new_key)
            if field == "other_document_key":
                staff.other_document_name = PurePath(upload.filename or "document").name

        if aadhaar_number is not None:
            staff.aadhaar_number = aadhaar_number
        if pan_number is not None:
            staff.pan_number = pan_number
        if bank_account_number is not None:
            staff.bank_account_number = bank_account_number
        if bank_ifsc is not None:
            staff.bank_ifsc = bank_ifsc

        staff.verification_status = "pending"
        staff.verification_submitted_at = datetime.now(timezone.utc)
        staff.verification_approved_at = None
        staff.verification_rejection_reason = None
        staff.verification_rejected_at = None
        db.commit()
        db.refresh(staff)
    except Exception:
        db.rollback()
        for object_key in uploaded_keys:
            delete_private_document(object_key)
        raise

    for object_key in replaced_keys:
        delete_private_document(object_key)

    return build_staff_profile(db, staff)
