import re
import uuid
from datetime import datetime, timezone
from pathlib import PurePath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    Branch,
    Course,
    CourseTask,
    CourseStudyMaterial,
    Enrollment,
    Staff,
    StaffCourse,
    StudentTaskAssignment,
    User,
)
from routers.auth import get_current_user
from schemas.assignment import AssignmentGradeUpdate
from schemas.staff_task import StaffTaskCreate
from utils.assignment_files import assignment_pdf_url
from utils.spaces import SPACES_BUCKET, spaces_client
from utils.study_material_files import (
    delete_study_material_pdf,
    study_material_download_url,
    upload_study_material_pdf,
)


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
        .filter(
            StaffCourse.staff_id == staff.id,
            Course.branch_id == staff.branch_id,
        )
        .order_by(Course.title.asc())
        .all()
    )
    if not courses:
        course = (
            db.query(Course)
            .filter(
                Course.id == staff.course_id,
                Course.branch_id == staff.branch_id,
            )
            .first()
        )
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
        "registration_status": "success",
        "document_status": staff.verification_status,
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


def build_staff_verification_reviewers(db: Session, staff: Staff):
    reviewer_ids = {
        reviewer_id
        for reviewer_id in (
            staff.verification_approved_by_user_id,
            staff.verification_rejected_by_user_id,
        )
        if reviewer_id is not None
    }
    reviewers = (
        {
            user.id: user
            for user in db.query(User).filter(User.id.in_(reviewer_ids)).all()
        }
        if reviewer_ids
        else {}
    )

    def reviewer_details(reviewer_id: int | None):
        reviewer = reviewers.get(reviewer_id)
        if not reviewer:
            return None
        return {
            "id": reviewer.id,
            "name": reviewer.name,
            "role": reviewer.role,
        }

    return {
        "verification_approved_by": reviewer_details(
            staff.verification_approved_by_user_id
        ),
        "verification_rejected_by": reviewer_details(
            staff.verification_rejected_by_user_id
        ),
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


@router.get("/dashboard")
def get_my_staff_dashboard(
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    branch = db.query(Branch).filter(Branch.id == staff.branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Staff branch not found")

    courses = get_staff_courses(db, staff)
    course_ids = [course.id for course in courses]
    students_by_course = {}
    total_assigned_course_students = 0
    if courses:
        student_counts = (
            db.query(
                Enrollment.course_id,
                func.count(func.distinct(Enrollment.user_id)).label("student_count"),
            )
            .filter(
                Enrollment.course_id.in_(course_ids),
                Enrollment.branch_id == staff.branch_id,
            )
            .group_by(Enrollment.course_id)
            .all()
        )
        students_by_course = {
            row.course_id: row.student_count for row in student_counts
        }
        total_assigned_course_students = (
            db.query(func.count(func.distinct(Enrollment.user_id)))
            .filter(
                Enrollment.course_id.in_(course_ids),
                Enrollment.branch_id == staff.branch_id,
            )
            .scalar()
            or 0
        )
    branch_total_students = (
        db.query(func.count(func.distinct(Enrollment.user_id)))
        .filter(Enrollment.branch_id == staff.branch_id)
        .scalar()
        or 0
    )

    return {
        "staff": {
            "staff_id": staff.id,
            "staff_code": staff.staff_code,
            "name": staff.name,
        },
        "branch": {
            "branch_id": branch.id,
            "branch_name": branch.name,
            "branch_location": branch.location,
        },
        "summary": {
            "total_assigned_courses": len(courses),
            "total_students_in_assigned_courses": total_assigned_course_students,
            "branch_total_students": branch_total_students,
        },
        "assigned_courses": [
            {
                "course_id": course.id,
                "course_title": course.title,
                "total_students": students_by_course.get(course.id, 0),
            }
            for course in courses
        ],
    }


@router.get("/courses/{course_id}/students")
def get_my_course_students(
    course_id: int,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    course = next(
        (course for course in get_staff_courses(db, staff) if course.id == course_id),
        None,
    )
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course is not assigned to this staff member",
        )

    enrollment_rows = (
        db.query(Enrollment, User)
        .join(User, User.id == Enrollment.user_id)
        .filter(
            Enrollment.course_id == course.id,
            Enrollment.branch_id == staff.branch_id,
        )
        .order_by(Enrollment.id.desc())
        .all()
    )

    students = []
    seen_student_ids = set()
    for enrollment, user in enrollment_rows:
        if enrollment.user_id in seen_student_ids:
            continue
        seen_student_ids.add(enrollment.user_id)
        students.append(
            {
                "student_id": user.id,
                "name": enrollment.name or user.name,
                "email": enrollment.email or user.email,
                "phone": enrollment.phone or user.phone,
                "profile_image": user.profile_image,
                "parent_name": enrollment.parent_name or user.parent_name,
                "parent_phone": enrollment.parent_phone or user.parent_phone,
                "highest_qualification": (
                    enrollment.highest_qualification or user.highest_qualification
                ),
                "address": enrollment.address or user.address,
                "account_status": user.status,
                "enrollment": {
                    "enrollment_id": enrollment.id,
                    "admission_date": enrollment.admission_date,
                    "enrolled_at": enrollment.created_at,
                    "course_status": enrollment.course_status,
                    "branch_approval_status": enrollment.branch_approval_status,
                    "super_admin_approval_status": (
                        enrollment.super_admin_approval_status
                    ),
                },
            }
        )

    return {
        "course": {
            "course_id": course.id,
            "course_title": course.title,
            "branch_id": course.branch_id,
        },
        "total_students": len(students),
        "students": students,
    }


@router.post(
    "/courses/{course_id}/study-materials",
    status_code=201,
)
async def upload_course_study_material(
    course_id: int,
    title: str = Form(..., min_length=1, max_length=255),
    file: UploadFile = File(...),
    description: str | None = Form(default=None, max_length=5000),
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    course = next(
        (course for course in get_staff_courses(db, staff) if course.id == course_id),
        None,
    )
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course is not assigned to this staff member",
        )

    title = title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    description = description.strip() if description else None
    if description == "":
        description = None

    file_key, filename = await upload_study_material_pdf(
        course.id,
        staff.id,
        file,
    )
    material = CourseStudyMaterial(
        course_id=course.id,
        staff_id=staff.id,
        title=title,
        description=description,
        file_key=file_key,
        filename=filename,
    )
    db.add(material)
    try:
        db.commit()
        db.refresh(material)
    except Exception:
        db.rollback()
        delete_study_material_pdf(file_key)
        raise

    return {
        "id": material.id,
        "course_id": course.id,
        "course_title": course.title,
        "title": material.title,
        "description": material.description,
        "filename": material.filename,
        "created_at": material.created_at,
        "download_url": study_material_download_url(
            material.file_key,
            material.filename,
        ),
    }


@router.get("/courses/{course_id}/study-materials")
def get_course_study_materials_for_staff(
    course_id: int,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    course = next(
        (course for course in get_staff_courses(db, staff) if course.id == course_id),
        None,
    )
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course is not assigned to this staff member",
        )

    materials = (
        db.query(CourseStudyMaterial, Staff)
        .join(Staff, Staff.id == CourseStudyMaterial.staff_id)
        .filter(CourseStudyMaterial.course_id == course.id)
        .order_by(
            CourseStudyMaterial.created_at.desc(),
            CourseStudyMaterial.id.desc(),
        )
        .all()
    )
    return {
        "course_id": course.id,
        "course_title": course.title,
        "total": len(materials),
        "materials": [
            {
                "id": material.id,
                "title": material.title,
                "description": material.description,
                "filename": material.filename,
                "uploaded_by": {
                    "staff_id": uploader.id,
                    "staff_name": uploader.name,
                },
                "created_at": material.created_at,
                "download_url": study_material_download_url(
                    material.file_key,
                    material.filename,
                ),
            }
            for material, uploader in materials
        ],
    }


@router.post("/courses/{course_id}/assignments", status_code=201)
def create_course_assignment(
    course_id: int,
    task_data: StaffTaskCreate,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    course = next(
        (course for course in get_staff_courses(db, staff) if course.id == course_id),
        None,
    )
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course is not assigned to this staff member",
        )

    enrolled_student_ids = {
        row.user_id
        for row in (
            db.query(Enrollment.user_id)
            .filter(
                Enrollment.course_id == course.id,
                Enrollment.branch_id == staff.branch_id,
            )
            .distinct()
            .all()
        )
    }
    if task_data.student_ids is None:
        student_ids = sorted(enrolled_student_ids)
    else:
        student_ids = list(dict.fromkeys(task_data.student_ids))
        unenrolled_ids = set(student_ids) - enrolled_student_ids
        if unenrolled_ids:
            raise HTTPException(
                status_code=404,
                detail="One or more selected students are not enrolled in this course",
            )

    if not student_ids:
        raise HTTPException(
            status_code=400,
            detail="There are no enrolled students to assign this task to",
        )

    task = CourseTask(
        course_id=course.id,
        staff_id=staff.id,
        title=task_data.title.strip(),
        description=task_data.description.strip(),
        due_date=task_data.due_date,
        max_marks=task_data.max_marks,
    )
    db.add(task)
    db.flush()
    db.add_all(
        [
            StudentTaskAssignment(task_id=task.id, student_id=student_id)
            for student_id in student_ids
        ]
    )
    db.commit()
    db.refresh(task)

    return {
        "task_id": task.id,
        "course_id": course.id,
        "course_title": course.title,
        "title": task.title,
        "description": task.description,
        "due_date": task.due_date,
        "max_marks": task.max_marks,
        "created_at": task.created_at,
        "assigned_student_count": len(student_ids),
        "student_ids": student_ids,
    }


@router.get("/courses/{course_id}/assignments")
def get_course_assignments(
    course_id: int,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    course = next(
        (course for course in get_staff_courses(db, staff) if course.id == course_id),
        None,
    )
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course is not assigned to this staff member",
        )

    tasks = (
        db.query(CourseTask)
        .filter(
            CourseTask.course_id == course.id,
            CourseTask.staff_id == staff.id,
        )
        .order_by(CourseTask.created_at.desc(), CourseTask.id.desc())
        .all()
    )
    assignments_by_task = {task.id: [] for task in tasks}
    max_marks_by_task = {task.id: task.max_marks for task in tasks}
    if tasks:
        assignment_rows = (
            db.query(StudentTaskAssignment, User)
            .join(User, User.id == StudentTaskAssignment.student_id)
            .filter(StudentTaskAssignment.task_id.in_(assignments_by_task))
            .order_by(StudentTaskAssignment.assigned_at.asc())
            .all()
        )
        for assignment, student in assignment_rows:
            status = (
                "verified"
                if assignment.marks_obtained is not None
                else "submitted"
                if assignment.submitted_at is not None
                else "pending_submission"
            )
            assignments_by_task[assignment.task_id].append(
                {
                    "student_id": student.id,
                    "name": student.name,
                    "email": student.email,
                    "assigned_at": assignment.assigned_at,
                    "assignment_id": assignment.id,
                    "status": status,
                    "submission_url": assignment_pdf_url(assignment.submission_key),
                    "submission_filename": assignment.submission_filename,
                    "submitted_at": assignment.submitted_at,
                    "marks_obtained": assignment.marks_obtained,
                    "max_marks": max_marks_by_task[assignment.task_id],
                    "feedback": assignment.feedback,
                    "marked_at": assignment.marked_at,
                }
            )

    return {
        "course_id": course.id,
        "course_title": course.title,
        "total_assignments": len(tasks),
        "assignments": [
            {
                "task_id": task.id,
                "title": task.title,
                "description": task.description,
                "due_date": task.due_date,
                "max_marks": task.max_marks,
                "created_at": task.created_at,
                "assigned_student_count": len(assignments_by_task[task.id]),
                "students": assignments_by_task[task.id],
            }
            for task in tasks
        ],
    }


@router.get("/courses/{course_id}/verified-assignments")
def get_verified_assignments(
    course_id: int,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    course = next(
        (course for course in get_staff_courses(db, staff) if course.id == course_id),
        None,
    )
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course is not assigned to this staff member",
        )

    rows = (
        db.query(StudentTaskAssignment, CourseTask, User)
        .join(CourseTask, CourseTask.id == StudentTaskAssignment.task_id)
        .join(User, User.id == StudentTaskAssignment.student_id)
        .filter(
            CourseTask.course_id == course.id,
            CourseTask.staff_id == staff.id,
            StudentTaskAssignment.marks_obtained.isnot(None),
        )
        .order_by(
            StudentTaskAssignment.marked_at.desc(),
            StudentTaskAssignment.id.desc(),
        )
        .all()
    )
    return {
        "course_id": course.id,
        "course_title": course.title,
        "total_verified": len(rows),
        "assignments": [
            {
                "assignment_id": assignment.id,
                "task_id": task.id,
                "title": task.title,
                "student_id": student.id,
                "student_name": student.name,
                "submission_url": assignment_pdf_url(assignment.submission_key),
                "submission_filename": assignment.submission_filename,
                "submitted_at": assignment.submitted_at,
                "marks_obtained": assignment.marks_obtained,
                "max_marks": task.max_marks,
                "feedback": assignment.feedback,
                "marked_at": assignment.marked_at,
            }
            for assignment, task, student in rows
        ],
    }


@router.put("/assignments/{assignment_id}/marks")
def update_assignment_marks(
    assignment_id: int,
    grade_data: AssignmentGradeUpdate,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    assignment_row = (
        db.query(StudentTaskAssignment, CourseTask)
        .join(CourseTask, CourseTask.id == StudentTaskAssignment.task_id)
        .filter(
            StudentTaskAssignment.id == assignment_id,
            CourseTask.staff_id == staff.id,
        )
        .first()
    )
    if not assignment_row:
        raise HTTPException(
            status_code=404,
            detail="Assignment is not assigned to this staff member",
        )

    assignment, task = assignment_row
    if assignment.submitted_at is None:
        raise HTTPException(
            status_code=409,
            detail="The student has not submitted this assignment",
        )
    if grade_data.marks_obtained > task.max_marks:
        raise HTTPException(
            status_code=400,
            detail=f"Marks cannot exceed the total of {task.max_marks}",
        )

    assignment.marks_obtained = grade_data.marks_obtained
    assignment.feedback = (
        grade_data.feedback.strip() if grade_data.feedback else None
    )
    assignment.marked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assignment)

    return {
        "message": "Assignment marks saved successfully",
        "assignment_id": assignment.id,
        "task_id": task.id,
        "student_id": assignment.student_id,
        "status": "verified",
        "marks_obtained": assignment.marks_obtained,
        "max_marks": task.max_marks,
        "feedback": assignment.feedback,
        "marked_at": assignment.marked_at,
    }


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
        staff.verification_approved_by_user_id = None
        staff.verification_rejection_reason = None
        staff.verification_rejected_at = None
        staff.verification_rejected_by_user_id = None
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
